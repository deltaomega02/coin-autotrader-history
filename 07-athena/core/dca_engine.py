"""DCA Engine — 동적 매일 자동 매수 + 누적 매수.

학술 검증:
- UCLA: BTC DCA 1년 76% / 2년 93% / 3년 100% 양수
- 12년 +6,712%

설계:
- 매일 02:00 UTC 실행
- 매수액 = 시드의 X% × multiplier (동적)
- 자산별 매수액 < min_order (Bybit $5) 면 누적 → 도달 시 매수
- USDT 부족 시 가능한 만큼 매수 또는 누적 유지

모든 예외처리:
- multiplier=0 → 누적만
- USDT 잔고 0 또는 부족 → 누적 유지
- 가격 조회 실패 → 누적 유지
- 매수 API 실패 → 누적 유지 (다음에 재시도)
- DB 실패 → 로그 + 계속
- 자산 비활성화 (symbol 누락) → 스킵
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from exchange import bybit_spot
from exchange.bybit_spot_client import BybitSpotError
from core import cost_basis_tracker
from database import db
from config import ATHENA, get_logger

logger = get_logger("dca")


@dataclass
class DcaConfig:
    """동적 DCA 설정 (시드 % 기반)."""
    daily_pct_per_asset: Dict[str, float] = None

    multiplier_min: float = 0.0
    multiplier_max: float = 2.0
    multiplier_default: float = 1.0

    # Bybit Spot 최소 주문 (USDT)
    min_order_usdt: float = 5.0
    # USDT 잔고 보호 (한 번에 USDT의 X% 이상 안 씀)
    max_usdt_use_per_day_pct: float = 0.50
    # 누적 한도 (한 자산당 최대 누적 USDT — 너무 많이 쌓이지 않게)
    max_pending_per_asset_usdt: float = 100.0

    def __post_init__(self):
        if self.daily_pct_per_asset is None:
            # BTC 60 / ETH 30 / SOL 10 비중. 총 0.36%/일.
            self.daily_pct_per_asset = {
                "BTC": 0.00216,
                "ETH": 0.00108,
                "SOL": 0.00036,
            }


DCA = DcaConfig()


def execute_daily_dca(multiplier: float = 1.0,
                      paper_mode: bool = True) -> List[Dict[str, Any]]:
    """오늘의 동적 DCA 매수 (누적 매수 포함, 모든 예외처리).

    Args:
        multiplier: AI Guardian이 정한 비율 (0.0 ~ 2.0)
        paper_mode: True면 시뮬

    Returns:
        결과 리스트 (executed True/False, reason, 누적 정보)
    """
    # 0. multiplier 안전 클램프
    multiplier = max(DCA.multiplier_min, min(DCA.multiplier_max, multiplier))

    # 1. 잔고 조회 (실패 시 안전 종료)
    try:
        portfolio = bybit_spot.get_portfolio_value_usdt()
    except Exception as e:
        logger.error(f"[DCA] 잔고 조회 실패: {e}")
        return [{"executed": False, "reason": "balance_fetch_failed", "error": str(e)}]

    usdt_balance = portfolio.get("values", {}).get("USDT", 0)
    total_value = portfolio.get("total_usdt", 0)

    if total_value <= 0:
        logger.warning("[DCA] 총자산 0 — 매수 불가")
        return [{"executed": False, "reason": "zero_total_value"}]

    # 2. multiplier=0이면 매수 X (단 누적도 X — AI 결정 존중)
    if multiplier == 0.0:
        logger.info("[DCA] multiplier=0 — 매수 정지 (AI 정점 신호)")
        return [{"executed": False, "reason": "multiplier_zero", "multiplier": 0}]

    # 3. USDT 사용 한도 (한 번에 USDT의 50% 이상 X)
    max_usdt_today = usdt_balance * DCA.max_usdt_use_per_day_pct

    logger.info(
        f"[DCA] 총자산 ${total_value:.2f} / USDT ${usdt_balance:.2f} / "
        f"multiplier {multiplier:.2f} / 일일 한도 ${max_usdt_today:.2f}"
    )

    # USDT 거의 0이면 모든 자산 누적만
    if usdt_balance < DCA.min_order_usdt:
        logger.warning(f"[DCA] USDT ${usdt_balance:.2f} < min ${DCA.min_order_usdt} — 모든 자산 누적만")
        results = []
        for asset, daily_pct in DCA.daily_pct_per_asset.items():
            today_amount = total_value * daily_pct * multiplier
            try:
                _accumulate(asset, today_amount)
                results.append({
                    "asset": asset, "executed": False,
                    "reason": "no_usdt_accumulated",
                    "today_amount": round(today_amount, 4),
                })
            except Exception as e:
                logger.error(f"[DCA] {asset} 누적 실패: {e}")
        return results

    # 4. 자산별 처리
    results = []
    usdt_used_today = 0.0

    for asset, daily_pct in DCA.daily_pct_per_asset.items():
        try:
            result = _process_asset(
                asset=asset,
                today_amount=total_value * daily_pct * multiplier,
                usdt_remaining=max(0, max_usdt_today - usdt_used_today),
                multiplier=multiplier,
                paper_mode=paper_mode,
            )
            results.append(result)
            if result.get("executed"):
                usdt_used_today += result.get("value_usdt", 0)
        except Exception as e:
            logger.exception(f"[DCA] {asset} 처리 중 예외: {e}")
            results.append({
                "asset": asset, "executed": False,
                "reason": "unexpected_exception", "error": str(e),
            })

    return results


def _process_asset(asset: str, today_amount: float, usdt_remaining: float,
                   multiplier: float, paper_mode: bool) -> Dict[str, Any]:
    """단일 자산 DCA 처리 (예외처리 강화)."""

    symbol = ATHENA.SYMBOLS.get(asset)
    if not symbol:
        return {"asset": asset, "executed": False, "reason": "no_symbol"}

    # 누적액 조회 (DB 실패 시 0 가정)
    try:
        pending = db.get_dca_pending(asset)
    except Exception as e:
        logger.error(f"[DCA] {asset} 누적 조회 실패: {e} → 0으로 가정")
        pending = 0.0

    target_amount = today_amount + pending  # 매수 시도 액수

    # min 미달 → 누적
    if target_amount < DCA.min_order_usdt:
        new_total = pending + today_amount
        # 누적 한도 체크
        if new_total > DCA.max_pending_per_asset_usdt:
            logger.warning(
                f"[DCA] {asset} 누적 {new_total:.2f} > 한도 {DCA.max_pending_per_asset_usdt} — "
                f"한도까지만 누적"
            )
            new_total = DCA.max_pending_per_asset_usdt
            today_to_add = max(0, new_total - pending)
        else:
            today_to_add = today_amount

        try:
            db.add_dca_pending(asset, today_to_add)
        except Exception as e:
            logger.error(f"[DCA] {asset} 누적 저장 실패: {e}")

        logger.info(
            f"[DCA] {asset} ${target_amount:.2f} < min ${DCA.min_order_usdt} — "
            f"누적 (오늘 +${today_to_add:.2f} = 총 ${new_total:.2f})"
        )
        return {
            "asset": asset, "executed": False, "reason": "below_min_accumulated",
            "today_amount": round(today_amount, 4),
            "pending_total": round(new_total, 2),
        }

    # USDT 잔고 부족
    if usdt_remaining < DCA.min_order_usdt:
        # 누적은 유지, 오늘치만 추가
        try:
            db.add_dca_pending(asset, today_amount)
        except Exception:
            pass
        return {
            "asset": asset, "executed": False, "reason": "no_usdt_left",
            "today_amount": round(today_amount, 4),
        }

    # USDT 잔고 한도까지만 매수
    actual_amount = min(target_amount, usdt_remaining)
    actual_amount = round(actual_amount, 2)  # Bybit 소수점 2자리

    if actual_amount < DCA.min_order_usdt:
        try:
            db.add_dca_pending(asset, today_amount)
        except Exception:
            pass
        return {
            "asset": asset, "executed": False, "reason": "rounded_below_min",
            "today_amount": round(today_amount, 4),
        }

    # 가격 조회 (실패 시 누적 유지)
    try:
        ticker = bybit_spot.get_ticker(symbol)
        price = float(ticker.get("lastPrice", 0) or 0)
    except Exception as e:
        logger.error(f"[DCA] {symbol} 가격 조회 실패: {e}")
        try:
            db.add_dca_pending(asset, today_amount)
        except Exception:
            pass
        return {
            "asset": asset, "executed": False, "reason": "price_fetch_failed",
            "error": str(e),
        }

    if price <= 0:
        try:
            db.add_dca_pending(asset, today_amount)
        except Exception:
            pass
        return {
            "asset": asset, "executed": False, "reason": "price_zero",
        }

    qty = actual_amount / price

    # ── 페이퍼 모드 ──
    if paper_mode:
        logger.info(
            f"[DCA PAPER] Buy {asset} ${actual_amount:.2f} @ ${price:.2f} = {qty:.6f} "
            f"(누적 ${pending:.2f} + 오늘 ${today_amount:.2f})"
        )
        try:
            cost_basis_tracker.record_buy(asset, qty, price)
            db.reset_dca_pending(asset)
        except Exception as e:
            logger.error(f"[DCA] {asset} 평단 갱신/누적 리셋 실패: {e}")

        return {
            "asset": asset, "executed": True, "paper": True,
            "value_usdt": actual_amount, "qty": qty, "price": price,
            "pending_consumed": round(pending, 2),
        }

    # ── 실전 모드 ──
    try:
        resp = bybit_spot.place_market_buy(symbol=symbol, quote_qty=actual_amount)
        order_id = resp.get("orderId") if resp else None

        logger.info(
            f"[DCA LIVE] Buy {asset} ${actual_amount:.2f} order_id={order_id} "
            f"(누적 ${pending:.2f} 소진)"
        )

        # 평단 + 누적 리셋
        try:
            cost_basis_tracker.record_buy(asset, qty, price)
            db.reset_dca_pending(asset)
        except Exception as e:
            logger.error(f"[DCA] {asset} 평단/누적 리셋 실패 (매수는 성공): {e}")

        return {
            "asset": asset, "executed": True, "paper": False,
            "value_usdt": actual_amount, "qty": qty, "price": price,
            "order_id": order_id, "pending_consumed": round(pending, 2),
        }
    except BybitSpotError as e:
        logger.error(f"[DCA] {asset} 매수 실패 (누적 유지): {e}")
        # 매수 실패 → 오늘치 누적 추가 (다음에 재시도)
        try:
            db.add_dca_pending(asset, today_amount)
        except Exception:
            pass
        return {
            "asset": asset, "executed": False, "reason": "order_failed",
            "error": str(e),
            "today_amount": round(today_amount, 4),
        }
    except Exception as e:
        logger.exception(f"[DCA] {asset} 예상 외 매수 에러: {e}")
        try:
            db.add_dca_pending(asset, today_amount)
        except Exception:
            pass
        return {
            "asset": asset, "executed": False, "reason": "unexpected_error",
            "error": str(e),
        }


def _accumulate(asset: str, amount: float):
    """누적 헬퍼 (한도 체크 포함)."""
    try:
        pending = db.get_dca_pending(asset)
        if pending + amount > DCA.max_pending_per_asset_usdt:
            amount = max(0, DCA.max_pending_per_asset_usdt - pending)
        db.add_dca_pending(asset, amount)
    except Exception as e:
        logger.error(f"[DCA] {asset} 누적 실패: {e}")


def get_dca_summary() -> Dict[str, Any]:
    """DCA 설정 + 누적 현황 (AI 컨텍스트용)."""
    try:
        portfolio = bybit_spot.get_portfolio_value_usdt()
        total = portfolio.get("total_usdt", 0)
    except Exception:
        total = 0

    daily_estimates = {}
    monthly_estimates = {}
    for asset, pct in DCA.daily_pct_per_asset.items():
        daily = total * pct
        daily_estimates[asset] = round(daily, 2)
        monthly_estimates[asset] = round(daily * 30, 2)

    # 누적 현황
    try:
        pending = db.get_all_dca_pending()
    except Exception:
        pending = {}

    return {
        "current_total_value_usdt": round(total, 2),
        "daily_pct_per_asset": DCA.daily_pct_per_asset,
        "daily_buy_estimate_usd": daily_estimates,
        "monthly_buy_estimate_usd": monthly_estimates,
        "total_daily_pct": round(sum(DCA.daily_pct_per_asset.values()) * 100, 3),
        "total_monthly_pct": round(sum(DCA.daily_pct_per_asset.values()) * 30 * 100, 1),
        "multiplier_range": [DCA.multiplier_min, DCA.multiplier_max],
        "min_order_usdt": DCA.min_order_usdt,
        "pending_accumulation": pending,
        "note": "추가 입금 시 자동 ↑. min 미달 시 누적 후 도달하면 매수.",
    }
