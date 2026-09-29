"""Emergency Monitor — 24시간 가격 급락 감지 + 위기 키워드 감지.

평소엔 가벼운 polling (15분마다 BTC 가격 체크).
다음 발생 시 AI Guardian 즉시 호출:
- BTC 24h -10% 이상 (시장 급락)
- BTC 1h -5% 이상 (즉시 위기)
- 뉴스에 위기 키워드 (해킹/규제 발효 등)

평상시: 매우 저비용 (가격 체크만, AI 호출 X)
위기 시: AI 1회 즉시 호출
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from exchange import bybit_spot
from data_sources import news_adapter
from config import get_logger

logger = get_logger("emergency")


# 가격 급락 임계
PRICE_DROP_24H_PCT = 10.0   # 24시간 -10%
PRICE_DROP_1H_PCT = 5.0     # 1시간 -5%

# 위기 키워드 (뉴스)
CRISIS_KEYWORDS = [
    "hack", "exploit", "stolen",                      # 해킹 (drained 제거 — 일반 시장 기사 false positive)
    "ban", "banned", "shutdown", "closure",          # 규제
    "bankruptcy", "insolvent", "halts", "suspend",    # 거래소 위기
    "sec sues", "sec charges", "criminal",            # 법적
    "exchange collapse", "withdrawal halt",
    "rug pull", "exit scam",
]


def check_price_emergency() -> Optional[Dict[str, Any]]:
    """BTC 가격 급락 체크.

    Returns:
        None (정상) 또는 위기 dict
    """
    try:
        # 1H 캔들 25개 (24h + 여유)
        candles_1h = bybit_spot.get_kline("BTCUSDT", interval="60", limit=25)
        if len(candles_1h) < 25:
            return None

        current = candles_1h[-1]["close"]
        last_1h_open = candles_1h[-1]["open"]
        price_24h_ago = candles_1h[0]["close"]

        change_1h = (current - last_1h_open) / last_1h_open * 100 if last_1h_open else 0
        change_24h = (current - price_24h_ago) / price_24h_ago * 100 if price_24h_ago else 0

        if change_24h <= -PRICE_DROP_24H_PCT:
            return {
                "type": "PRICE_CRASH_24H",
                "severity": "HIGH",
                "current_price": current,
                "change_24h_pct": round(change_24h, 2),
                "message": f"BTC 24h {change_24h:.1f}% 급락 — AI 즉시 호출 권장",
            }

        if change_1h <= -PRICE_DROP_1H_PCT:
            return {
                "type": "PRICE_CRASH_1H",
                "severity": "MEDIUM",
                "current_price": current,
                "change_1h_pct": round(change_1h, 2),
                "message": f"BTC 1h {change_1h:.1f}% 급락 — AI 호출 권장",
            }

        return None
    except Exception as e:
        logger.error(f"가격 체크 실패: {e}")
        return None


# 처리한 title 24h dedupe — 같은 기사로 반복 트리거 방지 (AI 비용 폭주 차단)
# 영속화: 재시작 시에도 유지 (메모리 dict는 휘발됨)
import json as _json
from pathlib import Path as _Path

_DEDUPE_FILE = _Path(__file__).parent.parent / "logs" / "emergency_dedupe.json"
_DEDUPE_TTL = 24 * 3600  # 24시간


def _load_dedupe() -> Dict[str, float]:
    try:
        if _DEDUPE_FILE.exists():
            return _json.loads(_DEDUPE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_dedupe(data: Dict[str, float]) -> None:
    try:
        _DEDUPE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DEDUPE_FILE.write_text(_json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.warning(f"dedupe 저장 실패: {e}")


def _is_already_processed(title: str) -> bool:
    """24시간 내 이미 트리거된 title인지 확인. 영속 저장 + 자동 만료."""
    import hashlib
    key = hashlib.md5(title.lower().strip().encode()).hexdigest()[:16]
    now = datetime.now(timezone.utc).timestamp()

    data = _load_dedupe()
    # 만료된 항목 청소
    data = {k: ts for k, ts in data.items() if now - ts <= _DEDUPE_TTL}

    if key in data:
        _save_dedupe(data)  # 청소 결과 저장
        return True
    data[key] = now
    _save_dedupe(data)
    return False


def check_news_emergency() -> Optional[Dict[str, Any]]:
    """최근 6시간 뉴스에서 위기 키워드 검색.

    Word boundary 매칭 (substring X):
    - "K-Bank" → "ban" 매칭 안 함 ✅
    - "exploiter" → "exploit" 매칭 안 함 ✅
    - "BTC banned" → "banned" 매칭 ✅

    24시간 title dedupe — 같은 기사로 반복 트리거 X (비용 폭주 방지).
    """
    import re

    try:
        all_news = news_adapter.get_all_news(per_source_limit=15)
        if not all_news:
            return None

        cutoff = datetime.now(timezone.utc).timestamp() - 6 * 3600
        recent = [n for n in all_news if n.get("published_ts", 0) >= cutoff]

        # word boundary 패턴 컴파일
        pattern = r'\b(' + '|'.join(re.escape(k) for k in CRISIS_KEYWORDS) + r')\b'
        keyword_re = re.compile(pattern, re.IGNORECASE)

        # 정말 위기 거래소/플랫폼 키워드 (단순 "bitcoin"보다 구체)
        crisis_context_re = re.compile(
            r'\b(binance|bybit|coinbase|upbit|kraken|okx|exchange hack|protocol exploit|'
            r'rug pull|exit scam|sec sues|sec charges|withdrawal halt|'
            r'bankruptcy|insolvent|stolen funds|drained)\b',
            re.IGNORECASE
        )

        crisis_items = []
        for news in recent:
            text = news["title"] + " " + news.get("summary", "")

            keyword_hits = keyword_re.findall(text)
            # 더 엄격: 거래소/플랫폼 위기 컨텍스트도 있어야
            crisis_context = crisis_context_re.search(text)

            if keyword_hits and crisis_context:
                # 24h dedupe: 이미 트리거된 기사는 무시
                if _is_already_processed(news["title"]):
                    continue
                crisis_items.append({
                    "title": news["title"][:200],
                    "source": news["source"],
                    "keywords": list(set(keyword_hits)),
                })

        if not crisis_items:
            return None

        return {
            "type": "CRISIS_NEWS",
            "severity": "MEDIUM",
            "items_count": len(crisis_items),
            "items": crisis_items[:5],
            "message": f"위기 뉴스 {len(crisis_items)}건 (word boundary + context) — AI 점검",
        }
    except Exception as e:
        logger.error(f"뉴스 위기 체크 실패: {e}")
        return None


def check_all() -> Optional[Dict[str, Any]]:
    """모든 위기 체크 (가격 + 뉴스).

    Returns:
        None (정상) 또는 가장 심각한 위기 dict
    """
    # 우선순위: 가격 급락 > 뉴스
    price = check_price_emergency()
    if price and price.get("severity") == "HIGH":
        return price

    news_crisis = check_news_emergency()

    # MEDIUM 둘 중 하나만
    if price:
        return price
    if news_crisis:
        return news_crisis

    return None
