"""DefiLlama API — DeFi TVL.

무료, 무인증.
Docs: https://api-docs.defillama.com/
"""

import requests
from typing import Optional, Dict, Any

from config import DATA_SOURCES, get_logger

logger = get_logger("defillama")


def get_total_tvl() -> Optional[float]:
    """전체 DeFi TVL (USD)."""
    try:
        r = requests.get(f"{DATA_SOURCES.DEFILLAMA_BASE}/v2/historicalChainTvl",
                        timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[-1]["tvl"])
    except Exception as e:
        logger.error(f"DefiLlama TVL 실패: {e}")
        return None


def get_chain_tvl_summary() -> Optional[Dict[str, Any]]:
    """주요 체인별 TVL + 24h 변화."""
    try:
        r = requests.get(f"{DATA_SOURCES.DEFILLAMA_BASE}/v2/chains", timeout=15)
        r.raise_for_status()
        chains = r.json()

        # 상위 5개 체인
        top = sorted(chains, key=lambda c: c.get("tvl", 0), reverse=True)[:5]

        return {
            "top_chains": [
                {
                    "name": c.get("name"),
                    "tvl_usd": c.get("tvl"),
                    "change_1d_pct": c.get("change_1d", 0),
                    "change_7d_pct": c.get("change_7d", 0),
                }
                for c in top
            ],
            "total_tvl_usd": sum(c.get("tvl", 0) for c in chains),
        }
    except Exception as e:
        logger.error(f"DefiLlama chains 실패: {e}")
        return None


if __name__ == "__main__":
    print(get_chain_tvl_summary())
