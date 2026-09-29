# dashboard_app.py
# Streamlit 대시보드
# 포지션 상태, 거래 히스토리, 손익 차트

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from database import db_manager
from exchange import bybit_client
from config import TRADING, BYBIT

st.set_page_config(
    page_title="METIS-F Dashboard",
    page_icon="📈",
    layout="wide"
)

st.title("METIS-F 대시보드")

# 환경 표시
env = "🟡 Testnet" if BYBIT.USE_TESTNET else "🟢 Production"
st.sidebar.markdown(f"**환경**: {env}")

# 잔고 조회
try:
    balance = bybit_client.get_wallet_balance()
    st.sidebar.metric("잔고", f"{balance.get('available_balance', 0):.2f} USDT")
except Exception as e:
    st.sidebar.error(f"잔고 조회 실패: {e}")

# 현재 포지션
st.header("현재 포지션")
try:
    position = bybit_client.get_position(TRADING.SYMBOL)
    if position:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("방향", "LONG" if position['side'] == "Buy" else "SHORT")
        col2.metric("레버리지", f"{position['leverage']}x")
        col3.metric("진입가", f"{position['entry_price']:,.2f}")
        col4.metric("미실현 PnL", f"{position['unrealized_pnl']:+.2f} USDT")
    else:
        st.info("활성 포지션 없음")
except Exception as e:
    st.error(f"포지션 조회 실패: {e}")

# 거래 통계
st.header("거래 통계 (7일)")
try:
    stats = db_manager.get_trade_stats(days=7)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 거래", stats['total_trades'])
    col2.metric("승률", f"{stats['win_rate']:.1f}%")
    col3.metric("누적 PnL", f"{stats['total_pnl']:+.2f} USDT")
    col4.metric("평균 PnL", f"{stats['avg_pnl_pct']:+.2f}%")
except Exception as e:
    st.error(f"통계 조회 실패: {e}")

# 최근 거래
st.header("최근 거래 내역")
try:
    trades = db_manager.get_recent_trades(limit=10)
    if trades:
        df = pd.DataFrame(trades)
        df = df[['direction', 'leverage', 'entry_price', 'exit_price', 
                 'realized_pnl', 'realized_pnl_percentage', 'exit_reason', 'exit_timestamp']]
        df.columns = ['방향', '레버리지', '진입가', '청산가', 'PnL', 'PnL%', '청산사유', '청산시각']
        st.dataframe(df, use_container_width=True)
    else:
        st.info("거래 내역 없음")
except Exception as e:
    st.error(f"거래 내역 조회 실패: {e}")