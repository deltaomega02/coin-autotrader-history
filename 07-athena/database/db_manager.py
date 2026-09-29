"""ATHENA SQLite 매니저."""

import sqlite3
import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from config import get_logger

logger = get_logger("db")

DB_PATH = Path(__file__).parent / "athena.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DB:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._init_schema()

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self):
        if not SCHEMA_PATH.exists():
            logger.error(f"schema.sql 없음: {SCHEMA_PATH}")
            return
        sql = SCHEMA_PATH.read_text()
        with self._conn() as c:
            c.executescript(sql)

    # ────────────────────────────────────────
    # decisions
    # ────────────────────────────────────────

    def save_decision(self, cycle_id: str, paper_mode: bool,
                      analyst: dict, risk: dict, manager: dict,
                      input_hash: str = "") -> int:
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO decisions
                (timestamp, cycle_id, paper_mode, analyst_json, risk_json, manager_json,
                 confidence, risk_score, regime, input_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                cycle_id,
                1 if paper_mode else 0,
                json.dumps(analyst, ensure_ascii=False, default=str) if analyst else None,
                json.dumps(risk, ensure_ascii=False, default=str) if risk else None,
                json.dumps(manager, ensure_ascii=False, default=str) if manager else None,
                manager.get("confidence") if manager else None,
                risk.get("risk_score") if risk else None,
                analyst.get("regime") if analyst else None,
                input_hash,
            ))
            return cur.lastrowid

    def get_recent_decisions(self, days: int = 7) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT * FROM decisions
                WHERE datetime(timestamp) > datetime('now', ?)
                ORDER BY id DESC
            """, (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]

    # ────────────────────────────────────────
    # executions
    # ────────────────────────────────────────

    def save_execution(self, cycle_id: str, paper_mode: bool,
                       asset: str, side: str, value_usdt: float,
                       qty: Optional[float] = None, price: Optional[float] = None,
                       order_id: Optional[str] = None, error: Optional[str] = None) -> int:
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO executions
                (timestamp, cycle_id, asset, side, value_usdt, qty, price,
                 paper_mode, order_id, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                cycle_id, asset, side, value_usdt, qty, price,
                1 if paper_mode else 0, order_id, error,
            ))
            return cur.lastrowid

    # ────────────────────────────────────────
    # portfolio snapshots
    # ────────────────────────────────────────

    def save_snapshot(self, cycle_id: Optional[str], total_value: float,
                      weights: Dict[str, float], values: Dict[str, float]) -> int:
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO portfolio_snapshots
                (timestamp, cycle_id, total_value_usdt,
                 btc_weight, eth_weight, sol_weight, usdt_weight,
                 weights_json, values_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                cycle_id, total_value,
                weights.get("BTC"), weights.get("ETH"),
                weights.get("SOL"), weights.get("USDT"),
                json.dumps(weights), json.dumps(values),
            ))
            return cur.lastrowid

    def get_recent_snapshots(self, days: int = 7) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT * FROM portfolio_snapshots
                WHERE datetime(timestamp) > datetime('now', ?)
                ORDER BY id ASC
            """, (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]

    def get_peak_value(self) -> float:
        with self._conn() as c:
            row = c.execute(
                "SELECT MAX(total_value_usdt) AS peak FROM portfolio_snapshots"
            ).fetchone()
            return float(row["peak"]) if row and row["peak"] else 0.0

    # ────────────────────────────────────────
    # reflections
    # ────────────────────────────────────────

    # ────────────────────────────────────────
    # DCA 누적 매수 대기
    # ────────────────────────────────────────

    def get_dca_pending(self, asset: str) -> float:
        """누적된 매수 대기액 (USDT)."""
        with self._conn() as c:
            row = c.execute(
                "SELECT pending_usdt FROM dca_pending WHERE asset=?", (asset,)
            ).fetchone()
            return float(row["pending_usdt"]) if row else 0.0

    def add_dca_pending(self, asset: str, amount: float):
        """누적액에 추가 (UPSERT)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute("""
                INSERT INTO dca_pending (asset, pending_usdt, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(asset) DO UPDATE SET
                    pending_usdt = pending_usdt + excluded.pending_usdt,
                    last_updated = excluded.last_updated
            """, (asset, amount, now))

    def reset_dca_pending(self, asset: str):
        """매수 성공 시 누적 0으로."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute("""
                INSERT INTO dca_pending (asset, pending_usdt, last_updated)
                VALUES (?, 0, ?)
                ON CONFLICT(asset) DO UPDATE SET
                    pending_usdt = 0, last_updated = excluded.last_updated
            """, (asset, now))

    def get_all_dca_pending(self) -> Dict[str, float]:
        """모든 자산 누적액."""
        with self._conn() as c:
            rows = c.execute("SELECT asset, pending_usdt FROM dca_pending").fetchall()
            return {r["asset"]: float(r["pending_usdt"]) for r in rows}

    def save_reflection(self, week_start: str, week_end: str,
                       pnl_usdt: float, pnl_pct: float, reflection: dict) -> int:
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO reflections
                (timestamp, week_start, week_end, weekly_pnl_usdt, weekly_pnl_pct, reflection_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                week_start, week_end, pnl_usdt, pnl_pct,
                json.dumps(reflection, ensure_ascii=False, default=str),
            ))
            return cur.lastrowid


db = DB()
