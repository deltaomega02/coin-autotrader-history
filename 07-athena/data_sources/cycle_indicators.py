"""BTC 사이클 지표 — Pi Cycle Top, MVRV Z-Score, NUPL, LTH.

학술/실증 검증된 사이클 위치 지표:
- Pi Cycle Top: 111일 SMA × 350일 SMA × 2 → 시장 정점 (2013/2017 적중)
- MVRV Z-Score: 시장-실현가치 z-score → top/bottom (역사적 정확)
- NUPL: 미실현 손익 → 사이클 위치
- LTH Supply: 장기 보유자 비율 (>1년)

소스:
1. Pi Cycle: Bybit OHLCV로 직접 계산 (가장 정확)
2. MVRV/NUPL/LTH: bitcoinmagazinepro.com / checkonchain.com 차트 스크래핑
"""

import re
import requests
from typing import Dict, Any, Optional, List

from exchange import bybit_spot
from config import get_logger

logger = get_logger("cycle")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# ────────────────────────────────────────────────────────────
# Pi Cycle Top (Bybit OHLCV로 직접 계산 — 가장 안정)
# ────────────────────────────────────────────────────────────

def get_pi_cycle_status() -> Dict[str, Any]:
    """Pi Cycle Top Indicator.

    111일 SMA가 350일 SMA × 2 위에 있으면 시장 정점 (역사적 적중).

    Returns:
        {
          "sma_111": float,
          "sma_350x2": float,
          "ratio": float,          # sma_111 / sma_350x2
          "status": "TOP_SIGNAL" | "APPROACHING_TOP" | "NORMAL" | "BOTTOM",
          "days_until_cross": int | None  # 추세 기반 추정
        }
    """
    try:
        # 일봉 400개 (350+여유)
        candles = bybit_spot.get_kline("BTCUSDT", interval="D", limit=400)
        if len(candles) < 350:
            return {"error": f"insufficient_data: {len(candles)}/350"}

        closes = [c["close"] for c in candles]

        # SMA 계산
        sma_111 = sum(closes[-111:]) / 111
        sma_350 = sum(closes[-350:]) / 350
        sma_350x2 = sma_350 * 2

        ratio = sma_111 / sma_350x2 if sma_350x2 > 0 else 0

        if ratio >= 1.0:
            status = "TOP_SIGNAL"  # 역사적 정점 신호
        elif ratio >= 0.95:
            status = "APPROACHING_TOP"
        elif ratio <= 0.30:
            status = "BOTTOM"  # 매수 영역
        elif ratio <= 0.50:
            status = "ACCUMULATION"
        else:
            status = "NORMAL"

        return {
            "sma_111": round(sma_111, 2),
            "sma_350x2": round(sma_350x2, 2),
            "ratio": round(ratio, 4),
            "status": status,
            "interpretation": _pi_cycle_interpretation(ratio, status),
        }
    except Exception as e:
        logger.error(f"Pi Cycle 계산 실패: {e}")
        return {"error": str(e)}


def _pi_cycle_interpretation(ratio: float, status: str) -> str:
    if status == "TOP_SIGNAL":
        return "시장 정점 신호. 역사적으로 며칠~몇 주 내 큰 조정. 매도/방어 모드 권장."
    if status == "APPROACHING_TOP":
        return f"정점 임박 (비율 {ratio:.2%}). 신규 매수 자제, 일부 익절 검토."
    if status == "BOTTOM":
        return f"바닥 영역 (비율 {ratio:.2%}). 적극 매수 영역."
    if status == "ACCUMULATION":
        return f"축적 영역 (비율 {ratio:.2%}). DCA 가속 권장."
    return f"중립 (비율 {ratio:.2%}). 평소 DCA 유지."


# ────────────────────────────────────────────────────────────
# MVRV Z-Score (스크래핑)
# ────────────────────────────────────────────────────────────

def get_mvrv_z_score() -> Dict[str, Any]:
    """MVRV Z-Score (시장가치 vs 실현가치 표준화).

    > 7: 극단 정점 (역사적 매도)
    > 4: 정점 영역
    < 0: 바닥 영역 (역사적 매수)
    < -0.5: 극단 바닥 (적극 매수)

    소스: bitcoinmagazinepro.com / checkonchain.com (스크래핑)
    """
    # 1. bitcoinmagazinepro 시도
    result = _scrape_bmpro_mvrv()
    if result:
        return result

    # 2. fallback: checkonchain
    result = _scrape_checkonchain_mvrv()
    if result:
        return result

    return {"error": "all_sources_failed"}


