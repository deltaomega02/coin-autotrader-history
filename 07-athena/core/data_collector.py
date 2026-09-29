"""ATHENA 데이터 수집기.

모든 무료 API 어댑터를 호출하여 AI에게 줄 통합 컨텍스트 생성.
"""

from typing import Dict, Any
from datetime import datetime, timezone

from data_sources import (
    bybit_market_adapter,
    coinalyze_adapter,
    fear_greed_adapter,
    yfinance_adapter,
    etf_flow_adapter,        # bitbo.io 기반 (Farside 대체)
    reddit_adapter,
    news_adapter,            # 8개 RSS 통합
    defillama_adapter,
)
from config import get_logger

logger = get_logger("collector")


def collect_all() -> Dict[str, Any]:
    """모든 데이터 소스 호출 → AI 컨텍스트 dict.

    실패한 소스는 None 또는 빈 값. AI가 부분 데이터로도 결정 가능.
    """
    logger.info("데이터 수집 시작...")
    snapshot = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "market": {},
        "macro": None,
        "sentiment": {},
        "etf_flow": None,
        "social": None,
        "news": None,
        "defi": None,
    }

    # 1. Bybit 시장 데이터 (필수)
    try:
        snapshot["market"]["tickers"] = bybit_market_adapter.get_market_snapshot()
        snapshot["market"]["btc_summary"] = bybit_market_adapter.get_ohlcv_summary("BTCUSDT")
        snapshot["market"]["eth_summary"] = bybit_market_adapter.get_ohlcv_summary("ETHUSDT")
    except Exception as e:
        logger.error(f"Bybit 시장 데이터 실패: {e}")

    # 2. Coinalyze (펀딩/OI/청산)
    try:
        snapshot["market"]["btc_funding"] = coinalyze_adapter.get_funding_rates("BTCUSDT_PERP.A")
        snapshot["market"]["btc_liquidations_24h"] = coinalyze_adapter.get_liquidations_24h("BTC")
    except Exception as e:
        logger.warning(f"Coinalyze 실패: {e}")

    # 3. F&G
    try:
        snapshot["sentiment"]["fear_greed"] = fear_greed_adapter.get_current()
    except Exception as e:
        logger.warning(f"F&G 실패: {e}")

    # 4. 거시 (DXY/SPX/Gold)
    try:
        snapshot["macro"] = yfinance_adapter.get_macro_snapshot()
    except Exception as e:
        logger.warning(f"Macro 실패: {e}")

    # 5. ETF 자금 흐름 (2026 핵심 신호) — bitbo.io
    try:
        snapshot["etf_flow"] = etf_flow_adapter.get_summary(7)
    except Exception as e:
        logger.warning(f"ETF flow 실패: {e}")

    # 6. Reddit sentiment
    try:
        snapshot["social"] = reddit_adapter.get_sentiment_summary("Bitcoin", 25)
    except Exception as e:
        logger.warning(f"Reddit 실패: {e}")

    # 7. 뉴스 (8개 매체 RSS 통합 → BTC 필터)
    try:
        snapshot["news"] = news_adapter.get_news_summary(hours=24)
    except Exception as e:
        logger.warning(f"News 실패: {e}")

    # 8. DeFi TVL (시장 광범위 신호)
    try:
        snapshot["defi"] = defillama_adapter.get_chain_tvl_summary()
    except Exception as e:
        logger.warning(f"DefiLlama 실패: {e}")

    n_collected = sum(1 for v in snapshot.values() if v not in (None, {}, []))
    logger.info(f"데이터 수집 완료 ({n_collected}/8 카테고리 성공)")

    return snapshot
