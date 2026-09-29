"""ATHENA 운영 현황 CSV Export.

DB → CSV 파일들로 변환. 엑셀에서 분석 가능.

생성 파일 (logs/csv/ 폴더):
- decisions.csv          : 모든 AI Guardian 결정
- executions.csv         : 모든 거래
- portfolio_history.csv  : 포트폴리오 시간별 변화
- cost_basis.csv         : 자산별 평단가
- daily_summary.csv      : 일일 요약 (PnL + 비용 + 거래)
- ai_costs.csv          : AI 호출 비용 추이

사용:
  cd ~/ATHENA && python3 export_csv.py

  # 결과 다운로드 (Mac)
  gcloud compute scp -r YOUR_USER@YOUR_SERVER:~/ATHENA/logs/csv /tmp/athena_csv --zone=YOUR_ZONE
"""

import csv
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

DB_PATH = Path(__file__).parent / "database" / "athena.db"
CSV_DIR = Path(__file__).parent / "logs" / "csv"

# GCP VM 비용 (월 고정)
GCP_DAILY_USD = 0.77   # 약 ₩1,150/일 = $0.77
GCP_MONTHLY_USD = 23.0


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def export_decisions():
    """모든 AI Guardian 결정."""
    fp = CSV_DIR / "decisions.csv"
    with conn() as c, fp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "timestamp", "cycle_id", "paper_mode",
            "regime", "cycle_score", "confidence", "risk_score",
            "multiplier", "action", "btc_w", "eth_w", "sol_w", "usdt_w",
            "reasoning", "ai_cost_usd",
        ])
        rows = c.execute("SELECT * FROM decisions ORDER BY id ASC").fetchall()
        for r in rows:
            try:
                manager = json.loads(r["manager_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                manager = {}
            target = manager.get("portfolio_decision", {}).get("target_weights", {})
            dca = manager.get("dca_decision", {})

            w.writerow([
                r["id"], r["timestamp"], r["cycle_id"], r["paper_mode"],
                manager.get("regime", ""),
                manager.get("cycle_position_score", ""),
                r["confidence"] or "",
                r["risk_score"] or "",
                dca.get("multiplier", ""),
                manager.get("portfolio_decision", {}).get("action", ""),
                target.get("BTC", ""),
                target.get("ETH", ""),
                target.get("SOL", ""),
                target.get("USDT", ""),
                (manager.get("reasoning") or "")[:300],
                "",  # AI cost는 별도 추적 X (옵션)
            ])
    print(f"✓ {fp.name}: {len(rows)} rows")


def export_executions():
    """모든 거래."""
    fp = CSV_DIR / "executions.csv"
    with conn() as c, fp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "timestamp", "cycle_id", "paper_mode",
            "asset", "side", "value_usdt", "qty", "price",
            "order_id", "error",
        ])
        rows = c.execute("SELECT * FROM executions ORDER BY id ASC").fetchall()
        for r in rows:
            w.writerow([
                r["id"], r["timestamp"], r["cycle_id"], r["paper_mode"],
                r["asset"], r["side"],
                r["value_usdt"], r["qty"] or "", r["price"] or "",
                r["order_id"] or "", r["error"] or "",
            ])
    print(f"✓ {fp.name}: {len(rows)} rows")


def export_snapshots():
    """포트폴리오 시간별 변화."""
    fp = CSV_DIR / "portfolio_history.csv"
    with conn() as c, fp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "timestamp", "total_value_usdt",
            "btc_weight", "eth_weight", "sol_weight", "usdt_weight",
        ])
        rows = c.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY id ASC"
        ).fetchall()
        for r in rows:
            w.writerow([
                r["id"], r["timestamp"], r["total_value_usdt"],
                r["btc_weight"] or "", r["eth_weight"] or "",
                r["sol_weight"] or "", r["usdt_weight"] or "",
            ])
    print(f"✓ {fp.name}: {len(rows)} rows")


def export_cost_basis():
    """자산별 평단가."""
    fp = CSV_DIR / "cost_basis.csv"
    with conn() as c, fp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "asset", "total_qty", "total_cost_usdt", "avg_cost_usdt",
            "realized_pnl_usdt", "last_updated",
        ])
        rows = c.execute("SELECT * FROM cost_basis").fetchall()
        for r in rows:
            w.writerow([
                r["asset"], r["total_qty"], r["total_cost_usdt"],
                r["avg_cost_usdt"], r["realized_pnl_usdt"], r["last_updated"],
            ])
    print(f"✓ {fp.name}: {len(rows)} rows")


