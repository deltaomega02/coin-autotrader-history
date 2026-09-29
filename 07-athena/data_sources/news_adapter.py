"""크립토 뉴스 어댑터 — 다중 RSS 통합.

소스 (전부 무료, 무인증):
- CoinDesk (가장 권위 있음)
- CoinTelegraph
- Decrypt
- The Block
- Bitcoin Magazine
- CryptoSlate
- BeInCrypto

전략: 모든 RSS 병렬로 가져와서 통합 → 시간순 정렬 → BTC 관련 필터.
한 소스 실패해도 다른 소스로 보완 (graceful).
"""

import re
import requests
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from config import get_logger

logger = get_logger("news")


# 검증된 RSS 피드 (공식 매체)
RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ("BeInCrypto", "https://beincrypto.com/feed/"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ATHENA-bot/1.0; +https://athena.local)"
    ),
}

BTC_KEYWORDS = [
    "bitcoin", "btc", "비트코인",
    "etf", "ibit", "fbtc", "blackrock", "fidelity",
    "fomc", "fed", "powell", "rate", "cpi", "inflation",
    "sec", "regulation", "approval",
    "halving", "miner", "hashrate",
    "futures", "perpetual", "funding",
]


def _fetch_one_rss(name: str, url: str, limit: int = 20) -> List[Dict[str, Any]]:
    """단일 RSS 피드 파싱."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()

        root = ET.fromstring(r.content)
        items = []
        # RSS 2.0 또는 Atom
        for item in root.iter():
            tag = item.tag.split("}")[-1]  # namespace 제거
            if tag != "item" and tag != "entry":
                continue

            title = ""
            link = ""
            desc = ""
            pub = ""

            for child in item:
                ctag = child.tag.split("}")[-1]
                if ctag == "title":
                    title = (child.text or "").strip()
                elif ctag == "link":
                    link = (child.text or child.get("href", "")).strip()
                elif ctag in ("description", "summary"):
                    desc = (child.text or "")[:300].strip()
                    desc = re.sub(r"<[^>]+>", "", desc)  # HTML 태그 제거
                elif ctag in ("pubDate", "published", "updated"):
                    pub = (child.text or "").strip()

            if title:
                items.append({
                    "title": title,
                    "summary": desc,
                    "source": name,
                    "published_at": pub,
                    "published_ts": _parse_rss_date(pub),
                    "url": link,
                })
            if len(items) >= limit:
                break

        return items
    except Exception as e:
        logger.debug(f"RSS {name} 실패: {e}")
        return []


def _parse_rss_date(s: str) -> int:
    """RSS pubDate → unix timestamp."""
    if not s:
        return 0
    try:
        dt = parsedate_to_datetime(s)
        return int(dt.timestamp())
    except (TypeError, ValueError):
        try:
            # ISO 형식
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except ValueError:
            return 0


def get_all_news(per_source_limit: int = 15) -> List[Dict[str, Any]]:
    """모든 RSS 통합 → 시간순 정렬."""
    all_items = []
    for name, url in RSS_FEEDS:
        items = _fetch_one_rss(name, url, per_source_limit)
        if items:
            all_items.extend(items)
            logger.debug(f"  {name}: {len(items)}건")

    # 시간순 (최신 먼저)
    all_items.sort(key=lambda x: x["published_ts"], reverse=True)

    # 중복 제거 (같은 제목)
    seen_titles = set()
    deduped = []
    for item in all_items:
        title_key = item["title"].lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped.append(item)

    logger.info(f"뉴스 수집: {len(all_items)} → {len(deduped)} (중복 제거)")
    return deduped


def filter_btc_relevant(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """BTC/거시 관련만 필터."""
    return [
        item for item in items
        if any(k in (item["title"] + item.get("summary", "")).lower()
               for k in BTC_KEYWORDS)
    ]


def get_recent_btc_news(hours: int = 24, max_items: int = 20) -> List[Dict[str, Any]]:
    """최근 N시간 BTC 관련 뉴스 (AI 컨텍스트용)."""
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)

    all_news = get_all_news(per_source_limit=20)
    relevant = filter_btc_relevant(all_news)

    # 시간 필터
    recent = [n for n in relevant if n["published_ts"] >= cutoff]

    # 결과 다듬기 (AI 토큰 절약)
    return [
        {
            "title": n["title"][:200],
            "source": n["source"],
            "published": n["published_at"][:25] if n["published_at"] else "",
        }
        for n in recent[:max_items]
    ]


def get_news_summary(hours: int = 24, query: str = "") -> Dict[str, Any]:
    """AI 컨텍스트용 뉴스 요약.

    Args:
        hours: 시간 윈도우 (1-72)
        query: 추가 키워드 필터 (선택)
               예: "FOMC" / "hack" / "Fed" / "BlackRock"
               빈 문자열이면 BTC 전체
    """
    news = get_recent_btc_news(hours=hours, max_items=30)
    if not news:
        return {"count": 0, "titles": [], "sources_count": {}}

    # 키워드 필터 추가
    if query:
        q_lower = query.lower()
        # 따옴표로 묶은 multi-word 처리 안 함, 단순 substring
        filtered = []
        for n in news:
            text = (n["title"]).lower()
            if q_lower in text:
                filtered.append(n)
        news = filtered

    if not news:
        return {
            "count": 0,
            "titles": [],
            "sources_count": {},
            "query": query,
            "note": f"'{query}' 관련 뉴스 없음 (지난 {hours}h)",
        }

    sources = {}
    for n in news[:15]:
        sources[n["source"]] = sources.get(n["source"], 0) + 1

    return {
        "count": len(news),
        "hours_window": hours,
        "query": query if query else "all_btc",
        "titles": [f"[{n['source']}] {n['title']}" for n in news[:15]],
        "sources_count": sources,
    }


if __name__ == "__main__":
    import json
    summary = get_news_summary(hours=24)
    print(f"수집: {summary['count']}건 / {summary.get('sources_count', {})}")
    print()
    for t in summary["titles"][:10]:
        print(f"- {t}")
