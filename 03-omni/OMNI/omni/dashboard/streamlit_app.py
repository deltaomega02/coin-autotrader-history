# dashboard/streamlit_app_minimal.py
# OMNI Trading System Dashboard - Minimalist Version
# Powered by 운영자

import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

# 상위 디렉토리 추가
sys.path.append(str(Path(__file__).parent.parent))

from data.database import TradeDatabase
from data.upbit_client import UpbitClient
from config.settings import settings

# ==================== 페이지 설정 ====================
st.set_page_config(
    page_title="OMNI Trading System",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 미니멀 스타일 ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');
    
    * {
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    .stApp {
        background: #ffffff;
    }
    
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    h1, h2, h3, h4, h5, h6 {
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    
    .dataframe {
        font-size: 12px;
    }
    
    /* 메트릭 스타일 */
    [data-testid="metric-container"] {
        background: #f8f9fa;
        padding: 15px;
        border: 1px solid #dee2e6;
        border-radius: 0;
    }
    
    [data-testid="metric-container"] label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #6c757d;
    }
    
    [data-testid="metric-container"] [data-testid="metric-value"] {
        font-size: 20px;
        font-weight: 600;
    }
    
    /* 테이블 스타일 */
    .dataframe thead th {
        background: #f8f9fa;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .dataframe tbody td {
        font-size: 12px;
        border-bottom: 1px solid #f0f0f0;
    }
    
    /* 버튼 스타일 */
    .stButton button {
        background: #000;
        color: #fff;
        border-radius: 0;
        border: 1px solid #000;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 0.4rem 1.5rem;
    }
    
    .stButton button:hover {
        background: #fff;
        color: #000;
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
        border-bottom: 2px solid #000;
    }
    
    .stTabs [aria-selected="true"] {
        background: transparent;
        border-bottom: 2px solid #000;
    }
    
    /* 제거할 요소들 */
    div[data-testid="stSidebarNav"] {
        display: none;
    }
    
    .css-1rs6os {
        display: none;
    }
    
    .main > div:first-child {
        padding-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 데이터 함수 ====================
@st.cache_resource
def get_db_connection():
    """DB 연결"""
    try:
        db_path = settings.DB_PATH
        if os.path.exists(db_path):
            return sqlite3.connect(db_path, check_same_thread=False)
        return None
    except:
        return None

@st.cache_data(ttl=5)
def load_trades():
    """거래 내역 로드 - V14 업데이트: T1, T2 목표가 지원"""
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT 
            trade_id,
            timestamp,
            coin_ticker,
            status,
            entry_price,
            target_price_1,
            target_price_2,
            target_split_ratio,
            stop_loss_price,
            actual_entry_price,
            actual_exit_price,
            actual_volume,
            entry_fee,
            exit_fee,
            profit_loss,
            profit_rate,
            exit_timestamp,
            target_1_reached_time,
            target_1_exit_price,
            target_1_exit_volume,
            target_2_exit_price,
            target_2_exit_volume,
            breakeven_stop_moved
        FROM trade_log 
        ORDER BY timestamp DESC 
        LIMIT 100
        """
        df = pd.read_sql_query(query, conn)
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'], errors='coerce')
            df['target_1_reached_time'] = pd.to_datetime(df['target_1_reached_time'], errors='coerce')
        
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=10)
def load_current_status():
    """현재 상태 로드"""
    try:
        client = UpbitClient()
        
        # KRW 잔고
        krw_balance = client.get_balance("KRW")
        
        # 보유 코인
        balances = client.get_balances()
        holdings = []
        for b in balances:
            if b['currency'] != 'KRW' and float(b['balance']) > 0:
                ticker = f"KRW-{b['currency']}"
                current_price = client.get_current_price(ticker)
                
                holdings.append({
                    'coin': b['currency'],
                    'ticker': ticker,
                    'amount': float(b['balance']),
                    'avg_price': float(b.get('avg_buy_price', 0)),
                    'current_price': current_price,
                    'value': float(b['balance']) * current_price if current_price else 0
                })
        
        # BTC 가격 (참고용)
        btc_price = client.get_current_price("KRW-BTC")
        
        return {
            'krw_balance': krw_balance,
            'holdings': holdings,
            'btc_price': btc_price,
            'timestamp': datetime.now()
        }
    except Exception as e:
        return {
            'krw_balance': 0,
            'holdings': [],
            'btc_price': 0,
            'timestamp': datetime.now()
        }

def format_krw(amount):
    """원화 포맷 (심플)"""
    try:
        amount = float(amount) if amount else 0
        if amount >= 100000000:
            return f"{amount/100000000:.2f}억"
        elif amount >= 10000:
            return f"{amount/10000:.1f}만"
        else:
            return f"{amount:,.0f}"
    except:
        return "0"

def calculate_stats(trades_df):
    """통계 계산"""
    stats = {
        'total_trades': 0,
        'win_trades': 0,
        'win_rate': 0,
        'total_profit': 0,
        'total_fees': 0,
        'net_profit': 0
    }
    
    if trades_df.empty:
        return stats
    
    completed = trades_df[trades_df['status'] == 'COMPLETED']
    
    if not completed.empty:
        stats['total_trades'] = len(completed)
        stats['win_trades'] = len(completed[completed['profit_rate'] > 0])
        stats['win_rate'] = (stats['win_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
        stats['total_profit'] = completed['profit_loss'].sum()
        stats['total_fees'] = completed['entry_fee'].sum() + completed['exit_fee'].sum()
        stats['net_profit'] = stats['total_profit'] - stats['total_fees']
    
    return stats

# ==================== 메인 ====================
def main():
    # 헤더
    st.markdown("# OMNI TRADING SYSTEM")
    st.markdown("---")
    
    # 데이터 로드
    current_status = load_current_status()
    trades_df = load_trades()
    stats = calculate_stats(trades_df)
    
    # 상단 메트릭
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("KRW 잔고", format_krw(current_status['krw_balance']) + "원")
    
    with col2:
        total_value = sum([h['value'] for h in current_status['holdings']])
        st.metric("보유 자산", format_krw(total_value) + "원")
    
    with col3:
        st.metric("승률", f"{stats['win_rate']:.1f}%" if stats['win_rate'] else "0%")
    
    with col4:
        st.metric("순수익", format_krw(stats['net_profit']) + "원")
    
    # 진행중인 거래
    if not trades_df.empty:
        active_trades = trades_df[trades_df['status'].isin(['PENDING', 'ACTIVE'])]
        
        if not active_trades.empty:
            st.markdown("---")
            st.markdown("### 진행중인 거래")
            
            for _, trade in active_trades.iterrows():
                # 5개 컬럼에서 6개 컬럼으로 확장 (T1, T2 분리 표시)
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.markdown(f"**{trade['coin_ticker']}**")
                    st.caption(f"상태: {trade['status']}")
                
                with col2:
                    if trade['status'] == 'ACTIVE':
                        st.markdown(f"진입가: {format_krw(trade.get('actual_entry_price', 0))}원")
                    else:
                        st.markdown(f"목표 진입: {format_krw(trade['entry_price'])}원")
                
                with col3:
                    # T1 표시
                    t1_status = ""
                    if pd.notna(trade.get('target_1_reached_time')):
                        t1_status = " ✓"
                    st.markdown(f"T1 (70%): {format_krw(trade.get('target_price_1', 0))}원{t1_status}")
                
                with col4:
                    # T2 표시
                    st.markdown(f"T2 (30%): {format_krw(trade.get('target_price_2', 0))}원")
                
                with col5:
                    # 손절가 (본절 이동 여부 표시)
                    sl_status = ""
                    if trade.get('breakeven_stop_moved'):
                        sl_status = " (본절)"
                    st.markdown(f"손절가: {format_krw(trade['stop_loss_price'])}원{sl_status}")
                
                with col6:
                    if trade['status'] == 'ACTIVE' and trade.get('actual_volume'):
                        st.markdown(f"보유: {trade['actual_volume']:.8f}개")
                    else:
                        st.markdown(f"ID: {trade['trade_id'][-8:]}")
    
    # 보유 코인
    if current_status['holdings']:
        st.markdown("---")
        st.markdown("### 보유 코인")
        
        holdings_data = []
        for h in current_status['holdings']:
            pnl_rate = ((h['current_price'] - h['avg_price']) / h['avg_price'] * 100) if h['avg_price'] > 0 else 0
            
            holdings_data.append({
                '코인': h['coin'],
                '수량': f"{h['amount']:.8f}",
                '평균단가': format_krw(h['avg_price']) + "원",
                '현재가': format_krw(h['current_price']) + "원",
                '평가금액': format_krw(h['value']) + "원",
                '수익률': f"{pnl_rate:+.2f}%"
            })
        
        df_holdings = pd.DataFrame(holdings_data)
        st.dataframe(df_holdings, hide_index=True, use_container_width=True)
    
    # 탭
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["거래 내역", "거래 상세", "시스템 정보"])
    
    with tab1:
        st.markdown("### 최근 거래 내역")
        
        if not trades_df.empty:
            # 표시용 데이터 준비
            display_df = trades_df.copy()
            
            # 컬럼 선택 및 포맷팅
            columns_to_show = [
                'timestamp', 'coin_ticker', 'status',
                'actual_entry_price', 'target_price_1', 'target_price_2',
                'actual_exit_price', 'profit_rate', 'profit_loss',
                'entry_fee', 'exit_fee'
            ]
            
            # 존재하는 컬럼만 선택
            available_columns = [col for col in columns_to_show if col in display_df.columns]
            display_df = display_df[available_columns]
            
            # 컬럼명 한글화
            column_mapping = {
                'timestamp': '시작시간',
                'coin_ticker': '코인',
                'status': '상태',
                'actual_entry_price': '진입가',
                'target_price_1': 'T1(70%)',
                'target_price_2': 'T2(30%)',
                'actual_exit_price': '청산가',
                'profit_rate': '수익률(%)',
                'profit_loss': '손익(원)',
                'entry_fee': '진입수수료',
                'exit_fee': '청산수수료'
            }
            
            display_df = display_df.rename(columns=column_mapping)
            
            # 포맷팅
            if '시작시간' in display_df.columns:
                display_df['시작시간'] = display_df['시작시간'].dt.strftime('%m-%d %H:%M')
            
            for col in ['진입가', 'T1(70%)', 'T2(30%)', '청산가', '손익(원)', '진입수수료', '청산수수료']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: format_krw(x) if pd.notna(x) else '-')
            
            if '수익률(%)' in display_df.columns:
                display_df['수익률(%)'] = display_df['수익률(%)'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else '-')
            
            # 최근 20개만 표시
            st.dataframe(display_df.head(20), hide_index=True, use_container_width=True)
            
            # 완료된 거래 통계
            completed = trades_df[trades_df['status'] == 'COMPLETED']
            if not completed.empty:
                st.markdown("---")
                st.markdown("#### 거래 통계")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.text(f"총 거래 횟수: {len(completed)}회")
                    st.text(f"수익 거래: {len(completed[completed['profit_rate'] > 0])}회")
                    st.text(f"손실 거래: {len(completed[completed['profit_rate'] <= 0])}회")
                
                with col2:
                    st.text(f"최대 수익률: {completed['profit_rate'].max():.2f}%")
                    st.text(f"최대 손실률: {completed['profit_rate'].min():.2f}%")
                    st.text(f"평균 수익률: {completed['profit_rate'].mean():.2f}%")
                
                with col3:
                    st.text(f"총 수익/손실: {format_krw(completed['profit_loss'].sum())}원")
                    st.text(f"총 수수료: {format_krw(stats['total_fees'])}원")
                    st.text(f"순수익: {format_krw(stats['net_profit'])}원")
        else:
            st.info("거래 내역이 없습니다")
    
    with tab2:
        st.markdown("### 거래 상세 정보")
        
        if not trades_df.empty:
            # 거래 선택
            trade_ids = trades_df['trade_id'].tolist()
            selected_trade_id = st.selectbox(
                "거래 ID 선택",
                trade_ids,
                format_func=lambda x: f"{x} ({trades_df[trades_df['trade_id']==x].iloc[0]['coin_ticker']} - {trades_df[trades_df['trade_id']==x].iloc[0]['status']})"
            )
            
            if selected_trade_id:
                trade = trades_df[trades_df['trade_id'] == selected_trade_id].iloc[0]
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### 계획")
                    st.text(f"코인: {trade['coin_ticker']}")
                    st.text(f"진입 목표: {format_krw(trade['entry_price'])}원")
                    st.text(f"T1 (70% 청산): {format_krw(trade.get('target_price_1', 0))}원")
                    st.text(f"T2 (30% 추격): {format_krw(trade.get('target_price_2', 0))}원")
                    st.text(f"손절가: {format_krw(trade['stop_loss_price'])}원")
                    
                    if trade['entry_price'] > 0:
                        t1_rate = (trade.get('target_price_1', 0) - trade['entry_price']) / trade['entry_price'] * 100
                        t2_rate = (trade.get('target_price_2', 0) - trade['entry_price']) / trade['entry_price'] * 100
                        stop_rate = (trade['stop_loss_price'] - trade['entry_price']) / trade['entry_price'] * 100
                        st.text(f"T1 목표 수익률: +{t1_rate:.2f}%")
                        st.text(f"T2 목표 수익률: +{t2_rate:.2f}%")
                        st.text(f"손절 수익률: {stop_rate:.2f}%")
                
                with col2:
                    st.markdown("#### 실행")
                    st.text(f"상태: {trade['status']}")
                    
                    if pd.notna(trade.get('actual_entry_price')):
                        st.text(f"실제 진입가: {format_krw(trade['actual_entry_price'])}원")
                        st.text(f"진입 수량: {trade.get('actual_volume', 0):.8f}개")
                        st.text(f"진입 수수료: {format_krw(trade.get('entry_fee', 0))}원")
                    
                    # T1 청산 정보
                    if pd.notna(trade.get('target_1_exit_price')):
                        st.text("---")
                        st.text(f"T1 청산가: {format_krw(trade['target_1_exit_price'])}원")
                        st.text(f"T1 청산량: {trade.get('target_1_exit_volume', 0):.8f}개")
                        if pd.notna(trade.get('target_1_reached_time')):
                            st.text(f"T1 달성: {trade['target_1_reached_time'].strftime('%m-%d %H:%M')}")
                    
                    # T2 청산 정보
                    if pd.notna(trade.get('target_2_exit_price')):
                        st.text("---")
                        st.text(f"T2 청산가: {format_krw(trade['target_2_exit_price'])}원")
                        st.text(f"T2 청산량: {trade.get('target_2_exit_volume', 0):.8f}개")
                    
                    # 최종 결과
                    if pd.notna(trade.get('actual_exit_price')):
                        st.text("---")
                        st.text(f"최종 평균 청산가: {format_krw(trade['actual_exit_price'])}원")
                        st.text(f"청산 수수료: {format_krw(trade.get('exit_fee', 0))}원")
                        st.text(f"손익: {format_krw(trade.get('profit_loss', 0))}원")
                        st.text(f"수익률: {trade.get('profit_rate', 0):.2f}%")
                    
                    # 본절 이동 표시
                    if trade.get('breakeven_stop_moved'):
                        st.text("✓ 손절가 본절 이동됨")
                
                # 타임라인
                st.markdown("---")
                st.markdown("#### 타임라인")
                
                timeline_data = []
                
                timeline_data.append({
                    '시간': trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    '이벤트': '거래 계획 수립'
                })
                
                if pd.notna(trade.get('actual_entry_price')):
                    timeline_data.append({
                        '시간': trade.get('timestamp', trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                        '이벤트': f'진입 완료 ({format_krw(trade["actual_entry_price"])}원)'
                    })
                
                if pd.notna(trade.get('target_1_reached_time')):
                    timeline_data.append({
                        '시간': trade['target_1_reached_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        '이벤트': f'T1 달성 - 70% 청산 ({format_krw(trade.get("target_1_exit_price", 0))}원)'
                    })
                
                if trade.get('breakeven_stop_moved'):
                    timeline_data.append({
                        '시간': '-',
                        '이벤트': '손절가 본절 이동'
                    })
                
                if pd.notna(trade.get('exit_timestamp')):
                    timeline_data.append({
                        '시간': trade['exit_timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                        '이벤트': f'최종 청산 ({trade["status"]})'
                    })
                
                if timeline_data:
                    st.dataframe(pd.DataFrame(timeline_data), hide_index=True, use_container_width=True)
        else:
            st.info("거래 내역이 없습니다")
    
    with tab3:
        st.markdown("### 시스템 정보")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 거래 설정 (V14)")
            st.text(f"최소 신호 점수: 70")
            st.text(f"포지션 크기: 20-97%")
            st.text(f"진입 대기 시간: 1시간")
            st.text(f"T1 청산 비율: 70%")
            st.text(f"T2 추격 비율: 30%")
            st.text(f"최소 R:R 비율: 1:1.5")
        
        with col2:
            st.markdown("#### API 상태")
            st.text(f"Upbit API: 정상")
            st.text(f"Gemini 2.5 Pro: 정상")
            st.text(f"GPT-4o: 정상")
            st.text(f"마지막 업데이트: {current_status['timestamp'].strftime('%H:%M:%S')}")
        
        st.markdown("---")
        st.markdown("#### 시스템 아키텍처 (V14)")
        st.text("Phase 1: Gemini 2.5 Pro - 시장 분석 및 코인 선정")
        st.text("Phase 3: GPT-4o - 2-Target 전략 수립 (T1 70% / T2 30%)")
        st.text("Phase 4: Trade Executor - 분할 익절 자동 실행")
        st.text("  ▸ T1 달성 시: 70% 물량 청산, 손절가를 본절로 이동")
        st.text("  ▸ T2 추격: 나머지 30% 물량으로 추가 수익 추구")
        
        st.markdown("---")
        
        # 새로고침 버튼
        if st.button("새로고침"):
            st.cache_data.clear()
            st.rerun()

if __name__ == "__main__":
    main()