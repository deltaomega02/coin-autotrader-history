"""Reddit JSON API — 무인증, 무료.

각 subreddit URL 끝에 .json 추가하면 구조화 데이터.
Rate limit: 약 10 requests/min (unauthenticated)

X(Twitter) API ($100/월) 대안.
"""

import requests
from typing import Optional, List, Dict, Any

from config import DATA_SOURCES, get_logger

logger = get_logger("reddit")


def get_top_posts(subreddit: str = "Bitcoin", limit: int = 25,
                  time_filter: str = "day") -> Optional[List[Dict[str, Any]]]:
    """Subreddit 인기 게시물.

    Args:
        subreddit: "Bitcoin" / "CryptoCurrency" / "BitcoinMarkets"
        limit: 최대 100
        time_filter: "hour" / "day" / "week" / "month"

    Returns:
        [{"title", "score", "num_comments", "upvote_ratio", "url"}, ...]
    """
    try:
        url = f"{DATA_SOURCES.REDDIT_BASE}/r/{subreddit}/top/.json"
        params = {"limit": limit, "t": time_filter}
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": "ATHENA-bot/1.0"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        return [
            {
                "title": p["data"]["title"],
                "score": p["data"]["score"],
                "num_comments": p["data"]["num_comments"],
                "upvote_ratio": p["data"]["upvote_ratio"],
                "created_utc": p["data"]["created_utc"],
                "url": p["data"]["url"],
            }
            for p in data["data"]["children"]
        ]
    except Exception as e:
        logger.error(f"Reddit /r/{subreddit} 실패: {e}")
        return None


def get_sentiment_summary(subreddit: str = "Bitcoin", limit: int = 25) -> Optional[Dict[str, Any]]:
    """간단한 sentiment 요약 (LLM에게 줄 컨텍스트).

    Returns:
        {"top_titles": [...], "avg_upvote_ratio": 0.85, "total_score": 12000}
    """
    posts = get_top_posts(subreddit, limit, "day")
    if not posts:
        return None

    return {
        "subreddit": subreddit,
        "post_count": len(posts),
        "top_titles": [p["title"] for p in posts[:10]],
        "avg_upvote_ratio": sum(p["upvote_ratio"] for p in posts) / len(posts),
        "total_score": sum(p["score"] for p in posts),
        "high_engagement_titles": [
            p["title"] for p in posts
            if p["num_comments"] > 100 or p["score"] > 500
        ][:5],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_sentiment_summary("Bitcoin"), indent=2, ensure_ascii=False))
