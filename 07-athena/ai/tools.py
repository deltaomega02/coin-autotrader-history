"""ATHENA AI 도구 카탈로그.

Gemini 3.1 Pro Function Calling용 Python 함수.
공식 문서 (https://ai.google.dev/gemini-api/docs/function-calling):
- Python 함수 직접 전달
- type hints + docstring → 자동 schema 변환
- 타입: 기본 타입 (str, int, float, bool, list, dict)

핵심 원칙:
- 각 함수 짧고 명확한 docstring (AI가 도구 선택할 때 참조)
- 반환은 JSON 직렬화 가능한 dict/list
- 에러 시 {"error": "..."} 반환 (예외 raise X)
- AI가 같은 도구 반복 호출하지 않게 명확한 기능 분리
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger("tools")


# ────────────────────────────────────────────────────────────
# 시장 데이터 (Bybit)
# ────────────────────────────────────────────────────────────

def get_market_summary() -> Dict[str, Any]:
    """모든 ATHENA 자산(BTC/ETH/SOL)의 현재 시세 요약.

    Returns 24h 가격 변화, 거래량, 고가/저가.
    이 도구를 가장 먼저 호출해서 시장 전체 상황을 파악하세요.
    """
    try:
        from data_sources import bybit_market_adapter
        return bybit_market_adapter.get_market_snapshot() or {}
    except Exception as e:
        logger.error(f"get_market_summary: {e}")
        return {"error": str(e)}


def get_price_action(symbol: str) -> Dict[str, Any]:
    """특정 자산의 가격 추세 분석 (4H/1D).

    Args:
        symbol: "BTCUSDT", "ETHUSDT", "SOLUSDT" 중 하나

    Returns 현재가, 4H/24H/7D 변화율, ATR%, 추세 방향.
    """
    try:
        from data_sources import bybit_market_adapter
        result = bybit_market_adapter.get_ohlcv_summary(symbol)
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


def get_orderbook_depth(symbol: str) -> Dict[str, Any]:
    """현재 호가 두께 (매수/매도 압력).

    Args:
        symbol: "BTCUSDT" 등

    Returns 매수벽/매도벽 비율. 큰 매수벽 = 단기 지지, 매도벽 = 저항.
    """
    try:
        from exchange import bybit_spot
        ob = bybit_spot.get_orderbook(symbol, limit=25)
        if not ob:
            return {"error": "no_data"}

        bids = ob.get("b", [])
        asks = ob.get("a", [])
        bid_total = sum(float(b[1]) for b in bids[:10])
        ask_total = sum(float(a[1]) for a in asks[:10])
        total = bid_total + ask_total
        return {
            "bid_ratio": round(bid_total / total, 3) if total else 0.5,
            "ask_ratio": round(ask_total / total, 3) if total else 0.5,
            "bid_volume_top10": round(bid_total, 2),
            "ask_volume_top10": round(ask_total, 2),
        }
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# 시장 미시구조 (펀딩 / OI / 청산)
# ────────────────────────────────────────────────────────────

def get_funding_rates() -> Dict[str, Any]:
    """다중거래소 BTC 영구 선물 펀딩비.

    높은 양수 = 롱 과열 (반전 위험), 음수 = 숏 과열 (역반등 가능).
    """
    try:
        from data_sources import coinalyze_adapter
        result = coinalyze_adapter.get_funding_rates("BTCUSDT_PERP.A")
        return {"funding": result} if result else {"error": "no_data_or_no_api_key"}
    except Exception as e:
        return {"error": str(e)}


def get_liquidations_24h() -> Dict[str, Any]:
    """BTC 24시간 청산 데이터 (long/short 분리).

    한쪽 청산 폭증 = 반대 방향 진입 신호 (역사적).
    """
    try:
        from data_sources import coinalyze_adapter
        result = coinalyze_adapter.get_liquidations_24h("BTC")
        return {"liquidations": result} if result else {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# 자금 흐름 / 거시
# ────────────────────────────────────────────────────────────

def get_etf_flow(days: int = 7) -> Dict[str, Any]:
    """BTC 현물 ETF 일별 순자금 흐름 (BlackRock IBIT 등).

    Args:
        days: 최근 N일 (1-14)

    +값 = 기관 매수, -값 = 기관 매도.
    2024 ETF 승인 후 BTC 가격의 가장 강한 구조적 신호.
    """
    try:
        from data_sources import etf_flow_adapter
        result = etf_flow_adapter.get_summary(min(days, 14))
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


def get_macro_indicators() -> Dict[str, Any]:
    """거시 지표: DXY (달러), SPX (S&P 500), Gold.

    DXY 상승 = BTC 약세 (역상관 21-27배).
    SPX 상관 = 0.3 (점차 약해짐).
    """
    try:
        from data_sources import yfinance_adapter
        result = yfinance_adapter.get_macro_snapshot()
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


def get_fear_greed_index() -> Dict[str, Any]:
    """비트코인 공포-탐욕 지수 (0-100).

    < 25 = 극단 공포 (역사적 매수 구간)
    > 75 = 극단 탐욕 (역사적 조정 임박)
    """
    try:
        from data_sources import fear_greed_adapter
        result = fear_greed_adapter.get_current()
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# 뉴스 / 소셜
# ────────────────────────────────────────────────────────────

def search_news(hours: int = 24, query: str = "") -> Dict[str, Any]:
    """최근 N시간 뉴스 검색 (8개 매체 통합).

    **사용 시점 (중요)**:
    - 평소엔 호출하지 않음 (차트/ETF/사이클이 메인)
    - 다음 경우만 호출:
      1. 가격 이상 움직임 발견 ("왜 이런 변동?")
      2. 사이클 지표 모순 ("Pi Cycle은 정상인데 거래량 폭증?")
      3. 위기 상황 의심 (해킹/규제 키워드 확인)
      4. 거시 이벤트 일정 확인 (FOMC, CPI 등)

    Args:
        hours: 1-72 시간 윈도우
        query: 키워드 필터 (선택). 비워두면 BTC 전체.
               예: "FOMC", "hack", "Fed", "BlackRock", "regulation", "ETF"

    효율적 사용 예시:
        search_news(hours=12, query="FOMC")  # FOMC 관련 최근 12h
        search_news(hours=6, query="hack")   # 해킹 뉴스 최근 6h
    """
    try:
        from data_sources import news_adapter
        result = news_adapter.get_news_summary(hours=min(hours, 72), query=query)
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


def get_reddit_sentiment() -> Dict[str, Any]:
    """r/Bitcoin 인기 게시물 sentiment (24h).

    상위 게시물 제목, 평균 upvote ratio, 고참여 게시물.
    급격한 sentiment 변화 = 시장 변곡점 신호.
    """
    try:
        from data_sources import reddit_adapter
        result = reddit_adapter.get_sentiment_summary("Bitcoin", 25)
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# DeFi
# ────────────────────────────────────────────────────────────

def get_defi_tvl() -> Dict[str, Any]:
    """주요 체인별 TVL (Total Value Locked).

    DeFi 자금 유입/유출은 위험자산 선호도 지표.
    급격한 TVL 감소 = 시장 위험 회피.
    """
    try:
        from data_sources import defillama_adapter
        result = defillama_adapter.get_chain_tvl_summary()
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# 사이클 위치 (학술 검증된 BTC 사이클 지표)
# ────────────────────────────────────────────────────────────

def get_pi_cycle_status() -> Dict[str, Any]:
    """Pi Cycle Top Indicator (BTC 일봉 SMA 기반).

    111일 SMA가 350일 SMA × 2 위로 가면 시장 정점 신호.
    역사적 적중: 2013, 2017, 2021-04. 매도/방어 신호의 기본.
    """
    try:
        from data_sources import cycle_indicators
        return cycle_indicators.get_pi_cycle_status()
    except Exception as e:
        return {"error": str(e)}


def get_mvrv_z_score() -> Dict[str, Any]:
    """MVRV Z-Score (시장가치 vs 실현가치 표준화).

    > 7: 극단 정점 (매도)
    > 4: 정점 영역
    < 0: 바닥 영역 (매수)
    < -0.5: 극단 바닥 (적극 매수)
    역사적으로 정확한 사이클 지표.
    """
    try:
        from data_sources import cycle_indicators
        return cycle_indicators.get_mvrv_z_score()
    except Exception as e:
        return {"error": str(e)}


def get_cycle_position_score() -> Dict[str, Any]:
    """종합 BTC 사이클 위치 (0-100).

    Pi Cycle + MVRV 가중 조합:
    0-20: EXTREME_BOTTOM (매수 가속)
    20-40: ACCUMULATION (DCA 가속)
    40-60: NEUTRAL (DCA 평소)
    60-80: OVERHEATED (DCA 줄임)
    80-100: EXTREME_TOP (DCA 정지 + 일부 USDT)

    한 번 호출로 핵심 사이클 정보 종합 → AI 판단 빠름.
    """
    try:
        from data_sources import cycle_indicators
        return cycle_indicators.get_cycle_position_score()
    except Exception as e:
        return {"error": str(e)}


def get_dca_status() -> Dict[str, Any]:
    """현재 DCA 설정 (시드 % 기반 동적).

    AI는 multiplier (0.0-2.0)만 결정.
    매수액 = 총자산 × daily_pct × multiplier (자동 계산).
    추가 입금 시 자동 ↑.
    """
    try:
        from core.dca_engine import get_dca_summary
        return get_dca_summary()
    except Exception as e:
        return {"error": str(e)}


def get_cost_basis() -> Dict[str, Any]:
    """평단가 (avg cost) + 미실현 손익 + 실현 PnL.

    AI 활용:
    - 현재가 vs 평단가 비교 → "지금 비싼가 싼가" 객관 판단
    - vs_avg_pct > +30%: 일부 익절 검토
    - vs_avg_pct < -10%: DCA 가속 (평단가 낮춤)
    - vs_avg_pct ≈ 0%: 평소
    """
    try:
        from core import cost_basis_tracker
        from data_sources import bybit_market_adapter

        snapshot = bybit_market_adapter.get_market_snapshot() or {}
        prices = {
            "BTC": snapshot.get("BTCUSDT", {}).get("price", 0),
            "ETH": snapshot.get("ETHUSDT", {}).get("price", 0),
            "SOL": snapshot.get("SOLUSDT", {}).get("price", 0),
        }
        return cost_basis_tracker.get_all_cost_basis_with_pnl(prices)
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# 자기 인식 (포트폴리오 / 이력)
# ────────────────────────────────────────────────────────────

def get_my_portfolio() -> Dict[str, Any]:
    """현재 포트폴리오 상태.

    Returns 총자산 (USDT), 자산별 비중, 자산별 USD 가치.
    리밸런싱 결정 전 반드시 호출.
    """
    try:
        from exchange import bybit_spot
        result = bybit_spot.get_portfolio_value_usdt()
        return result or {"error": "no_data"}
    except Exception as e:
        return {"error": str(e)}


def get_recent_decisions(days: int = 7) -> Dict[str, Any]:
    """최근 N일 ATHENA 결정 이력.

    Args:
        days: 1-14

    Returns 시점별 결정 (regime, confidence, target_weights, reasoning).
    같은 결정 반복 방지 + 일관성 확인.
    """
    try:
        from database import db
        rows = db.get_recent_decisions(days=min(days, 14))
        # 핵심 정보만 추려서 반환 (토큰 절약)
        import json
        compact = []
        for r in rows[:10]:  # 최대 10건
            try:
                manager = json.loads(r.get("manager_json", "{}")) if r.get("manager_json") else {}
                compact.append({
                    "timestamp": r["timestamp"],
                    "confidence": r.get("confidence"),
                    "regime": r.get("regime"),
                    "target_weights": manager.get("target_weights"),
                    "reasoning_brief": (manager.get("reasoning") or "")[:150],
                })
            except (json.JSONDecodeError, TypeError):
                continue
        return {"count": len(compact), "decisions": compact}
    except Exception as e:
        return {"error": str(e)}


def get_lessons() -> Dict[str, Any]:
    """학습된 교훈 (lessons.md).

    Returns 검증된 교훈 텍스트 (주 1회 자동 갱신).
    매 결정 시 참조 (안티패턴 회피).
    """
    try:
        from core import lessons_keeper
        text = lessons_keeper.read_lessons()
        if not text:
            return {"lessons": "", "note": "초기 운영 — 학습된 교훈 없음"}
        # 토큰 절약: 최근 8000자만
        return {"lessons": text[-8000:] if len(text) > 8000 else text}
    except Exception as e:
        return {"error": str(e)}


# ────────────────────────────────────────────────────────────
# 도구 카탈로그 (Gemini에 전달)
# ────────────────────────────────────────────────────────────

ALL_TOOLS = [
    # 시장 (가장 먼저 호출 권장)
    get_market_summary,
    get_price_action,
    get_orderbook_depth,

    # 미시구조
    get_funding_rates,
    get_liquidations_24h,

    # 자금/거시
    get_etf_flow,
    get_macro_indicators,
    get_fear_greed_index,

    # 뉴스/소셜
    search_news,
    get_reddit_sentiment,

    # DeFi
    get_defi_tvl,

    # 사이클 위치 (학술 검증)
    get_pi_cycle_status,
    get_mvrv_z_score,
    get_cycle_position_score,

    # DCA 상태 + 평단가
    get_dca_status,
    get_cost_basis,

    # 자기 인식 (결정 직전)
    get_my_portfolio,
    get_recent_decisions,
    get_lessons,
]


TOOL_NAMES = [t.__name__ for t in ALL_TOOLS]
