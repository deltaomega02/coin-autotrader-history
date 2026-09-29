"""ATHENA Streamlit 대시보드.

실시간 모니터링:
- 총 자산 + 24h PnL + 누적 PnL
- 자산별 평단가 vs 현재가 + 수익률
- 포트폴리오 비중 (파이차트)
- 시간별 자산 가치 추이
- AI Guardian 결정 이력
- DCA 누적 현황
- 사이클 위치 (Pi Cycle, MVRV)
- 최근 거래

가동:
  streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0

접속:
  http://<GCP_IP>:8501
  (GCP 방화벽에 8501 포트 열어야 함)
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd

# ATHENA 모듈
from exchange import bybit_spot
from data_sources import (
    bybit_market_adapter,
    fear_greed_adapter,
    etf_flow_adapter,
    cycle_indicators,
)
from core import cost_basis_tracker
from database import db

# ─ 페이지 설정 ─
st.set_page_config(
    page_title="ATHENA Dashboard",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 60초마다 자동 새로고침
st.markdown(
    '<meta http-equiv="refresh" content="60">',
    unsafe_allow_html=True,
)


# ─ 데이터 캐싱 (30초) ─

@st.cache_data(ttl=30)
def fetch_portfolio():
    return bybit_spot.get_portfolio_value_usdt()

@st.cache_data(ttl=30)
def fetch_market():
    return bybit_market_adapter.get_market_snapshot() or {}

@st.cache_data(ttl=60)
def fetch_pnl(prices_tuple):
    prices = dict(prices_tuple)
    return cost_basis_tracker.get_all_cost_basis_with_pnl(prices)

@st.cache_data(ttl=300)
def fetch_fear_greed():
    return fear_greed_adapter.get_current() or {}

@st.cache_data(ttl=300)
def fetch_etf():
    return etf_flow_adapter.get_summary(7) or {}

@st.cache_data(ttl=600)
def fetch_cycle():
    return cycle_indicators.get_cycle_position_score() or {}

@st.cache_data(ttl=60)
def fetch_snapshots():
    return db.get_recent_snapshots(days=30)

@st.cache_data(ttl=60)
def fetch_decisions():
    return db.get_recent_decisions(days=14)

@st.cache_data(ttl=60)
def fetch_dca_pending():
    try:
        return db.get_all_dca_pending()
    except Exception:
        return {}


# ─ 헤더 ─
st.title("🏛️ ATHENA Dashboard")
st.caption(f"마지막 업데이트: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} (60초 자동 새로고침)")

# ────────────────────────────────────────────────────────────
# 데이터 로드
# ────────────────────────────────────────────────────────────

try:
    portfolio = fetch_portfolio()
    market = fetch_market()
    snapshots = fetch_snapshots()
    decisions = fetch_decisions()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# 가격
prices = {
    "BTC": float(market.get("BTCUSDT", {}).get("price", 0) or 0),
    "ETH": float(market.get("ETHUSDT", {}).get("price", 0) or 0),
    "SOL": float(market.get("SOLUSDT", {}).get("price", 0) or 0),
}

pnl_data = fetch_pnl(tuple(prices.items()))

# 통계
total_value = portfolio.get("total_usdt", 0)
weights = portfolio.get("weights", {})
values = portfolio.get("values", {})

if snapshots:
    start_value = float(snapshots[0]["total_value_usdt"])
    peak_value = max(float(s["total_value_usdt"]) for s in snapshots)

    # 24h 전 잔고
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    snap_24h = [s for s in snapshots if s["timestamp"] < cutoff_24h]
    value_24h_ago = float(snap_24h[-1]["total_value_usdt"]) if snap_24h else start_value
else:
    start_value = total_value
    peak_value = total_value
    value_24h_ago = total_value

total_change = total_value - start_value
total_pct = (total_change / start_value * 100) if start_value > 0 else 0
change_24h = total_value - value_24h_ago
pct_24h = (change_24h / value_24h_ago * 100) if value_24h_ago > 0 else 0
dd_from_peak = (peak_value - total_value) / peak_value * 100 if peak_value > 0 else 0

# ────────────────────────────────────────────────────────────
# 상단 메트릭 (4 열)
# ────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "💰 총 자산",
        f"${total_value:,.2f}",
        f"{total_pct:+.2f}% (시작 대비)",
    )

with col2:
    st.metric(
        "📈 24h PnL",
        f"${change_24h:+.2f}",
        f"{pct_24h:+.2f}%",
    )

with col3:
    st.metric(
        "💎 누적 PnL",
        f"${pnl_data.get('total_pnl_usdt', 0):+.2f}",
        f"실현 ${pnl_data.get('total_realized_pnl_usdt', 0):+.2f}",
    )

with col4:
    st.metric(
        "📉 DD from peak",
        f"-{dd_from_peak:.2f}%",
        f"피크 ${peak_value:,.2f}",
        delta_color="inverse",
    )

st.divider()

# ────────────────────────────────────────────────────────────
# 자산별 PnL + 비중
# ────────────────────────────────────────────────────────────

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📊 자산별 PnL")
    rows = []
    for asset in ["BTC", "ETH", "SOL"]:
        info = pnl_data["assets"].get(asset, {})
        qty = info.get("qty", 0)
        if qty <= 0:
            continue
        rows.append({
            "자산": asset,
            "수량": f"{qty:.6f}",
            "평단가": f"${info.get('avg_cost_usdt', 0):,.2f}",
            "현재가": f"${prices.get(asset, 0):,.2f}",
            "PnL %": f"{info.get('vs_avg_pct', 0):+.2f}%",
            "PnL $": f"${info.get('unrealized_pnl_usdt', 0):+.2f}",
            "가치": f"${info.get('current_value_usdt', 0):,.2f}",
        })
    # USDT
    rows.append({
        "자산": "USDT",
        "수량": f"{values.get('USDT', 0):,.2f}",
        "평단가": "-",
        "현재가": "$1.00",
        "PnL %": "-",
        "PnL $": "-",
        "가치": f"${values.get('USDT', 0):,.2f}",
    })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

with col_right:
    st.subheader("🥧 자산 비중")
    if weights:
        weight_df = pd.DataFrame([
            {"자산": a, "비중": w * 100}
            for a, w in weights.items() if w > 0.001
        ])
        st.bar_chart(weight_df.set_index("자산"))

st.divider()

# ────────────────────────────────────────────────────────────
# 시간별 자산 가치 추이
# ────────────────────────────────────────────────────────────

st.subheader("📈 자산 가치 추이 (30일)")

if len(snapshots) >= 2:
    snap_df = pd.DataFrame([
        {
            "시간": pd.to_datetime(s["timestamp"]),
            "총자산 (USD)": float(s["total_value_usdt"]),
        }
        for s in snapshots
    ])
    st.line_chart(snap_df.set_index("시간"))
else:
    st.info("데이터 누적 중 (스냅샷 부족)")

st.divider()

# ────────────────────────────────────────────────────────────
# 시장 사이클 + 시그널
# ────────────────────────────────────────────────────────────

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.subheader("🎯 사이클 위치")
    try:
        cycle = fetch_cycle()
    except Exception:
        cycle = {}
    score = cycle.get("cycle_position", 50)
    regime = cycle.get("regime", "?")
    st.metric(f"점수 ({regime})", f"{score}/100")
    st.progress(min(100, max(0, score)) / 100)
    if cycle.get("factors"):
        for f in cycle["factors"][:3]:
            st.caption(f"• {f}")

with col_b:
    st.subheader("😱 Fear & Greed")
    try:
        fg = fetch_fear_greed()
    except Exception:
        fg = {}
    fg_value = fg.get("value", 50)
    fg_label = fg.get("label", "?")
    st.metric(fg_label, f"{fg_value}/100")
    st.progress(fg_value / 100)

with col_c:
    st.subheader("💸 ETF 7일 흐름")
    try:
        etf = fetch_etf()
    except Exception:
        etf = {}
    cum = etf.get("cumulative_net_musd", 0)
    trend = etf.get("trend", "?")
    st.metric(f"누적 ({trend})", f"${cum:,.1f}M")
    st.caption(f"매수일 {etf.get('inflow_days', 0)}/7")
    st.caption(f"IBIT 비중 {etf.get('ibit_dominance', 0)*100:.0f}%")

st.divider()

# ────────────────────────────────────────────────────────────
# AI Guardian 결정 이력
# ────────────────────────────────────────────────────────────

st.subheader("🏛️ AI Guardian 최근 결정")

if decisions:
    rows = []
    for d in decisions[:10]:
        try:
            manager = json.loads(d.get("manager_json") or "{}")
            dca = manager.get("dca_decision", {})
            pf = manager.get("portfolio_decision", {})
            ts = d["timestamp"][:19].replace("T", " ")
            rows.append({
                "시각": ts,
                "Regime": manager.get("regime", "-"),
                "사이클": manager.get("cycle_position_score", "-"),
                "Multiplier": dca.get("multiplier", "-"),
                "Action": pf.get("action", "-"),
                "신뢰도": manager.get("confidence", "-"),
                "근거 (요약)": (manager.get("reasoning") or "")[:80],
            })
        except (json.JSONDecodeError, TypeError):
            continue

    if rows:
        df_d = pd.DataFrame(rows)
        st.dataframe(df_d, hide_index=True, use_container_width=True)
else:
    st.info("결정 이력 없음")

st.divider()

# ────────────────────────────────────────────────────────────
# DCA 누적 현황
# ────────────────────────────────────────────────────────────

col_dca, col_emergency = st.columns(2)

with col_dca:
    st.subheader("📦 DCA 누적 매수 대기")
    pending = fetch_dca_pending()
    if pending:
        for asset in ["BTC", "ETH", "SOL"]:
            amt = pending.get(asset, 0)
            target = 5.0  # min order
            ratio = min(1.0, amt / target)
            st.text(f"{asset}: ${amt:.2f} / ${target:.2f}")
            st.progress(ratio)
    else:
        st.info("누적 없음")

with col_emergency:
    st.subheader("🌐 시장 시세")
    for asset in ["BTC", "ETH", "SOL"]:
        symbol = f"{asset}USDT"
        m = market.get(symbol, {})
        if m:
            change = m.get("change_24h_pct", 0)
            st.metric(asset, f"${prices[asset]:,.2f}", f"{change:+.2f}% (24h)")

# ─ Footer ─
st.divider()
st.caption(f"ATHENA — Smart DCA + AI Guardian | Bybit Spot | {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
