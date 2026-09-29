"""ATHENA 포트폴리오 매니저 (코드).

AI Manager의 target_weights를 받아 실제 주문으로 변환.
페이퍼 모드와 실전 모드 분기.
"""

from typing import Dict, Any, List

from exchange import bybit_spot
from exchange.bybit_spot_client import BybitSpotError
from core import cost_basis_tracker
from config import ATHENA, SAFETY, get_logger

logger = get_logger("portfolio")


def compute_rebalance_orders(
    current_weights: Dict[str, float],
    target_weights: Dict[str, float],
    total_value_usdt: float,
) -> List[Dict[str, Any]]:
    """비중 차이 → 주문 리스트.

    Returns:
        [
          {"asset": "BTC", "side": "Sell", "value_usdt": 100.0, "symbol": "BTCUSDT"},
          {"asset": "ETH", "side": "Buy", "value_usdt": 100.0, "symbol": "ETHUSDT"},
        ]
    """
    orders = []

    for asset in ATHENA.ALLOWED_ASSETS:
        if asset == "USDT":
            continue  # USDT는 다른 거래의 결과로 자동 조정

        target_value = total_value_usdt * target_weights.get(asset, 0)
        current_value = total_value_usdt * current_weights.get(asset, 0)
        delta = target_value - current_value

        if total_value_usdt <= 0:
            continue
        if abs(delta) / total_value_usdt < SAFETY.MIN_REBALANCE_THRESHOLD:
            continue  # 0.5% 미만 무시 (수수료 비효율)

        symbol = ATHENA.SYMBOLS.get(asset)
        if not symbol:
            continue

        if delta > 0:
            orders.append({
                "asset": asset,
                "side": "Buy",
                "value_usdt": delta,
                "symbol": symbol,
            })
        else:
            orders.append({
                "asset": asset,
                "side": "Sell",
                "value_usdt": abs(delta),
                "symbol": symbol,
            })

    # 매도 먼저 (USDT 확보), 매수 나중
    orders.sort(key=lambda o: 0 if o["side"] == "Sell" else 1)
    return orders


def execute_orders(orders: List[Dict[str, Any]],
                   paper_mode: bool = True) -> List[Dict[str, Any]]:
    """주문 실행.

    Args:
        paper_mode: True면 가상 (DB 기록만)

    Returns:
        체결 결과 리스트
    """
    results = []

    for order in orders:
        # 가격 조회 (paper/live 모두 필요)
        try:
            ticker = bybit_spot.get_ticker(order["symbol"])
            price = float(ticker.get("lastPrice", 0) or 0)
        except Exception:
            price = 0

        if price <= 0:
            logger.error(f"가격 조회 실패 {order['symbol']} — 주문 스킵")
            results.append({**order, "executed": False, "error": "price_fetch_failed"})
            continue

        qty = order["value_usdt"] / price

        # 최소 수량 체크
        min_qty = ATHENA.MIN_ORDER_QTYS.get(order["asset"], 0)
        if qty < min_qty:
            logger.warning(f"{order['asset']} 수량 {qty} < min {min_qty} — 스킵")
            results.append({**order, "executed": False, "error": "below_min_qty",
                          "qty": qty, "price": price})
            continue

        # 정밀도 적용
        precision = ATHENA.QTY_PRECISIONS.get(order["asset"], 6)
        qty = round(qty, precision)

        if paper_mode:
            logger.info(
                f"[PAPER] {order['side']} {order['asset']} "
                f"~${order['value_usdt']:.2f} @ ${price:.2f} = {qty}"
            )
            # 평단가 추적 (페이퍼도)
            try:
                if order["side"] == "Buy":
                    cost_basis_tracker.record_buy(order["asset"], qty, price)
                else:
                    cost_basis_tracker.record_sell(order["asset"], qty, price)
            except Exception as e:
                logger.error(f"평단가 갱신 실패: {e}")

            results.append({
                **order,
                "executed": True,
                "paper": True,
                "price": price,
                "qty": qty,
            })
        else:
            try:
                if order["side"] == "Buy":
                    # Bybit Spot quoteCoin: USDT 금액 2자리까지 (소수점 제한)
                    quote_amt = round(order["value_usdt"], 2)
                    resp = bybit_spot.place_market_buy(
                        symbol=order["symbol"],
                        quote_qty=quote_amt,
                    )
                else:
                    resp = bybit_spot.place_market_sell(
                        symbol=order["symbol"],
                        base_qty=qty,  # 이미 위에서 round 적용됨
                    )

                logger.info(f"[LIVE] {order['side']} {order['asset']} "
                          f"order_id={resp.get('orderId')}")
                # 평단가 갱신 (LIVE)
                try:
                    if order["side"] == "Buy":
                        cost_basis_tracker.record_buy(order["asset"], qty, price)
                    else:
                        cost_basis_tracker.record_sell(order["asset"], qty, price)
                except Exception as e:
                    logger.error(f"평단가 갱신 실패: {e}")

                results.append({
                    **order,
                    "executed": True,
                    "paper": False,
                    "price": price,
                    "qty": qty,
                    "order_id": resp.get("orderId"),
                })
            except BybitSpotError as e:
                logger.error(f"주문 실패 {order}: {e}")
                results.append({**order, "executed": False, "error": str(e),
                              "qty": qty, "price": price})

    return results
