"""BTC 스팟 ETF 자금 흐름 — bitbo.io 스크래핑.

Farside는 Cloudflare 차단 (403). bitbo.io는 차단 없음.
URL: https://bitbo.io/treasuries/etf-flows/

테이블 구조 (검증 완료 2026-04-27):
  헤더: Date, IBIT, FBTC, GBTC, BTC, BITB, ARKB, HODL, BTCO, BRRR, EZBC,
        MSBT, BTCW, DEFI, Totals, Total, Average, Maximum, Minimum
  데이터: 일별 14일치 (최근 2주), USD millions
  날짜: "Apr 23, 2026" 형식
  Totals = 일별 모든 ETF 합계

2024 ETF 승인 후 가장 중요한 신호 (구조적 매수세).
"""

import re
import requests
from typing import Optional, Dict, List, Any
from datetime import datetime

from config import get_logger

logger = get_logger("etf")

URL = "https://bitbo.io/treasuries/etf-flows/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def get_recent_flows(days: int = 14) -> Optional[List[Dict[str, Any]]]:
    """최근 N일 BTC ETF 일별 순유입.

    Returns:
        [{"date": "2026-04-23", "total_musd": 230.6, "ibit_musd": 169.8, ...}, ...]
    """
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        html = r.text

        # 첫 번째 stats-table larger-table 추출
        match = re.search(
            r'<table[^>]*class="[^"]*stats-table[^"]*"[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not match:
            logger.error("ETF table 못 찾음")
            return None

        table_html = match.group(1)

        # 헤더 추출
        headers = re.findall(r'<th[^>]*>(.*?)</th>', table_html, re.DOTALL)
        headers = [re.sub(r'<[^>]+>', '', h).strip() for h in headers]

        # 행 추출 (헤더 행 제외)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

        results = []
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if not cells:
                continue
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if not cells or not _is_date(cells[0]):
                continue

            try:
                date_str = _normalize_date(cells[0])
                # cells[1:14] = 13개 ETF, cells[14] = Totals
                total = _parse_float(cells[14]) if len(cells) > 14 else 0.0

                row_data = {"date": date_str, "total_musd": total}

                # 주요 ETF 개별 (IBIT가 가장 큼)
                for i, etf in enumerate(["ibit", "fbtc", "gbtc", "btc_mini", "bitb", "arkb"]):
                    idx = i + 1
                    if idx < len(cells):
                        row_data[f"{etf}_musd"] = _parse_float(cells[idx])

                results.append(row_data)
            except (ValueError, IndexError) as e:
                logger.debug(f"row 파싱 실패: {e}")
                continue

        # 최신순 → 오래된순 (보통 사이트가 최신 위)
        results.reverse()
        return results[-days:] if results else None

    except Exception as e:
        logger.error(f"bitbo.io ETF 실패: {e}")
        return None


def _is_date(s: str) -> bool:
    """'Apr 23, 2026' 형식인지."""
    return bool(re.match(r"\w{3}\s+\d{1,2},\s+\d{4}", s))


def _normalize_date(s: str) -> str:
    """'Apr 23, 2026' → '2026-04-23'"""
    try:
        return datetime.strptime(s, "%b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return s


def _parse_float(s: str) -> float:
    s = s.strip().replace("$", "").replace(",", "").replace("M", "")
    s = s.replace("(", "-").replace(")", "")
    if s in ("", "-", "N/A", "—"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def get_summary(days: int = 7) -> Optional[Dict[str, Any]]:
    """누적 흐름 요약 (AI 컨텍스트용).

    Returns:
        {
          "days": 7,
          "cumulative_net_musd": 1234.5,
          "inflow_days": 5,
          "outflow_days": 2,
          "latest_date": "2026-04-23",
          "latest_flow_musd": 230.6,
          "ibit_dominance": 0.73,    # IBIT가 전체의 몇 %
          "trend": "INFLOW" | "OUTFLOW" | "MIXED"
        }
    """
    flows = get_recent_flows(days)
    if not flows:
        return None

    cum_total = sum(f["total_musd"] for f in flows)
    cum_ibit = sum(f.get("ibit_musd", 0) for f in flows)
    pos_days = sum(1 for f in flows if f["total_musd"] > 0)
    neg_days = sum(1 for f in flows if f["total_musd"] < 0)

    if cum_total > 0:
        trend = "INFLOW"
    elif cum_total < 0:
        trend = "OUTFLOW"
    else:
        trend = "MIXED"

    return {
        "days": len(flows),
        "cumulative_net_musd": round(cum_total, 1),
        "inflow_days": pos_days,
        "outflow_days": neg_days,
        "latest_date": flows[-1]["date"],
        "latest_flow_musd": flows[-1]["total_musd"],
        "ibit_dominance": round(abs(cum_ibit) / abs(cum_total), 2) if cum_total else None,
        "trend": trend,
    }


if __name__ == "__main__":
    import json
    summary = get_summary(7)
    print(json.dumps(summary, indent=2, ensure_ascii=False) if summary else "Failed")