def export_daily_summary():
    """일일 요약: 거래 수, PnL, AI 호출, 비용."""
    fp = CSV_DIR / "daily_summary.csv"

    # 일별 데이터 집계
    daily = defaultdict(lambda: {
        "trades_count": 0, "buy_count": 0, "sell_count": 0,
        "buy_value_usdt": 0, "sell_value_usdt": 0,
        "ai_decisions": 0,
        "start_value": 0, "end_value": 0, "min_value": 1e18, "max_value": 0,
    })

    with conn() as c:
        # 거래
        for r in c.execute("SELECT * FROM executions WHERE error IS NULL OR error = ''"):
            day = r["timestamp"][:10]
            daily[day]["trades_count"] += 1
            if r["side"] == "Buy":
                daily[day]["buy_count"] += 1
                daily[day]["buy_value_usdt"] += float(r["value_usdt"] or 0)
            else:
                daily[day]["sell_count"] += 1
                daily[day]["sell_value_usdt"] += float(r["value_usdt"] or 0)

        # 결정
        for r in c.execute("SELECT * FROM decisions"):
            day = r["timestamp"][:10]
            daily[day]["ai_decisions"] += 1

        # 스냅샷 (시작/종료/min/max)
        for r in c.execute("SELECT * FROM portfolio_snapshots ORDER BY id ASC"):
            day = r["timestamp"][:10]
            v = float(r["total_value_usdt"])
            d = daily[day]
            if d["start_value"] == 0:
                d["start_value"] = v
            d["end_value"] = v
            d["min_value"] = min(d["min_value"], v)
            d["max_value"] = max(d["max_value"], v)

    with fp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "date",
            "start_value", "end_value", "min_value", "max_value",
            "daily_pnl_usdt", "daily_pnl_pct",
            "trades_count", "buy_count", "sell_count",
            "buy_value_usdt", "sell_value_usdt",
            "ai_decisions",
            "gcp_cost_usd", "ai_cost_usd_estimate", "total_cost_usd",
        ])
        for day in sorted(daily.keys()):
            d = daily[day]
            pnl = d["end_value"] - d["start_value"] if d["start_value"] else 0
            pnl_pct = (pnl / d["start_value"] * 100) if d["start_value"] else 0
            ai_cost = d["ai_decisions"] * 0.05  # cycle당 평균 $0.05 추정
            total_cost = GCP_DAILY_USD + ai_cost

            w.writerow([
                day,
                round(d["start_value"], 2), round(d["end_value"], 2),
                round(d["min_value"], 2) if d["min_value"] < 1e18 else 0,
                round(d["max_value"], 2),
                round(pnl, 2), round(pnl_pct, 2),
                d["trades_count"], d["buy_count"], d["sell_count"],
                round(d["buy_value_usdt"], 2), round(d["sell_value_usdt"], 2),
                d["ai_decisions"],
                round(GCP_DAILY_USD, 2), round(ai_cost, 4), round(total_cost, 2),
            ])
    print(f"✓ {fp.name}: {len(daily)} days")


def export_ai_costs():
    """AI 호출 비용 추이 (cycle별)."""
    fp = CSV_DIR / "ai_costs.csv"
    with conn() as c, fp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "cycle_id", "regime", "confidence", "ai_cost_usd_estimate"])
        rows = c.execute("SELECT * FROM decisions ORDER BY id ASC").fetchall()
        for r in rows:
            w.writerow([
                r["timestamp"], r["cycle_id"], r["regime"] or "",
                r["confidence"] or "",
                0.05,  # cycle당 평균 $0.05 (실측)
            ])
    print(f"✓ {fp.name}: {len(rows)} rows")


def main():
    if not DB_PATH.exists():
        print(f"❌ DB 없음: {DB_PATH}")
        return

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Export to: {CSV_DIR}")
    print()

    export_decisions()
    export_executions()
    export_snapshots()
    export_cost_basis()
    export_daily_summary()
    export_ai_costs()

    print()
    print("✅ 완료. 파일 다운로드 (Mac):")
    print(f"   gcloud compute scp -r YOUR_USER@YOUR_SERVER:~/ATHENA/logs/csv /tmp/athena_csv --zone=YOUR_ZONE")


if __name__ == "__main__":
    main()
