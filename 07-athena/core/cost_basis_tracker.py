"""평단가 추적 시스템.

자산별 평균 매입가를 추적해서 AI에게 "지금 비싼지 싼지" 판단 정보 제공.

알고리즘:
- BUY: 누적 수량 + 누적 비용 → 평단가 갱신 (가중 평균)
- SELL: 평단가 유지 (감소된 수량만 반영) + 실현 PnL 기록

수수료/슬리피지는 단순화 위해 cost에 포함됨.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from config import get_logger
from database.db_manager import DB_PATH

logger = get_logger("cost_basis")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def record_buy(asset: str, qty: float, price: float) -> Dict[str, Any]:
    """매수 기록 → 평단가 갱신.

    Args:
        asset: "BTC" / "ETH" / "SOL"
        qty: 매수 수량 (BASE)
        price: 매수 가격 (USDT)

    Returns 갱신된 평단가 정보.
    """
    cost = qty * price
    now = datetime.now(timezone.utc).isoformat()

    with _conn() as c:
        row = c.execute("SELECT * FROM cost_basis WHERE asset=?", (asset,)).fetchone()

        if row:
            new_qty = row["total_qty"] + qty
            new_cost = row["total_cost_usdt"] + cost
            new_avg = new_cost / new_qty if new_qty > 0 else 0
            c.execute("""
                UPDATE cost_basis
                SET total_qty=?, total_cost_usdt=?, avg_cost_usdt=?, last_updated=?
                WHERE asset=?
            """, (new_qty, new_cost, new_avg, now, asset))
        else:
            c.execute("""
                INSERT INTO cost_basis
                (asset, total_qty, total_cost_usdt, avg_cost_usdt, last_updated, realized_pnl_usdt)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (asset, qty, cost, price, now))

    return get_cost_basis(asset)


def record_sell(asset: str, qty: float, price: float) -> Dict[str, Any]:
    """매도 기록 → 평단가 유지 + 실현 PnL 누적."""
    now = datetime.now(timezone.utc).isoformat()
    proceeds = qty * price

    with _conn() as c:
        row = c.execute("SELECT * FROM cost_basis WHERE asset=?", (asset,)).fetchone()
        if not row or row["total_qty"] <= 0:
            logger.warning(f"매도 기록 실패: {asset} 보유 수량 없음")
            return {}

        # 매도 비율
        sell_ratio = min(1.0, qty / row["total_qty"])

        # 매도분의 cost basis (비례)
        cost_basis_sold = row["total_cost_usdt"] * sell_ratio

        # 실현 PnL = 매도 대금 - 매도분 cost basis
        realized = proceeds - cost_basis_sold

        new_qty = row["total_qty"] - qty
        new_cost = row["total_cost_usdt"] - cost_basis_sold
        if new_qty <= 0:
            new_qty = 0
            new_cost = 0
            new_avg = 0
        else:
            new_avg = new_cost / new_qty

        c.execute("""
            UPDATE cost_basis
            SET total_qty=?, total_cost_usdt=?, avg_cost_usdt=?,
                realized_pnl_usdt=realized_pnl_usdt+?, last_updated=?
            WHERE asset=?
        """, (new_qty, new_cost, new_avg, realized, now, asset))

    logger.info(f"[Sell] {asset} {qty} @ ${price:.2f} = +${realized:.2f} 실현 (누적 갱신)")
    return get_cost_basis(asset)


def get_cost_basis(asset: str) -> Dict[str, Any]:
    """특정 자산 평단가 + 미실현 손익."""
    with _conn() as c:
        row = c.execute("SELECT * FROM cost_basis WHERE asset=?", (asset,)).fetchone()
        if not row:
            return {
                "asset": asset, "qty": 0, "avg_cost_usdt": 0,
                "total_cost_usdt": 0, "realized_pnl_usdt": 0,
            }
        return dict(row)


def get_all_cost_basis_with_pnl(current_prices: Dict[str, float]) -> Dict[str, Any]:
    """모든 자산 평단가 + 현재가 비교 + 미실현 PnL.

    Args:
        current_prices: {"BTC": 95000.0, "ETH": 3500.0, ...}

    Returns:
        {
          "assets": {
            "BTC": {
              "qty": 0.012,
              "avg_cost_usdt": 92000,
              "current_price": 95000,
              "unrealized_pnl_usdt": 36,
              "unrealized_pnl_pct": 3.26,
              "vs_avg_pct": 3.26,    # 현재가가 평단 대비 +3.26%
            },
            ...
          },
          "total_realized_pnl_usdt": 12.5,
          "total_unrealized_pnl_usdt": 50.2,
          "total_pnl_usdt": 62.7,
        }
    """
    with _conn() as c:
        rows = c.execute("SELECT * FROM cost_basis").fetchall()

    assets = {}
    total_realized = 0
    total_unrealized = 0

    for row in rows:
        asset = row["asset"]
        qty = row["total_qty"]
        avg = row["avg_cost_usdt"]
        realized = row["realized_pnl_usdt"]
        total_realized += realized

        if qty <= 0 or avg <= 0:
            assets[asset] = {
                "qty": qty, "avg_cost_usdt": avg,
                "current_price": current_prices.get(asset, 0),
                "unrealized_pnl_usdt": 0,
                "unrealized_pnl_pct": 0,
                "vs_avg_pct": 0,
            }
            continue

        cur = current_prices.get(asset, 0)
        unrealized = (cur - avg) * qty
        pct = (cur - avg) / avg * 100 if avg > 0 else 0
        total_unrealized += unrealized

        assets[asset] = {
            "qty": round(qty, 8),
            "avg_cost_usdt": round(avg, 2),
            "current_price": round(cur, 2),
            "current_value_usdt": round(qty * cur, 2),
            "total_cost_usdt": round(row["total_cost_usdt"], 2),
            "unrealized_pnl_usdt": round(unrealized, 2),
            "unrealized_pnl_pct": round(pct, 2),
            "vs_avg_pct": round(pct, 2),
            "realized_pnl_usdt": round(realized, 2),
        }

    return {
        "assets": assets,
        "total_realized_pnl_usdt": round(total_realized, 2),
        "total_unrealized_pnl_usdt": round(total_unrealized, 2),
        "total_pnl_usdt": round(total_realized + total_unrealized, 2),
    }
