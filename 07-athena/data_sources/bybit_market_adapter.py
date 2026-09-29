"""Bybit 시장 데이터 어댑터 (ATHENA용 정제 인터페이스).

bybit_spot_client는 raw API.
이 어댑터는 LLM에게 줄 컨텍스트로 정제.
"""

from typing import Optional, Dict, Any, List

from exchange import bybit_spot
from config import ATHENA, get_logger

logger = get_logger("bybit_market")


def get_market_snapshot(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """ATHENA 자산들의 현재 시장 상태.

    Returns:
        {
          "BTCUSDT": {
            "price": 97500.0,
            "change_24h_pct": 1.2,
            "volume_24h_usd": 12000000000,
            "high_24h": 98200,
            "low_24h": 96800,
          },
          ...
        }
    """
    if symbols is None:
        symbols = [ATHENA.SYMBOLS[a] for a in ATHENA.ALLOWED_ASSETS if a != "USDT"]

    result = {}
    for symbol in symbols:
        try:
            ticker = bybit_spot.get_ticker(symbol)
            if not ticker:
                continue
            result[symbol] = {
                "price": float(ticker.get("lastPrice", 0)),
                "change_24h_pct": float(ticker.get("price24hPcnt", 0)) * 100,
                "volume_24h_usd": float(ticker.get("turnover24h", 0)),
                "high_24h": float(ticker.get("highPrice24h", 0)),
                "low_24h": float(ticker.get("lowPrice24h", 0)),
            }
        except Exception as e:
            logger.error(f"{symbol} ticker 실패: {e}")

    return result


def get_ohlcv_summary(symbol: str = "BTCUSDT") -> Optional[Dict[str, Any]]:
    """4H 캔들 기반 단순 컨텍스트.

    Returns:
        {
          "current_price": 97500,
          "change_4h_pct": 0.5,
          "change_24h_pct": 1.2,
          "change_7d_pct": -2.0,
          "atr_pct": 1.8,
          "trend": "up" / "down" / "sideways",
        }
    """
    try:
        candles_4h = bybit_spot.get_kline(symbol, interval="240", limit=50)
        if len(candles_4h) < 10:
            return None

        current = candles_4h[-1]["close"]
        prev_4h = candles_4h[-2]["close"]
        prev_24h = candles_4h[-7]["close"] if len(candles_4h) >= 7 else current
        prev_7d = candles_4h[-43]["close"] if len(candles_4h) >= 43 else current

        # 단순 ATR (마지막 14개 4H 캔들의 (high-low)/close 평균)
        recent = candles_4h[-14:]
        atr_pct = sum((c["high"] - c["low"]) / c["close"] for c in recent) / 14 * 100

        # 단순 추세 (최근 5개 4H의 종가 기울기)
        last5 = [c["close"] for c in candles_4h[-5:]]
        slope = (last5[-1] - last5[0]) / last5[0] * 100
        if slope > 1:
            trend = "up"
        elif slope < -1:
            trend = "down"
        else:
            trend = "sideways"

        return {
            "current_price": current,
            "change_4h_pct": (current - prev_4h) / prev_4h * 100,
            "change_24h_pct": (current - prev_24h) / prev_24h * 100,
            "change_7d_pct": (current - prev_7d) / prev_7d * 100,
            "atr_pct": atr_pct,
            "trend": trend,
        }
    except Exception as e:
        logger.error(f"{symbol} OHLCV summary 실패: {e}")
        return None