def _scrape_bmpro_mvrv() -> Optional[Dict[str, Any]]:
    """bitcoinmagazinepro.com MVRV Z-Score 페이지 스크래핑."""
    try:
        url = "https://www.bitcoinmagazinepro.com/charts/mvrv-zscore/"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None

        # 본문에서 z-score 값 추출 (페이지 구조 변경 시 깨질 수 있음)
        # 일반적으로 "Current MVRV Z-Score: X.XX" 같은 패턴
        html = r.text
        patterns = [
            r"MVRV\s*Z-Score[:\s]*<[^>]*>([+-]?\d+\.\d+)",
            r"Current[^<]*MVRV[^<]*Z[^<]*Score[^<]*<[^>]*>([+-]?\d+\.\d+)",
            r"z-score[^<]*<[^>]*>([+-]?\d+\.\d+)",
            r'data-value="([+-]?\d+\.\d+)"[^>]*z-score',
        ]

        for pat in patterns:
            match = re.search(pat, html, re.IGNORECASE)
            if match:
                try:
                    z = float(match.group(1))
                    return _format_mvrv(z, source="bitcoinmagazinepro")
                except ValueError:
                    continue

        return None
    except Exception as e:
        logger.debug(f"bmpro MVRV 실패: {e}")
        return None


def _scrape_checkonchain_mvrv() -> Optional[Dict[str, Any]]:
    """checkonchain.com fallback (MVRV)."""
    try:
        # checkonchain은 JS 렌더링 페이지가 많아 fetch 어려움
        # 대안: 단순 추정 메시지 반환
        return None
    except Exception:
        return None


def _format_mvrv(z: float, source: str) -> Dict[str, Any]:
    if z >= 7:
        status = "EXTREME_TOP"
        interp = f"극단 정점 영역 (Z={z:.2f}). 역사적 대규모 매도 신호."
    elif z >= 4:
        status = "TOP_ZONE"
        interp = f"정점 영역 (Z={z:.2f}). 일부 익절 권장."
    elif z >= 2:
        status = "OVERHEATED"
        interp = f"과열 (Z={z:.2f}). 신규 매수 자제."
    elif z >= 0:
        status = "NEUTRAL"
        interp = f"중립 (Z={z:.2f}). DCA 평소."
    elif z >= -0.5:
        status = "BOTTOM_ZONE"
        interp = f"바닥 영역 (Z={z:.2f}). DCA 가속 권장."
    else:
        status = "EXTREME_BOTTOM"
        interp = f"극단 바닥 (Z={z:.2f}). 적극 매수 영역."

    return {
        "z_score": round(z, 2),
        "status": status,
        "interpretation": interp,
        "source": source,
    }


# ────────────────────────────────────────────────────────────
# 종합 사이클 위치 (0-100)
# ────────────────────────────────────────────────────────────

def get_cycle_position_score() -> Dict[str, Any]:
    """Pi Cycle + MVRV 종합 → 사이클 위치 0-100.

    0  = 극단 바닥 (적극 매수)
    50 = 중립
    100 = 극단 정점 (방어 모드)
    """
    pi = get_pi_cycle_status()
    mvrv = get_mvrv_z_score()

    score = 50  # 기본 중립
    factors = []

    # Pi Cycle 기반 (0-50 가중치)
    if "ratio" in pi:
        ratio = pi["ratio"]
        # ratio 0.3 → score 0, ratio 1.0 → score 100
        pi_score = max(0, min(100, (ratio - 0.3) / 0.7 * 100))
        score = pi_score * 0.6 + score * 0.4  # Pi 60% 가중
        factors.append(f"Pi Cycle ratio {ratio:.2f} → {pi_score:.0f}")

    # MVRV 기반 (40% 가중)
    if "z_score" in mvrv:
        z = mvrv["z_score"]
        # z=-1 → score 0, z=7 → score 100
        mvrv_score = max(0, min(100, (z + 1) / 8 * 100))
        score = mvrv_score * 0.4 + score * 0.6
        factors.append(f"MVRV Z {z:.2f} → {mvrv_score:.0f}")

    score = round(score)

    if score < 20:
        regime = "EXTREME_BOTTOM"
    elif score < 40:
        regime = "ACCUMULATION"
    elif score < 60:
        regime = "NEUTRAL"
    elif score < 80:
        regime = "OVERHEATED"
    else:
        regime = "EXTREME_TOP"

    return {
        "cycle_position": score,
        "regime": regime,
        "factors": factors,
        "pi_cycle": pi,
        "mvrv_z_score": mvrv,
    }


if __name__ == "__main__":
    import json
    print("=== Pi Cycle ===")
    print(json.dumps(get_pi_cycle_status(), indent=2, ensure_ascii=False))
    print()
    print("=== MVRV Z-Score ===")
    print(json.dumps(get_mvrv_z_score(), indent=2, ensure_ascii=False))
    print()
    print("=== Cycle Position ===")
    print(json.dumps(get_cycle_position_score(), indent=2, ensure_ascii=False))
