"""yfinance — 거시 지표 (DXY, SPX, Gold).

무료, 무인증. pip install yfinance
"""

from typing import Dict, Any, Optional

from config import DATA_SOURCES, get_logger

logger = get_logger("yf")


def get_macro_snapshot() -> Optional[Dict[str, Any]]:
    """DXY, SPX, Gold 현재 + 최근 변화율.

    Returns:
        {
          "DXY": {"price": 104.5, "change_24h_pct": 0.3, "change_7d_pct": -0.8},
          "SPX": {...},
          "GOLD": {...},
        }
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance 미설치 — pip install yfinance")
        return None

    try:
        result = {}
        # settings.py에 정의된 ticker 사용
        macro_tickers = [
            (DATA_SOURCES.DXY_TICKER, "DXY"),
            (DATA_SOURCES.SPX_TICKER, "SPX"),
            (DATA_SOURCES.GOLD_TICKER, "GOLD"),
        ]

        for ticker, label in macro_tickers:
            t = yf.Ticker(ticker)
            hist = t.history(period="1mo", interval="1d")
            if hist.empty:
                continue

            current = float(hist["Close"].iloc[-1])
            day_ago = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
            week_ago = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else current

            result[label] = {
                "price": current,
                "change_24h_pct": (current - day_ago) / day_ago * 100,
                "change_7d_pct": (current - week_ago) / week_ago * 100,
            }
        return result
    except Exception as e:
        logger.error(f"macro snapshot 실패: {e}")
        return None


if __name__ == "__main__":
    print(get_macro_snapshot())
