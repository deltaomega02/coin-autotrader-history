"""Coinalyze — 다중거래소 펀딩/OI/청산 데이터.

무료 API: 40 calls/min, API key 등록 필요 (무료)
Docs: https://api.coinalyze.net/v1/doc/

History endpoints는 from/to UNIX timestamp 필수.
"""

import time
import requests
from typing import Optional, Dict, Any, List

from config import DATA_SOURCES, get_logger

logger = get_logger("coinalyze")


def _get(endpoint: str, params: Dict[str, Any] = None) -> Optional[Any]:
    """공통 GET 헬퍼."""
    if not DATA_SOURCES.COINALYZE_API_KEY:
        logger.warning("Coinalyze API key 미설정")
        return None

    try:
        url = f"{DATA_SOURCES.COINALYZE_BASE}/{endpoint}"
        headers = {"api_key": DATA_SOURCES.COINALYZE_API_KEY}
        r = requests.get(url, headers=headers, params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Coinalyze {endpoint} 실패: {e}")
        return None


def get_funding_rates(symbol: str = "BTCUSDT_PERP.A") -> Optional[List[Dict]]:
    """현재 펀딩비 (실시간, history 아님)."""
    return _get("funding-rate", {"symbols": symbol})


def get_open_interest(symbol: str = "BTCUSDT_PERP.A",
                      interval: str = "1hour",
                      hours: int = 24) -> Optional[List[Dict]]:
    """OI 시계열. from/to 타임스탬프 필수."""
    now = int(time.time())
    return _get("open-interest-history", {
        "symbols": symbol,
        "interval": interval,
        "from": now - hours * 3600,
        "to": now,
    })


def get_liquidations_24h(symbol: str = "BTC") -> Optional[Dict]:
    """24시간 청산 합계 (long/short)."""
    now = int(time.time())
    return _get("liquidation-history", {
        "symbols": f"{symbol}USDT_PERP.A",
        "interval": "1hour",
        "from": now - 24 * 3600,
        "to": now,
        "convert_to_usd": "true",
    })


def get_long_short_ratio(symbol: str = "BTCUSDT_PERP.A",
                        interval: str = "1hour",
                        hours: int = 24) -> Optional[List[Dict]]:
    """롱숏 비율."""
    now = int(time.time())
    return _get("long-short-ratio-history", {
        "symbols": symbol,
        "interval": interval,
        "from": now - hours * 3600,
        "to": now,
    })


if __name__ == "__main__":
    print("=== Funding ===")
    print(get_funding_rates())
    print("=== Liquidations ===")
    print(get_liquidations_24h("BTC"))
