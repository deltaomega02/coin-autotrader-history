"""실시간 PnL 확인.

사용:
  cd ~/ATHENA && python3 check_pnl.py

표시:
- 자산별 보유 수량 + 평단가 + 현재가 + 수익률
- 총 미실현 PnL + 실현 PnL + 합계
- 시작 잔고 대비 PnL
"""

import sys
from pathlib import Path

# 현재 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))


def main():
    try:
        from data_sources import bybit_market_adapter
        from core import cost_basis_tracker
        from exchange import bybit_spot
        from database import db
    except ImportError as e:
        print(f"❌ Import 실패: {e}")
        print("   해결: cd ~/ATHENA && python3 check_pnl.py")
        return

    print("=" * 70)
    print("📊 ATHENA 실시간 PnL")
    print("=" * 70)
    print()

    # 1. 현재 시세
    snapshot = bybit_market_adapter.get_market_snapshot() or {}
    prices = {
        "BTC": float(snapshot.get("BTCUSDT", {}).get("price", 0) or 0),
        "ETH": float(snapshot.get("ETHUSDT", {}).get("price", 0) or 0),
        "SOL": float(snapshot.get("SOLUSDT", {}).get("price", 0) or 0),
    }

    if not any(prices.values()):
        print("❌ 시세 조회 실패")
        return

    # 2. 평단가 + PnL
    pnl = cost_basis_tracker.get_all_cost_basis_with_pnl(prices)

    print("자산별 (평단가 vs 현재가):")
    print(f"{'자산':5} {'수량':>14} {'평단':>12} {'현재':>12} {'PnL%':>8} {'PnL$':>10}")
    print("-" * 70)

    for asset in ["BTC", "ETH", "SOL"]:
        info = pnl["assets"].get(asset, {})
        qty = info.get("qty", 0)
        avg = info.get("avg_cost_usdt", 0)
        cur = prices.get(asset, 0)
        pnl_usd = info.get("unrealized_pnl_usdt", 0)
        pnl_pct = info.get("vs_avg_pct", 0)

        if qty <= 0:
            print(f"{asset:5} {'(보유 없음)':>14}")
            continue

        # 색상 표시 (음수/양수)
        marker = "🟢" if pnl_pct >= 0 else "🔴"
        print(f"{asset:5} {qty:>14.6f} ${avg:>10.2f} ${cur:>10.2f} "
              f"{marker}{pnl_pct:>+6.2f}% ${pnl_usd:>+8.2f}")

    # 3. 종합
    print()
    print("-" * 70)
    realized = pnl.get("total_realized_pnl_usdt", 0)
    unrealized = pnl.get("total_unrealized_pnl_usdt", 0)
    total_pnl = pnl.get("total_pnl_usdt", 0)

    r_marker = "🟢" if realized >= 0 else "🔴"
    u_marker = "🟢" if unrealized >= 0 else "🔴"
    t_marker = "🟢" if total_pnl >= 0 else "🔴"

    print(f"실현 PnL    {r_marker} ${realized:>+10.2f}")
    print(f"미실현 PnL  {u_marker} ${unrealized:>+10.2f}")
    print(f"총 PnL      {t_marker} ${total_pnl:>+10.2f}")

    # 4. 현재 포트폴리오 가치 vs 시작 잔고
    print()
    print("=" * 70)
    portfolio = bybit_spot.get_portfolio_value_usdt()
    current_value = portfolio.get("total_usdt", 0)

    # 첫 snapshot = 시작 잔고
    snapshots = db.get_recent_snapshots(days=365)  # 365일 (충분히 길게)
    if snapshots:
        start_value = float(snapshots[0]["total_value_usdt"])
        peak_value = max(float(s["total_value_usdt"]) for s in snapshots)
    else:
        start_value = current_value
        peak_value = current_value

    total_change = current_value - start_value
    total_pct = (total_change / start_value * 100) if start_value > 0 else 0
    dd_from_peak = (peak_value - current_value) / peak_value * 100 if peak_value > 0 else 0

    p_marker = "🟢" if total_change >= 0 else "🔴"
    print(f"📦 포트폴리오 종합")
    print(f"   시작 잔고  ${start_value:>10.2f}")
    print(f"   최고 잔고  ${peak_value:>10.2f}")
    print(f"   현재 잔고  ${current_value:>10.2f}")
    print(f"   변화       {p_marker} ${total_change:>+8.2f} ({total_pct:+.2f}%)")
    print(f"   DD from peak  -{dd_from_peak:.2f}%")

    # 5. 자산 비중
    print()
    weights = portfolio.get("weights", {})
    if weights:
        print("자산 비중:")
        for asset, w in sorted(weights.items(), key=lambda x: -x[1]):
            if w > 0.001:
                bar = "█" * int(w * 30)
                print(f"  {asset:5} {w*100:>5.1f}% {bar}")


if __name__ == "__main__":
    main()
