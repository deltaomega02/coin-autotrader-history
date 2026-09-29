"""Alternative.me Fear & Greed Index — 무료, 무인증.

API: https://api.alternative.me/fng/
응답: {"data": [{"value": "32", "value_classification": "Fear", "timestamp": "..."}], ...}
"""

import requests
from typing import Optional, Dict, Any

from config import DATA_SOURCES, get_logger

logger = get_logger("fg")


def get_current() -> Optional[Dict[str, Any]]:
    """현재 F&G 지수.

    Returns:
        {"value": int 0-100, "label": str, "timestamp": int}
    """
    try:
        r = requests.get(DATA_SOURCES.FG_API, timeout=10)
        r.raise_for_status()
        data = r.json()["data"][0]
        return {
            "value": int(data["value"]),
            "label": data["value_classification"],  # "Extreme Fear" / "Fear" / "Neutral" / "Greed" / "Extreme Greed"
            "timestamp": int(data["timestamp"]),
        }
    except Exception as e:
        logger.error(f"F&G fetch 실패: {e}")
        return None


def get_history(limit: int = 30) -> Optional[list]:
    """F&G 과거 N일."""
    try:
        r = requests.get(f"{DATA_SOURCES.FG_API}?limit={limit}", timeout=10)
        r.raise_for_status()
        return [
            {
                "value": int(d["value"]),
                "label": d["value_classification"],
                "timestamp": int(d["timestamp"]),
            }
            for d in r.json()["data"]
        ]
    except Exception as e:
        logger.error(f"F&G history 실패: {e}")
        return None


if __name__ == "__main__":
    # 테스트
    print(get_current())
