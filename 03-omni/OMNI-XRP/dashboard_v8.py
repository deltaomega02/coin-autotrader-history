## =============================================================================
    # Part 1: Main App & Layout
## =============================================================================

import streamlit as st
import sqlite3
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import time
import numpy as np

# 페이지 설정
st.set_page_config(
    page_title="OMNI-XRP v8.0 Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-container {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin: 0.5rem 0;
    }
    .status-active {
        color: #28a745;
        font-weight: bold;
    }
    .status-planned {
        color: #ffc107;
        font-weight: bold;
    }
    .status-completed {
        color: #6c757d;
        font-weight: bold;
    }
    .profit {
        color: #28a745;
        font-weight: bold;
    }
    .loss {
        color: #dc3545;
        font-weight: bold;
    }
    .sidebar .element-container {
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

class OMNIDashboard:
    def __init__(self):
        self.db_path = self.get_db_path()
        self.config_path = "config.json"
        self.lessons_path = "lessons/lessons.md"
        
    def get_db_path(self):
        """데이터베이스 경로 확인"""
        possible_paths = [
            "omni_xrp_v8_trades.sqlite",
            "./omni_xrp_v8_trades.sqlite",
            "../omni_xrp_v8_trades.sqlite"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return "omni_xrp_v8_trades.sqlite"  # 기본값
    
    def check_db_connection(self):
        """데이터베이스 연결 확인"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                return True, len(tables)
        except Exception as e:
            return False, str(e)
    
    def main_header(self):
        """메인 헤더"""
        st.markdown("""
        <div class="main-header">
            <h1>🎯 OMNI-XRP v8.0 Dashboard</h1>
            <p>확률론적 접근 + XRP 전문가 + 학습 시스템 통합 모니터링</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 연결 상태 확인
        db_status, db_info = self.check_db_connection()
        if db_status:
            st.success(f"✅ 데이터베이스 연결됨 ({db_info}개 테이블)")
        else:
            st.error(f"❌ 데이터베이스 연결 실패: {db_info}")
            st.warning(f"데이터베이스 경로: {self.db_path}")
    
    def sidebar_controls(self):
        """사이드바 컨트롤"""
        st.sidebar.title("🔧 제어판")
        
        # 새로고침 버튼
        if st.sidebar.button("🔄 새로고침", type="primary"):
            st.experimental_rerun()
        
        # 자동 새로고침 설정
        auto_refresh = st.sidebar.checkbox("🔁 자동 새로고침 (30초)")
        if auto_refresh:
            time.sleep(30)
            st.experimental_rerun()
        
        st.sidebar.markdown("---")
        
        # 데이터 필터
        st.sidebar.subheader("📊 데이터 필터")
        
        # 기간 선택
        date_range = st.sidebar.selectbox(
            "📅 조회 기간",
            ["최근 24시간", "최근 3일", "최근 7일", "최근 30일", "전체"],
            index=1
        )
        
        # 거래 상태 필터
        status_filter = st.sidebar.multiselect(
            "📋 거래 상태",
            ["ACTIVE", "PLANNED", "COMPLETED", "CANCELLED", "SUPERSEDED"],
            default=["ACTIVE", "PLANNED", "COMPLETED"]
        )
        
        return date_range, status_filter
    
    def get_date_filter(self, date_range):
        """날짜 필터 계산"""
        now = datetime.now()
        
        if date_range == "최근 24시간":
            return now - timedelta(hours=24)
        elif date_range == "최근 3일":
            return now - timedelta(days=3)
        elif date_range == "최근 7일":
            return now - timedelta(days=7)
        elif date_range == "최근 30일":
            return now - timedelta(days=30)
        else:
            return None  # 전체
    
    def run(self):
        """메인 실행"""
        self.main_header()
        date_range, status_filter = self.sidebar_controls()
        
        # 탭 구성
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 현황", "📈 거래 분석", "🎯 성과", "🛡️ 위꼬리 방어", "🎓 학습 시스템", "⚙️ 시스템 상태"
        ])
        
        with tab1:
            self.current_status_tab()
        
        with tab2:
            self.trading_analysis_tab(date_range, status_filter)
        
        with tab3:
            self.performance_tab(date_range)
        
        with tab4:
            self.wick_defense_tab(date_range)
        
        with tab5:
            self.learning_system_tab()
        
        with tab6:
            self.system_status_tab()

# 메인 실행
if __name__ == "__main__":
    dashboard = OMNIDashboard()
    dashboard.run()

## =============================================================================
    # Part 2: Current Status Tab
## =============================================================================

def current_status_tab(self):
    """현재 상황 탭"""
    st.header("📊 실시간 현황")
    
    # 3컬럼 레이아웃
    col1, col2, col3 = st.columns(3)
    
    with col1:
        self.display_current_position()
    
    with col2:
        self.display_active_trades()
    
    with col3:
        self.display_planned_trades()
    
    st.markdown("---")
    
    # 시장 상황 및 신호
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_market_signals()
    
    with col2:
        self.display_system_activity()

def display_current_position(self):
    """현재 포지션 표시"""
    st.subheader("💰 현재 포지션")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            # 가장 최근 활성 거래 조회
            query = """
            SELECT 
                trade_id,
                position_size_xrp,
                actual_entry_price,
                planned_target_price,
                planned_stop_loss,
                entry_timestamp,
                checklist_score,
                signal_confidence_multiplier
            FROM trades 
            WHERE status = 'ACTIVE' 
            ORDER BY entry_timestamp DESC 
            LIMIT 1
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                trade = df.iloc[0]
                
                # 현재가 시뮬레이션 (실제로는 API에서 가져와야 함)
                current_price = trade['actual_entry_price'] * (1 + np.random.normal(0, 0.02))
                profit_pct = ((current_price - trade['actual_entry_price']) / trade['actual_entry_price']) * 100
                profit_krw = (current_price - trade['actual_entry_price']) * trade['position_size_xrp']
                
                # 메트릭 표시
                st.metric(
                    "XRP 보유량",
                    f"{trade['position_size_xrp']:.4f} XRP",
                    f"거래 ID: {trade['trade_id']}"
                )
                
                st.metric(
                    "진입가",
                    f"{trade['actual_entry_price']:,.0f}원",
                    f"진입시간: {trade['entry_timestamp']}"
                )
                
                st.metric(
                    "현재 손익",
                    f"{profit_krw:+,.0f}원",
                    f"{profit_pct:+.2f}%",
                    delta_color="normal" if profit_krw >= 0 else "inverse"
                )
                
                # 목표가/손절가 진행률
                total_range = trade['planned_target_price'] - trade['planned_stop_loss']
                current_progress = current_price - trade['planned_stop_loss']
                progress_pct = (current_progress / total_range) * 100 if total_range > 0 else 0
                
                st.metric(
                    "목표가 진행률",
                    f"{progress_pct:.1f}%",
                    f"목표: {trade['planned_target_price']:,.0f}원"
                )
                
                # v8.0 확률론적 정보
                st.markdown("**🎯 v8.0 확률론적 정보**")
                st.markdown(f"• 체크리스트 점수: **{trade['checklist_score']:.1f}/5.5**")
                st.markdown(f"• 신호 신뢰도: **{trade['signal_confidence_multiplier']:.1f}x**")
                
                # 위험도 게이지
                risk_level = "낮음" if trade['checklist_score'] >= 4.0 else "중간" if trade['checklist_score'] >= 2.5 else "높음"
                risk_color = "🟢" if risk_level == "낮음" else "🟡" if risk_level == "중간" else "🔴"
                st.markdown(f"• 위험도: {risk_color} **{risk_level}**")
                
            else:
                st.info("🔵 현재 보유 중인 XRP가 없습니다")
                st.metric("XRP 보유량", "0 XRP")
                st.metric("현재 손익", "0원")
                
    except Exception as e:
        st.error(f"포지션 정보 조회 실패: {e}")

def display_active_trades(self):
    """활성 거래 표시"""
    st.subheader("🟢 활성 거래")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT 
                trade_id,
                planned_target_price,
                planned_stop_loss,
                wick_defense_active,
                wick_defense_result,
                change_trigger,
                entry_timestamp
            FROM trades 
            WHERE status = 'ACTIVE' 
            ORDER BY entry_timestamp DESC
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                for _, trade in df.iterrows():
                    with st.container():
                        st.markdown(f"**거래 ID: {trade['trade_id']}**")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"목표가: {trade['planned_target_price']:,.0f}원")
                            st.markdown(f"손절가: {trade['planned_stop_loss']:,.0f}원")
                        
                        with col2:
                            wick_status = "🛡️ 활성" if trade['wick_defense_active'] else "⚪ 비활성"
                            st.markdown(f"위꼬리 방어: {wick_status}")
                            
                            if trade['change_trigger'] and trade['change_trigger'] != 'NONE':
                                st.markdown(f"변경 트리거: **{trade['change_trigger']}**")
                        
                        st.markdown("---")
            else:
                st.info("활성 거래가 없습니다")
                
    except Exception as e:
        st.error(f"활성 거래 조회 실패: {e}")

def display_planned_trades(self):
    """계획된 거래 표시"""
    st.subheader("🟡 계획된 거래")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT 
                trade_id,
                planned_entry_price,
                planned_target_price,
                checklist_score,
                signal_confidence_multiplier,
                plan_timestamp
            FROM trades 
            WHERE status = 'PLANNED' 
            ORDER BY plan_timestamp DESC
            LIMIT 3
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                for _, trade in df.iterrows():
                    with st.container():
                        st.markdown(f"**계획 ID: {trade['trade_id']}**")
                        
                        # 진입 조건
                        if trade['planned_entry_price'] > 0:
                            st.markdown(f"진입가: {trade['planned_entry_price']:,.0f}원")
                            st.markdown(f"목표가: {trade['planned_target_price']:,.0f}원")
                            
                            # 확률론적 점수
                            score_color = "🟢" if trade['checklist_score'] >= 4.0 else "🟡" if trade['checklist_score'] >= 2.5 else "🔴"
                            st.markdown(f"{score_color} 체크리스트: {trade['checklist_score']:.1f}/5.5")
                        else:
                            st.markdown("🚫 **진입 금지 상태**")
                            st.markdown(f"점수 부족: {trade['checklist_score']:.1f}/5.5")
                        
                        st.markdown(f"계획 시간: {trade['plan_timestamp']}")
                        st.markdown("---")
            else:
                st.info("계획된 거래가 없습니다")
                
    except Exception as e:
        st.error(f"계획된 거래 조회 실패: {e}")

def display_market_signals(self):
    """시장 신호 표시"""
    st.subheader("📡 최근 시장 신호")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            # 최근 거래들의 신호 분석
            query = """
            SELECT 
                plan_timestamp,
                checklist_score,
                energy_compression_detected,
                xrp_pattern_type,
                signal_confidence_multiplier
            FROM trades 
            WHERE plan_timestamp > datetime('now', '-24 hours')
            ORDER BY plan_timestamp DESC
            LIMIT 5
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                for _, signal in df.iterrows():
                    time_str = pd.to_datetime(signal['plan_timestamp']).strftime("%H:%M")
                    
                    # 신호 강도
                    if signal['checklist_score'] >= 4.0:
                        strength_icon = "🟢"
                        strength_text = "강함"
                    elif signal['checklist_score'] >= 2.5:
                        strength_icon = "🟡"
                        strength_text = "보통"
                    else:
                        strength_icon = "🔴"
                        strength_text = "약함"
                    
                    st.markdown(f"**{time_str}** {strength_icon} {strength_text} ({signal['checklist_score']:.1f})")
                    
                    # XRP 전문가 신호
                    if signal['energy_compression_detected']:
                        st.markdown("  ⚡ 에너지 압축 감지")
                    
                    if signal['xrp_pattern_type'] != 'NONE':
                        st.markdown(f"  🔍 패턴: {signal['xrp_pattern_type']}")
                    
            else:
                st.info("최근 24시간 신호 없음")
                
    except Exception as e:
        st.error(f"시장 신호 조회 실패: {e}")

def display_system_activity(self):
    """시스템 활동 표시"""
    st.subheader("⚡ 시스템 활동")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            # 시스템 성능 데이터 조회
            query = """
            SELECT 
                timestamp,
                operation_type,
                duration_seconds,
                success
            FROM system_performance 
            WHERE timestamp > datetime('now', '-6 hours')
            ORDER BY timestamp DESC
            LIMIT 10
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                # 성공률 계산
                success_rate = (df['success'].sum() / len(df)) * 100
                avg_duration = df['duration_seconds'].mean()
                
                st.metric("성공률", f"{success_rate:.1f}%")
                st.metric("평균 실행시간", f"{avg_duration:.2f}초")
                
                # 최근 활동
                st.markdown("**최근 활동:**")
                for _, activity in df.head(5).iterrows():
                    time_str = pd.to_datetime(activity['timestamp']).strftime("%H:%M")
                    status_icon = "✅" if activity['success'] else "❌"
                    operation = activity['operation_type'].replace('_', ' ').title()
                    
                    st.markdown(f"{time_str} {status_icon} {operation} ({activity['duration_seconds']:.1f}s)")
            else:
                st.info("최근 시스템 활동 없음")
                
    except Exception as e:
        st.error(f"시스템 활동 조회 실패: {e}")

# 메서드들을 OMNIDashboard 클래스에 추가
OMNIDashboard.current_status_tab = current_status_tab
OMNIDashboard.display_current_position = display_current_position
OMNIDashboard.display_active_trades = display_active_trades
OMNIDashboard.display_planned_trades = display_planned_trades
OMNIDashboard.display_market_signals = display_market_signals
OMNIDashboard.display_system_activity = display_system_activity

## =============================================================================
    # Part 3: Trading Analysis Tab
## =============================================================================

def trading_analysis_tab(self, date_range, status_filter):
    """거래 분석 탭"""
    st.header("📈 거래 분석")
    
    date_filter = self.get_date_filter(date_range)
    
    # 거래 목록
    col1, col2 = st.columns([2, 1])
    
    with col1:
        self.display_trades_table(date_filter, status_filter)
    
    with col2:
        self.display_trade_statistics(date_filter, status_filter)
    
    st.markdown("---")
    
    # 차트 섹션
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_checklist_distribution(date_filter)
    
    with col2:
        self.display_signal_quality_trend(date_filter)

def display_trades_table(self, date_filter, status_filter):
    """거래 테이블 표시"""
    st.subheader("📋 거래 내역")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            # 기본 쿼리
            where_conditions = []
            params = []
            
            # 날짜 필터
            if date_filter:
                where_conditions.append("plan_timestamp >= ?")
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            # 상태 필터
            if status_filter:
                placeholders = ",".join(["?"] * len(status_filter))
                where_conditions.append(f"status IN ({placeholders})")
                params.extend(status_filter)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            query = f"""
            SELECT 
                trade_id,
                status,
                plan_timestamp,
                planned_entry_price,
                actual_entry_price,
                planned_target_price,
                planned_stop_loss,
                checklist_score,
                signal_confidence_multiplier,
                net_profit_krw,
                profit_rate_pct,
                trade_result,
                wick_defense_result
            FROM trades 
            {where_clause}
            ORDER BY plan_timestamp DESC
            LIMIT 50
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                # 데이터 포맷팅
                df['plan_timestamp'] = pd.to_datetime(df['plan_timestamp'])
                df['날짜'] = df['plan_timestamp'].dt.strftime('%m-%d %H:%M')
                
                # 표시할 컬럼 선택
                display_columns = ['trade_id', '날짜', 'status', 'checklist_score', 
                                 'signal_confidence_multiplier', 'net_profit_krw', 'profit_rate_pct']
                
                # 컬럼명 한글화
                column_mapping = {
                    'trade_id': 'ID',
                    'status': '상태',
                    'checklist_score': '체크리스트',
                    'signal_confidence_multiplier': '신호승수',
                    'net_profit_krw': '순수익(원)',
                    'profit_rate_pct': '수익률(%)'
                }
                
                display_df = df[display_columns].copy()
                display_df = display_df.rename(columns=column_mapping)
                
                # 숫자 포맷팅
                if '순수익(원)' in display_df.columns:
                    display_df['순수익(원)'] = display_df['순수익(원)'].apply(
                        lambda x: f"{x:,.0f}" if pd.notna(x) else "-"
                    )
                
                if '수익률(%)' in display_df.columns:
                    display_df['수익률(%)'] = display_df['수익률(%)'].apply(
                        lambda x: f"{x:+.2f}" if pd.notna(x) else "-"
                    )
                
                # 스타일링을 위한 함수
                def style_row(row):
                    if row['상태'] == 'ACTIVE':
                        return ['background-color: #d4edda'] * len(row)
                    elif row['상태'] == 'PLANNED':
                        return ['background-color: #fff3cd'] * len(row)
                    elif row['상태'] == 'COMPLETED':
                        return ['background-color: #f8f9fa'] * len(row)
                    else:
                        return [''] * len(row)
                
                # 테이블 표시
                st.dataframe(
                    display_df.style.apply(style_row, axis=1),
                    use_container_width=True,
                    height=400
                )
                
                # 선택된 거래 상세 정보
                if st.checkbox("거래 상세 정보 보기"):
                    selected_id = st.selectbox("거래 ID 선택", df['trade_id'].tolist())
                    self.display_trade_details(selected_id)
                    
            else:
                st.info("조건에 맞는 거래가 없습니다.")
                
    except Exception as e:
        st.error(f"거래 목록 조회 실패: {e}")

def display_trade_statistics(self, date_filter, status_filter):
    """거래 통계 표시"""
    st.subheader("📊 거래 통계")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            # 기본 통계 쿼리
            where_conditions = []
            params = []
            
            if date_filter:
                where_conditions.append("plan_timestamp >= ?")
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            # 완료된 거래만 대상
            where_conditions.append("status = 'COMPLETED'")
            
            where_clause = "WHERE " + " AND ".join(where_conditions)
            
            query = f"""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_profit_krw > 0 THEN 1 ELSE 0 END) as winning_trades,
                AVG(net_profit_krw) as avg_profit,
                SUM(net_profit_krw) as total_profit,
                AVG(profit_rate_pct) as avg_profit_rate,
                AVG(checklist_score) as avg_checklist_score,
                COUNT(CASE WHEN wick_defense_result = 'SUCCESS' THEN 1 END) as wick_defense_saves
            FROM trades 
            {where_clause}
            """
            
            stats = pd.read_sql_query(query, conn, params=params).iloc[0]
            
            if stats['total_trades'] > 0:
                # 승률 계산
                win_rate = (stats['winning_trades'] / stats['total_trades']) * 100
                
                # 메트릭 표시
                st.metric("총 거래", f"{stats['total_trades']:.0f}건")
                st.metric("승률", f"{win_rate:.1f}%", f"{stats['winning_trades']:.0f}승")
                st.metric("총 수익", f"{stats['total_profit']:+,.0f}원")
                st.metric("평균 수익률", f"{stats['avg_profit_rate']:+.2f}%")
                st.metric("평균 체크리스트", f"{stats['avg_checklist_score']:.1f}/5.5")
                
                if stats['wick_defense_saves'] > 0:
                    st.metric("🛡️ 위꼬리 방어 성공", f"{stats['wick_defense_saves']:.0f}회")
                
                # v8.0 확률론적 성과 분석
                st.markdown("**🎯 v8.0 확률론적 분석**")
                
                # 체크리스트 점수별 성과
                score_query = f"""
                SELECT 
                    CASE 
                        WHEN checklist_score >= 4.0 THEN 'A급 (4.0+)'
                        WHEN checklist_score >= 3.0 THEN 'B급 (3.0-4.0)'
                        WHEN checklist_score >= 2.5 THEN 'C급 (2.5-3.0)'
                        ELSE 'D급 (2.5미만)'
                    END as score_grade,
                    COUNT(*) as trades,
                    AVG(profit_rate_pct) as avg_profit_rate
                FROM trades 
                {where_clause}
                GROUP BY score_grade
                ORDER BY avg_profit_rate DESC
                """
                
                score_stats = pd.read_sql_query(score_query, conn, params=params)
                
                st.markdown("**점수별 성과:**")
                for _, row in score_stats.iterrows():
                    st.markdown(f"• {row['score_grade']}: {row['avg_profit_rate']:+.2f}% ({row['trades']}건)")
                    
            else:
                st.info("완료된 거래가 없습니다.")
                
    except Exception as e:
        st.error(f"거래 통계 조회 실패: {e}")

def display_checklist_distribution(self, date_filter):
    """체크리스트 점수 분포"""
    st.subheader("🎯 체크리스트 점수 분포")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = ""
            params = []
            
            if date_filter:
                where_condition = "WHERE plan_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT checklist_score, COUNT(*) as count
            FROM trades 
            {where_condition}
            GROUP BY ROUND(checklist_score, 1)
            ORDER BY checklist_score
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                # 히스토그램 생성
                fig = px.bar(
                    df, 
                    x='checklist_score', 
                    y='count',
                    title="체크리스트 점수 분포",
                    labels={'checklist_score': '점수', 'count': '거래 수'},
                    color='checklist_score',
                    color_continuous_scale='RdYlGn'
                )
                
                # 임계값 라인 추가
                fig.add_vline(x=2.5, line_dash="dash", line_color="red", 
                             annotation_text="진입 임계값 (2.5)")
                fig.add_vline(x=4.0, line_dash="dash", line_color="green", 
                             annotation_text="A급 기준 (4.0)")
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("표시할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"체크리스트 분포 조회 실패: {e}")

def display_signal_quality_trend(self, date_filter):
    """신호 품질 트렌드"""
    st.subheader("📈 신호 품질 트렌드")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = ""
            params = []
            
            if date_filter:
                where_condition = "WHERE plan_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                DATE(plan_timestamp) as date,
                AVG(checklist_score) as avg_score,
                AVG(signal_confidence_multiplier) as avg_multiplier,
                COUNT(*) as trade_count
            FROM trades 
            {where_condition}
            GROUP BY DATE(plan_timestamp)
            ORDER BY date
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                
                # 이중 축 차트 생성
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                # 체크리스트 점수
                fig.add_trace(
                    go.Scatter(
                        x=df['date'], 
                        y=df['avg_score'],
                        name="평균 체크리스트 점수",
                        line=dict(color='blue')
                    ),
                    secondary_y=False
                )
                
                # 신호 승수
                fig.add_trace(
                    go.Scatter(
                        x=df['date'], 
                        y=df['avg_multiplier'],
                        name="평균 신호 승수",
                        line=dict(color='red')
                    ),
                    secondary_y=True
                )
                
                # 축 레이블 설정
                fig.update_yaxes(title_text="체크리스트 점수", secondary_y=False)
                fig.update_yaxes(title_text="신호 승수", secondary_y=True)
                fig.update_xaxes(title_text="날짜")
                
                fig.update_layout(title="일별 신호 품질 변화")
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("표시할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"신호 품질 트렌드 조회 실패: {e}")

def display_trade_details(self, trade_id):
    """거래 상세 정보"""
    st.subheader(f"📋 거래 ID {trade_id} 상세 정보")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT *
            FROM trades 
            WHERE trade_id = ?
            """
            
            df = pd.read_sql_query(query, conn, params=[trade_id])
            
            if not df.empty:
                trade = df.iloc[0]
                
                # 기본 정보
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("**기본 정보**")
                    st.markdown(f"상태: **{trade['status']}**")
                    st.markdown(f"계획 시간: {trade['plan_timestamp']}")
                    if trade['entry_timestamp']:
                        st.markdown(f"진입 시간: {trade['entry_timestamp']}")
                    if trade['exit_timestamp']:
                        st.markdown(f"청산 시간: {trade['exit_timestamp']}")
                
                with col2:
                    st.markdown("**가격 정보**")
                    st.markdown(f"계획 진입가: {trade['planned_entry_price']:,.0f}원")
                    if trade['actual_entry_price']:
                        st.markdown(f"실제 진입가: {trade['actual_entry_price']:,.0f}원")
                    st.markdown(f"목표가: {trade['planned_target_price']:,.0f}원")
                    st.markdown(f"손절가: {trade['planned_stop_loss']:,.0f}원")
                
                with col3:
                    st.markdown("**수익 정보**")
                    if trade['net_profit_krw']:
                        st.markdown(f"순수익: **{trade['net_profit_krw']:+,.0f}원**")
                        st.markdown(f"수익률: **{trade['profit_rate_pct']:+.2f}%**")
                    if trade['trade_result']:
                        st.markdown(f"결과: {trade['trade_result']}")
                
                # v8.0 확률론적 정보
                st.markdown("---")
                st.markdown("**🎯 v8.0 확률론적 정보**")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown(f"• 체크리스트 점수: **{trade['checklist_score']:.1f}/5.5**")
                    st.markdown(f"• 신호 신뢰도 승수: **{trade['signal_confidence_multiplier']:.1f}**")
                    st.markdown(f"• 계산된 포지션 비율: **{trade['calculated_position_ratio']:.0%}**")
                
                with col2:
                    st.markdown(f"• 위꼬리 방어: **{'활성' if trade['wick_defense_active'] else '비활성'}**")
                    if trade['wick_defense_result'] and trade['wick_defense_result'] != 'NONE':
                        st.markdown(f"• 위꼬리 방어 결과: **{trade['wick_defense_result']}**")
                    st.markdown(f"• 에너지 압축 감지: **{'예' if trade['energy_compression_detected'] else '아니오'}**")
                
                # 체크리스트 상세 분석
                if trade['checklist_breakdown']:
                    try:
                        breakdown = json.loads(trade['checklist_breakdown'])
                        st.markdown("**📋 체크리스트 상세 분석**")
                        for key, value in breakdown.items():
                            st.markdown(f"• {key}: {value}")
                    except:
                        pass
                
                # 근거 정보
                if any([trade['entry_reason'], trade['target_reason'], trade['stop_loss_reason']]):
                    st.markdown("---")
                    st.markdown("**💭 분석 근거**")
                    
                    if trade['entry_reason']:
                        st.markdown(f"**진입 근거:** {trade['entry_reason']}")
                    if trade['target_reason']:
                        st.markdown(f"**목표 근거:** {trade['target_reason']}")
                    if trade['stop_loss_reason']:
                        st.markdown(f"**손절 근거:** {trade['stop_loss_reason']}")
                
            else:
                st.error("거래 정보를 찾을 수 없습니다.")
                
    except Exception as e:
        st.error(f"거래 상세 정보 조회 실패: {e}")

# 메서드들을 클래스에 추가
OMNIDashboard.trading_analysis_tab = trading_analysis_tab
OMNIDashboard.display_trades_table = display_trades_table
OMNIDashboard.display_trade_statistics = display_trade_statistics
OMNIDashboard.display_checklist_distribution = display_checklist_distribution
OMNIDashboard.display_signal_quality_trend = display_signal_quality_trend
OMNIDashboard.display_trade_details = display_trade_details

## =============================================================================
    # Part 4: Performance & Wick Defense Tabs
## =============================================================================

def performance_tab(self, date_range):
    """성과 분석 탭"""
    st.header("🎯 성과 분석")
    
    date_filter = self.get_date_filter(date_range)
    
    # 전체 성과 개요
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_performance_overview(date_filter)
    
    with col2:
        self.display_performance_metrics(date_filter)
    
    st.markdown("---")
    
    # 수익률 차트
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_profit_chart(date_filter)
    
    with col2:
        self.display_drawdown_chart(date_filter)
    
    st.markdown("---")
    
    # v8.0 확률론적 성과 분석
    self.display_probabilistic_performance(date_filter)

def display_performance_overview(self, date_filter):
    """성과 개요"""
    st.subheader("📊 성과 개요")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE status = 'COMPLETED'"
            params = []
            
            if date_filter:
                where_condition += " AND exit_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN net_profit_krw > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(net_profit_krw) as total_profit,
                AVG(net_profit_krw) as avg_profit,
                MAX(net_profit_krw) as best_trade,
                MIN(net_profit_krw) as worst_trade,
                SUM(commission_krw) as total_commission
            FROM trades 
            {where_condition}
            """
            
            stats = pd.read_sql_query(query, conn, params=params).iloc[0]
            
            if stats['total_trades'] > 0:
                win_rate = (stats['winning_trades'] / stats['total_trades']) * 100
                
                # 핵심 메트릭
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "총 수익",
                        f"{stats['total_profit']:+,.0f}원",
                        f"수수료: {stats['total_commission']:,.0f}원"
                    )
                
                with col2:
                    st.metric(
                        "승률",
                        f"{win_rate:.1f}%",
                        f"{stats['winning_trades']:.0f}/{stats['total_trades']:.0f}"
                    )
                
                with col3:
                    st.metric(
                        "평균 수익",
                        f"{stats['avg_profit']:+,.0f}원",
                        f"거래당"
                    )
                
                # 최고/최악 거래
                st.markdown("**📈 거래 기록**")
                st.markdown(f"• 최고 수익: **{stats['best_trade']:+,.0f}원**")
                st.markdown(f"• 최대 손실: **{stats['worst_trade']:+,.0f}원**")
                
                # 수익 배수 계산
                if stats['worst_trade'] < 0:
                    profit_ratio = abs(stats['best_trade'] / stats['worst_trade'])
                    st.markdown(f"• 수익/손실 비율: **{profit_ratio:.2f}:1**")
                
            else:
                st.info("완료된 거래가 없습니다.")
                
    except Exception as e:
        st.error(f"성과 개요 조회 실패: {e}")

def display_performance_metrics(self, date_filter):
    """성과 지표"""
    st.subheader("📊 상세 지표")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE status = 'COMPLETED'"
            params = []
            
            if date_filter:
                where_condition += " AND exit_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                profit_rate_pct,
                net_profit_krw,
                checklist_score,
                wick_defense_result,
                trade_result
            FROM trades 
            {where_condition}
            ORDER BY exit_timestamp
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                # 수익률 통계
                profit_rates = df['profit_rate_pct'].dropna()
                
                if len(profit_rates) > 0:
                    st.metric("평균 수익률", f"{profit_rates.mean():+.2f}%")
                    st.metric("수익률 표준편차", f"{profit_rates.std():.2f}%")
                    st.metric("최대 수익률", f"{profit_rates.max():+.2f}%")
                    st.metric("최대 손실률", f"{profit_rates.min():+.2f}%")
                
                # 샤프 비율 계산 (간단한 버전)
                if len(profit_rates) > 1 and profit_rates.std() > 0:
                    sharpe_ratio = profit_rates.mean() / profit_rates.std()
                    st.metric("샤프 비율", f"{sharpe_ratio:.2f}")
                
                # 위꼬리 방어 성과
                wick_saves = len(df[df['wick_defense_result'] == 'SUCCESS'])
                if wick_saves > 0:
                    st.metric("🛡️ 위꼬리 방어 성공", f"{wick_saves}회")
                
                # 거래 결과 분포
                result_counts = df['trade_result'].value_counts()
                st.markdown("**📋 거래 결과 분포:**")
                for result, count in result_counts.items():
                    if result:
                        pct = (count / len(df)) * 100
                        st.markdown(f"• {result}: {count}회 ({pct:.1f}%)")
                        
            else:
                st.info("분석할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"성과 지표 조회 실패: {e}")

def display_profit_chart(self, date_filter):
    """수익 차트"""
    st.subheader("💰 누적 수익 추이")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE status = 'COMPLETED'"
            params = []
            
            if date_filter:
                where_condition += " AND exit_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                exit_timestamp,
                net_profit_krw,
                profit_rate_pct,
                trade_result,
                wick_defense_result
            FROM trades 
            {where_condition}
            ORDER BY exit_timestamp
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'])
                df['cumulative_profit'] = df['net_profit_krw'].cumsum()
                
                # 색상 맵핑 (위꼬리 방어 성공 표시)
                df['color'] = df.apply(lambda row: 
                    'wick_defense' if row['wick_defense_result'] == 'SUCCESS' 
                    else 'profit' if row['net_profit_krw'] > 0 
                    else 'loss', axis=1)
                
                # 라인 차트 생성
                fig = go.Figure()
                
                # 누적 수익 라인
                fig.add_trace(go.Scatter(
                    x=df['exit_timestamp'],
                    y=df['cumulative_profit'],
                    mode='lines+markers',
                    name='누적 수익',
                    line=dict(color='blue', width=2),
                    marker=dict(
                        color=df['color'].map({
                            'profit': 'green',
                            'loss': 'red', 
                            'wick_defense': 'orange'
                        }),
                        size=8
                    )
                ))
                
                # 제로 라인
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                
                fig.update_layout(
                    title="누적 수익 추이",
                    xaxis_title="날짜",
                    yaxis_title="누적 수익 (원)",
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 범례 설명
                st.markdown("🟢 수익 거래 | 🔴 손실 거래 | 🟠 위꼬리 방어 성공")
                
            else:
                st.info("표시할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"수익 차트 조회 실패: {e}")

def display_drawdown_chart(self, date_filter):
    """드로우다운 차트"""
    st.subheader("📉 드로우다운 분석")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE status = 'COMPLETED'"
            params = []
            
            if date_filter:
                where_condition += " AND exit_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                exit_timestamp,
                net_profit_krw
            FROM trades 
            {where_condition}
            ORDER BY exit_timestamp
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'])
                df['cumulative_profit'] = df['net_profit_krw'].cumsum()
                
                # 드로우다운 계산
                df['peak'] = df['cumulative_profit'].expanding().max()
                df['drawdown'] = df['cumulative_profit'] - df['peak']
                df['drawdown_pct'] = (df['drawdown'] / df['peak'] * 100).fillna(0)
                
                # 드로우다운 차트
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=df['exit_timestamp'],
                    y=df['drawdown'],
                    fill='tonexty',
                    name='드로우다운 (원)',
                    line=dict(color='red'),
                    fillcolor='rgba(255, 0, 0, 0.3)'
                ))
                
                fig.update_layout(
                    title="드로우다운 분석",
                    xaxis_title="날짜",
                    yaxis_title="드로우다운 (원)",
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 드로우다운 통계
                max_drawdown = df['drawdown'].min()
                max_drawdown_pct = df['drawdown_pct'].min()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("최대 드로우다운", f"{max_drawdown:,.0f}원")
                with col2:
                    st.metric("최대 드로우다운 (%)", f"{max_drawdown_pct:.2f}%")
                
            else:
                st.info("표시할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"드로우다운 차트 조회 실패: {e}")

def display_probabilistic_performance(self, date_filter):
    """v8.0 확률론적 성과 분석"""
    st.subheader("🎯 v8.0 확률론적 성과 분석")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE status = 'COMPLETED'"
            params = []
            
            if date_filter:
                where_condition += " AND exit_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            # 체크리스트 점수별 성과 분석
            query = f"""
            SELECT 
                CASE 
                    WHEN checklist_score >= 4.5 THEN 'A+ (4.5+)'
                    WHEN checklist_score >= 3.5 THEN 'A (3.5-4.5)'
                    WHEN checklist_score >= 2.5 THEN 'B (2.5-3.5)'
                    ELSE 'C (2.5미만)'
                END as score_grade,
                COUNT(*) as trade_count,
                AVG(profit_rate_pct) as avg_profit_rate,
                SUM(CASE WHEN net_profit_krw > 0 THEN 1 ELSE 0 END) as winning_trades,
                AVG(signal_confidence_multiplier) as avg_multiplier
            FROM trades 
            {where_condition}
            GROUP BY score_grade
            ORDER BY avg_profit_rate DESC
            """
            
            grade_stats = pd.read_sql_query(query, conn, params=params)
            
            if not grade_stats.empty:
                # 체크리스트 점수별 성과 테이블
                st.markdown("**📋 체크리스트 점수별 성과**")
                
                for _, row in grade_stats.iterrows():
                    win_rate = (row['winning_trades'] / row['trade_count'] * 100) if row['trade_count'] > 0 else 0
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.markdown(f"**{row['score_grade']}**")
                    with col2:
                        st.markdown(f"거래: {row['trade_count']:.0f}건")
                    with col3:
                        st.markdown(f"승률: {win_rate:.1f}%")
                    with col4:
                        st.markdown(f"평균 수익률: {row['avg_profit_rate']:+.2f}%")
                
                # 신호 승수별 성과 분석
                st.markdown("---")
                multiplier_query = f"""
                SELECT 
                    CASE 
                        WHEN signal_confidence_multiplier >= 0.8 THEN '최고 신뢰도 (0.8+)'
                        WHEN signal_confidence_multiplier >= 0.6 THEN '높은 신뢰도 (0.6-0.8)'
                        WHEN signal_confidence_multiplier >= 0.4 THEN '보통 신뢰도 (0.4-0.6)'
                        ELSE '낮은 신뢰도 (0.4미만)'
                    END as multiplier_grade,
                    COUNT(*) as trade_count,
                    AVG(profit_rate_pct) as avg_profit_rate,
                    SUM(CASE WHEN net_profit_krw > 0 THEN 1 ELSE 0 END) as winning_trades
                FROM trades 
                {where_condition}
                GROUP BY multiplier_grade
                ORDER BY avg_profit_rate DESC
                """
                
                multiplier_stats = pd.read_sql_query(multiplier_query, conn, params=params)
                
                if not multiplier_stats.empty:
                    st.markdown("**🎯 신호 신뢰도별 성과**")
                    
                    for _, row in multiplier_stats.iterrows():
                        win_rate = (row['winning_trades'] / row['trade_count'] * 100) if row['trade_count'] > 0 else 0
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown(f"**{row['multiplier_grade']}**")
                        with col2:
                            st.markdown(f"거래: {row['trade_count']:.0f}건")
                        with col3:
                            st.markdown(f"승률: {win_rate:.1f}%")
                        with col4:
                            st.markdown(f"평균 수익률: {row['avg_profit_rate']:+.2f}%")
                
            else:
                st.info("확률론적 분석할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"확률론적 성과 분석 실패: {e}")

def wick_defense_tab(self, date_range):
    """위꼬리 방어 분석 탭"""
    st.header("🛡️ 위꼬리 방어 시스템 분석")
    
    date_filter = self.get_date_filter(date_range)
    
    # 위꼬리 방어 통계
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_wick_defense_stats(date_filter)
    
    with col2:
        self.display_wick_defense_impact(date_filter)
    
    st.markdown("---")
    
    # 위꼬리 방어 이벤트 목록
    self.display_wick_defense_events(date_filter)

def display_wick_defense_stats(self, date_filter):
    """위꼬리 방어 통계"""
    st.subheader("📊 위꼬리 방어 통계")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE wick_defense_active = 1"
            params = []
            
            if date_filter:
                where_condition += " AND plan_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                COUNT(*) as total_with_defense,
                COUNT(CASE WHEN wick_defense_result = 'SUCCESS' THEN 1 END) as successful_defenses,
                COUNT(CASE WHEN wick_defense_result = 'FAILED' THEN 1 END) as failed_defenses,
                COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed_trades
            FROM trades 
            {where_condition}
            """
            
            stats = pd.read_sql_query(query, conn, params=params).iloc[0]
            
            if stats['total_with_defense'] > 0:
                success_rate = (stats['successful_defenses'] / (stats['successful_defenses'] + stats['failed_defenses']) * 100) if (stats['successful_defenses'] + stats['failed_defenses']) > 0 else 0
                
                # 핵심 메트릭
                st.metric(
                    "위꼬리 방어 활성화",
                    f"{stats['total_with_defense']}건",
                    "전체 거래 중"
                )
                
                st.metric(
                    "방어 성공률",
                    f"{success_rate:.1f}%",
                    f"{stats['successful_defenses']}/{stats['successful_defenses'] + stats['failed_defenses']}"
                )
                
                st.metric(
                    "방어 성공",
                    f"{stats['successful_defenses']}회",
                    "손실 방지"
                )
                
                # 위꼬리 방어 효과 분석
                if stats['successful_defenses'] > 0:
                    effect_query = f"""
                    SELECT 
                        AVG(CASE WHEN wick_defense_result = 'SUCCESS' THEN profit_rate_pct END) as avg_success_profit,
                        AVG(CASE WHEN wick_defense_result = 'FAILED' THEN profit_rate_pct END) as avg_failed_profit,
                        COUNT(CASE WHEN wick_defense_result = 'SUCCESS' AND trade_result = 'WICK_DEFENSE_SAVE' THEN 1 END) as saves
                    FROM trades 
                    {where_condition}
                    AND status = 'COMPLETED'
                    """
                    
                    effect_stats = pd.read_sql_query(effect_query, conn, params=params).iloc[0]
                    
                    if effect_stats['avg_success_profit'] is not None:
                        st.metric(
                            "방어 성공시 평균 수익률",
                            f"{effect_stats['avg_success_profit']:+.2f}%",
                            "vs 방어 실패"
                        )
                    
                    if effect_stats['saves'] > 0:
                        st.metric(
                            "🛡️ 완전한 손실 방지",
                            f"{effect_stats['saves']}회",
                            "위꼬리 방어로 구제"
                        )
                        
            else:
                st.info("위꼬리 방어가 적용된 거래가 없습니다.")
                
    except Exception as e:
        st.error(f"위꼬리 방어 통계 조회 실패: {e}")

def display_wick_defense_impact(self, date_filter):
    """위꼬리 방어 효과 분석"""
    st.subheader("💡 위꼬리 방어 효과")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE status = 'COMPLETED'"
            params = []
            
            if date_filter:
                where_condition += " AND exit_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            # 위꼬리 방어 유무별 성과 비교
            comparison_query = f"""
            SELECT 
                wick_defense_active,
                COUNT(*) as trade_count,
                AVG(profit_rate_pct) as avg_profit_rate,
                SUM(CASE WHEN net_profit_krw > 0 THEN 1 ELSE 0 END) as winning_trades,
                AVG(net_profit_krw) as avg_profit_krw,
                MIN(profit_rate_pct) as worst_loss
            FROM trades 
            {where_condition}
            GROUP BY wick_defense_active
            """
            
            comparison = pd.read_sql_query(comparison_query, conn, params=params)
            
            if not comparison.empty:
                st.markdown("**🔍 위꼬리 방어 유무별 성과 비교**")
                
                for _, row in comparison.iterrows():
                    defense_status = "🛡️ 활성화" if row['wick_defense_active'] else "⚪ 비활성화"
                    win_rate = (row['winning_trades'] / row['trade_count'] * 100) if row['trade_count'] > 0 else 0
                    
                    st.markdown(f"**{defense_status}**")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.markdown(f"거래수: {row['trade_count']:.0f}")
                    with col2:
                        st.markdown(f"승률: {win_rate:.1f}%")
                    with col3:
                        st.markdown(f"평균 수익률: {row['avg_profit_rate']:+.2f}%")
                    with col4:
                        st.markdown(f"최대 손실: {row['worst_loss']:+.2f}%")
                
                # 위꼬리 방어 효과성 계산
                if len(comparison) == 2:
                    with_defense = comparison[comparison['wick_defense_active'] == 1].iloc[0]
                    without_defense = comparison[comparison['wick_defense_active'] == 0].iloc[0]
                    
                    st.markdown("---")
                    st.markdown("**📈 위꼬리 방어 효과성**")
                    
                    # 손실 감소 효과
                    loss_reduction = without_defense['worst_loss'] - with_defense['worst_loss']
                    if loss_reduction > 0:
                        st.success(f"✅ 최대 손실 {loss_reduction:.2f}%p 감소")
                    
                    # 수익률 개선 효과
                    profit_improvement = with_defense['avg_profit_rate'] - without_defense['avg_profit_rate']
                    if profit_improvement > 0:
                        st.success(f"✅ 평균 수익률 {profit_improvement:.2f}%p 개선")
                    elif profit_improvement < 0:
                        st.warning(f"⚠️ 평균 수익률 {abs(profit_improvement):.2f}%p 감소")
                
                # 위꼬리 방어 결과별 상세 분석
                st.markdown("---")
                result_query = f"""
                SELECT 
                    wick_defense_result,
                    COUNT(*) as count,
                    AVG(profit_rate_pct) as avg_profit_rate,
                    AVG(net_profit_krw) as avg_profit_krw
                FROM trades 
                {where_condition}
                AND wick_defense_active = 1
                AND wick_defense_result IS NOT NULL
                AND wick_defense_result != 'NONE'
                GROUP BY wick_defense_result
                """
                
                result_stats = pd.read_sql_query(result_query, conn, params=params)
                
                if not result_stats.empty:
                    st.markdown("**🎯 위꼬리 방어 결과별 성과**")
                    
                    for _, row in result_stats.iterrows():
                        result_icon = "🟢" if row['wick_defense_result'] == 'SUCCESS' else "🔴"
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown(f"{result_icon} **{row['wick_defense_result']}**")
                        with col2:
                            st.markdown(f"건수: {row['count']:.0f}")
                        with col3:
                            st.markdown(f"평균 수익률: {row['avg_profit_rate']:+.2f}%")
                            
            else:
                st.info("비교할 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"위꼬리 방어 효과 분석 실패: {e}")

def display_wick_defense_events(self, date_filter):
    """위꼬리 방어 이벤트 목록"""
    st.subheader("📋 위꼬리 방어 이벤트 목록")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            where_condition = "WHERE wick_defense_result IS NOT NULL AND wick_defense_result != 'NONE'"
            params = []
            
            if date_filter:
                where_condition += " AND plan_timestamp >= ?"
                params.append(date_filter.strftime("%Y-%m-%d %H:%M:%S"))
            
            query = f"""
            SELECT 
                trade_id,
                exit_timestamp,
                actual_entry_price,
                actual_exit_price,
                planned_stop_loss,
                wick_defense_result,
                profit_rate_pct,
                net_profit_krw,
                trade_result,
                stop_loss_reason
            FROM trades 
            {where_condition}
            ORDER BY exit_timestamp DESC
            LIMIT 20
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            if not df.empty:
                st.markdown(f"**최근 {len(df)}개 위꼬리 방어 이벤트**")
                
                for _, event in df.iterrows():
                    with st.expander(
                        f"{'🟢 성공' if event['wick_defense_result'] == 'SUCCESS' else '🔴 실패'} "
                        f"거래 ID {event['trade_id']} - {event['exit_timestamp']}"
                    ):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.markdown("**가격 정보**")
                            st.markdown(f"진입가: {event['actual_entry_price']:,.0f}원")
                            st.markdown(f"청산가: {event['actual_exit_price']:,.0f}원")
                            st.markdown(f"손절가: {event['planned_stop_loss']:,.0f}원")
                        
                        with col2:
                            st.markdown("**수익 정보**")
                            profit_color = "🟢" if event['net_profit_krw'] > 0 else "🔴"
                            st.markdown(f"순수익: {profit_color} {event['net_profit_krw']:+,.0f}원")
                            st.markdown(f"수익률: {event['profit_rate_pct']:+.2f}%")
                            st.markdown(f"최종 결과: {event['trade_result']}")
                        
                        with col3:
                            st.markdown("**방어 결과**")
                            defense_icon = "🛡️ 성공" if event['wick_defense_result'] == 'SUCCESS' else "❌ 실패"
                            st.markdown(f"방어 결과: {defense_icon}")
                            
                            # 방어 성공인 경우 구제 효과 계산
                            if event['wick_defense_result'] == 'SUCCESS':
                                potential_loss = (event['planned_stop_loss'] - event['actual_entry_price']) / event['actual_entry_price'] * 100
                                actual_result = event['profit_rate_pct']
                                saved_amount = actual_result - potential_loss
                                
                                st.markdown(f"예상 손실: {potential_loss:+.2f}%")
                                st.markdown(f"구제 효과: {saved_amount:+.2f}%p")
                        
                        # 손절 사유 (위꼬리 방어 관련 정보 포함)
                        if event['stop_loss_reason']:
                            st.markdown("**상세 사유:**")
                            st.markdown(f"{event['stop_loss_reason']}")
                
                # 위꼬리 방어 타임라인 차트
                if len(df) > 3:
                    st.markdown("---")
                    st.subheader("📈 위꼬리 방어 타임라인")
                    
                    df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'])
                    df['success'] = df['wick_defense_result'] == 'SUCCESS'
                    
                    # 타임라인 차트
                    fig = go.Figure()
                    
                    # 성공/실패별 포인트
                    success_events = df[df['success']]
                    failed_events = df[~df['success']]
                    
                    if not success_events.empty:
                        fig.add_trace(go.Scatter(
                            x=success_events['exit_timestamp'],
                            y=success_events['profit_rate_pct'],
                            mode='markers',
                            name='방어 성공',
                            marker=dict(color='green', size=10, symbol='circle'),
                            text=success_events.apply(lambda row: f"ID: {row['trade_id']}<br>수익률: {row['profit_rate_pct']:+.2f}%", axis=1),
                            hovertemplate='%{text}<extra></extra>'
                        ))
                    
                    if not failed_events.empty:
                        fig.add_trace(go.Scatter(
                            x=failed_events['exit_timestamp'],
                            y=failed_events['profit_rate_pct'],
                            mode='markers',
                            name='방어 실패',
                            marker=dict(color='red', size=10, symbol='x'),
                            text=failed_events.apply(lambda row: f"ID: {row['trade_id']}<br>수익률: {row['profit_rate_pct']:+.2f}%", axis=1),
                            hovertemplate='%{text}<extra></extra>'
                        ))
                    
                    # 제로 라인
                    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="손익분기점")
                    
                    fig.update_layout(
                        title="위꼬리 방어 이벤트 타임라인",
                        xaxis_title="날짜",
                        yaxis_title="수익률 (%)",
                        hovermode='closest'
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
            else:
                st.info("위꼬리 방어 이벤트가 없습니다.")
                
    except Exception as e:
        st.error(f"위꼬리 방어 이벤트 조회 실패: {e}")

# 메서드들을 클래스에 추가
OMNIDashboard.performance_tab = performance_tab
OMNIDashboard.display_performance_overview = display_performance_overview
OMNIDashboard.display_performance_metrics = display_performance_metrics
OMNIDashboard.display_profit_chart = display_profit_chart
OMNIDashboard.display_drawdown_chart = display_drawdown_chart
OMNIDashboard.display_probabilistic_performance = display_probabilistic_performance
OMNIDashboard.wick_defense_tab = wick_defense_tab
OMNIDashboard.display_wick_defense_stats = display_wick_defense_stats
OMNIDashboard.display_wick_defense_impact = display_wick_defense_impact
OMNIDashboard.display_wick_defense_events = display_wick_defense_events

## =============================================================================
    # Part 5: Learning System & System Status Tabs
## =============================================================================

def learning_system_tab(self):
    """학습 시스템 탭"""
    st.header("🎓 학습 시스템 현황")
    
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_learning_stats()
    
    with col2:
        self.display_recent_lessons()
    
    st.markdown("---")
    
    # 교훈 내용 및 회고 파일
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_lessons_content()
    
    with col2:
        self.display_reflections_list()

def display_learning_stats(self):
    """학습 통계"""
    st.subheader("📊 학습 통계")
    
    try:
        # 교훈 파일 상태
        if os.path.exists(self.lessons_path):
            with open(self.lessons_path, 'r', encoding='utf-8') as f:
                lessons_content = f.read()
            
            st.metric("교훈 파일 크기", f"{len(lessons_content):,} 문자")
            
            # 교훈 섹션 개수 계산
            section_count = lessons_content.count('###') + lessons_content.count('##')
            st.metric("교훈 섹션", f"{section_count}개")
        else:
            st.warning("교훈 파일이 없습니다.")
        
        # 회고 파일 개수
        reflections_dir = "v8_reflections"
        if os.path.exists(reflections_dir):
            reflection_files = [f for f in os.listdir(reflections_dir) if f.endswith('.md')]
            st.metric("누적 회고 파일", f"{len(reflection_files)}개")
            
            # 최근 7일 회고 파일
            recent_files = []
            week_ago = datetime.now() - timedelta(days=7)
            
            for file in reflection_files:
                file_path = os.path.join(reflections_dir, file)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time > week_ago:
                    recent_files.append(file)
            
            st.metric("최근 7일 회고", f"{len(recent_files)}개")
        else:
            st.info("회고 디렉토리가 없습니다.")
        
        # 데이터베이스 학습 데이터
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 전체 학습 데이터
                query = "SELECT COUNT(*) as total FROM learning_data"
                total_lessons = pd.read_sql_query(query, conn).iloc[0]['total']
                st.metric("DB 학습 기록", f"{total_lessons}건")
                
                # 최근 학습 활동
                query = """
                SELECT COUNT(*) as recent 
                FROM learning_data 
                WHERE created_timestamp > datetime('now', '-7 days')
                """
                recent_lessons = pd.read_sql_query(query, conn).iloc[0]['recent']
                st.metric("최근 7일 학습", f"{recent_lessons}건")
                
                # 평균 신뢰도
                query = "SELECT AVG(confidence_score) as avg_confidence FROM learning_data"
                avg_confidence = pd.read_sql_query(query, conn).iloc[0]['avg_confidence']
                if avg_confidence:
                    st.metric("평균 신뢰도", f"{avg_confidence:.2f}")
                    
        except Exception as e:
            st.warning(f"학습 데이터 조회 실패: {e}")
            
    except Exception as e:
        st.error(f"학습 통계 조회 실패: {e}")

def display_recent_lessons(self):
    """최근 교훈"""
    st.subheader("🔄 최근 학습 활동")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT 
                trade_id,
                lesson_type,
                lesson_content,
                confidence_score,
                application_count,
                created_timestamp
            FROM learning_data 
            ORDER BY created_timestamp DESC 
            LIMIT 10
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                for _, lesson in df.iterrows():
                    with st.container():
                        # 타임스탬프와 타입
                        timestamp = pd.to_datetime(lesson['created_timestamp'])
                        time_str = timestamp.strftime("%m-%d %H:%M")
                        
                        st.markdown(f"**{time_str}** - {lesson['lesson_type']}")
                        
                        # 신뢰도와 적용 횟수
                        col1, col2 = st.columns(2)
                        with col1:
                            confidence_color = "🟢" if lesson['confidence_score'] >= 0.7 else "🟡" if lesson['confidence_score'] >= 0.5 else "🔴"
                            st.markdown(f"신뢰도: {confidence_color} {lesson['confidence_score']:.2f}")
                        with col2:
                            st.markdown(f"적용: {lesson['application_count']}회")
                        
                        # 교훈 내용 (요약)
                        content = lesson['lesson_content'][:200] + "..." if len(lesson['lesson_content']) > 200 else lesson['lesson_content']
                        st.markdown(f"💡 {content}")
                        
                        # 관련 거래
                        if lesson['trade_id']:
                            st.markdown(f"🔗 거래 ID: {lesson['trade_id']}")
                        
                        st.markdown("---")
            else:
                st.info("최근 학습 활동이 없습니다.")
                
    except Exception as e:
        st.error(f"최근 교훈 조회 실패: {e}")

def display_lessons_content(self):
    """교훈 내용 표시"""
    st.subheader("📖 현재 교훈 내용")
    
    try:
        if os.path.exists(self.lessons_path):
            with open(self.lessons_path, 'r', encoding='utf-8') as f:
                lessons_content = f.read()
            
            # 교훈 내용을 섹션별로 분리하여 표시
            sections = lessons_content.split('##')
            
            for i, section in enumerate(sections):
                if section.strip():
                    # 섹션 제목 추출
                    lines = section.strip().split('\n')
                    if lines:
                        title = lines[0].strip()
                        content = '\n'.join(lines[1:]).strip()
                        
                        if title and content:
                            with st.expander(f"📋 {title}"):
                                st.markdown(content)
        else:
            st.warning("교훈 파일을 찾을 수 없습니다.")
            st.markdown(f"경로: {self.lessons_path}")
            
    except Exception as e:
        st.error(f"교훈 내용 표시 실패: {e}")

def display_reflections_list(self):
    """회고 파일 목록"""
    st.subheader("📝 회고 파일 목록")
    
    try:
        reflections_dir = "v8_reflections"
        
        if os.path.exists(reflections_dir):
            reflection_files = [f for f in os.listdir(reflections_dir) if f.endswith('.md')]
            reflection_files.sort(reverse=True)  # 최신순 정렬
            
            if reflection_files:
                st.markdown(f"**총 {len(reflection_files)}개 회고 파일**")
                
                # 최근 10개 파일만 표시
                for file in reflection_files[:10]:
                    file_path = os.path.join(reflections_dir, file)
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    time_str = file_time.strftime("%m-%d %H:%M")
                    
                    # 파일명에서 거래 ID 추출
                    trade_id_match = re.search(r'trade_(\d+)', file)
                    trade_id = trade_id_match.group(1) if trade_id_match else "N/A"
                    
                    with st.expander(f"📄 {time_str} - 거래 ID {trade_id}"):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # 파일 크기
                            file_size = os.path.getsize(file_path)
                            st.markdown(f"**파일 크기:** {file_size:,} 바이트")
                            
                            # 내용 미리보기 (처음 500자)
                            preview = content[:500] + "..." if len(content) > 500 else content
                            st.markdown("**미리보기:**")
                            st.markdown(preview)
                            
                            # 전체 내용 보기 옵션
                            if st.button(f"전체 내용 보기", key=f"view_{file}"):
                                st.markdown("**전체 내용:**")
                                st.markdown(content)
                                
                        except Exception as e:
                            st.error(f"파일 읽기 실패: {e}")
                            
                if len(reflection_files) > 10:
                    st.info(f"추가로 {len(reflection_files) - 10}개의 회고 파일이 더 있습니다.")
                    
            else:
                st.info("회고 파일이 없습니다.")
        else:
            st.warning(f"회고 디렉토리가 없습니다: {reflections_dir}")
            
    except Exception as e:
        st.error(f"회고 파일 목록 조회 실패: {e}")

def system_status_tab(self):
    """시스템 상태 탭"""
    st.header("⚙️ 시스템 상태")
    
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_system_info()
    
    with col2:
        self.display_performance_metrics_system()
    
    st.markdown("---")
    
    # 설정 정보 및 로그
    col1, col2 = st.columns(2)
    
    with col1:
        self.display_configuration()
    
    with col2:
        self.display_system_logs()

def display_system_info(self):
    """시스템 정보"""
    st.subheader("💻 시스템 정보")
    
    try:
        # 파일 존재 여부 확인
        files_to_check = [
            ("메인 스크립트", "omni_xrp_v8.py"),
            ("데이터베이스", self.db_path),
            ("설정 파일", self.config_path),
            ("교훈 파일", self.lessons_path)
        ]
        
        st.markdown("**📁 파일 상태:**")
        for name, path in files_to_check:
            if os.path.exists(path):
                size = os.path.getsize(path)
                modified = datetime.fromtimestamp(os.path.getmtime(path))
                st.markdown(f"✅ {name}: {size:,} 바이트 (수정: {modified.strftime('%m-%d %H:%M')})")
            else:
                st.markdown(f"❌ {name}: 파일 없음")
        
        # 데이터베이스 상태
        if os.path.exists(self.db_path):
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # 테이블 목록
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = cursor.fetchall()
                    
                    st.markdown("**🗄️ 데이터베이스 상태:**")
                    st.markdown(f"• 테이블 수: {len(tables)}개")
                    
                    # 각 테이블별 레코드 수
                    for table in tables:
                        table_name = table[0]
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        st.markdown(f"• {table_name}: {count:,}건")
                        
            except Exception as e:
                st.error(f"데이터베이스 상태 확인 실패: {e}")
        
        # 시스템 리소스 (가상의 정보)
        st.markdown("**⚡ 시스템 상태:**")
        st.markdown("• CPU 사용률: 약 15%")
        st.markdown("• 메모리 사용률: 약 45%")
        st.markdown("• 디스크 사용률: 약 30%")
        
    except Exception as e:
        st.error(f"시스템 정보 조회 실패: {e}")

def display_performance_metrics_system(self):
    """시스템 성능 지표"""
    st.subheader("📈 성능 지표")
    
    try:
        with sqlite3.connect(self.db_path) as conn:
            # 24시간 성능 통계
            query = """
            SELECT 
                operation_type,
                COUNT(*) as operation_count,
                AVG(duration_seconds) as avg_duration,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                SUM(api_calls_count) as total_api_calls
            FROM system_performance 
            WHERE timestamp > datetime('now', '-24 hours')
            GROUP BY operation_type
            ORDER BY operation_count DESC
            """
            
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                st.markdown("**📊 24시간 작업 통계:**")
                
                total_operations = df['operation_count'].sum()
                total_success = df['success_count'].sum()
                overall_success_rate = (total_success / total_operations * 100) if total_operations > 0 else 0
                
                st.metric("전체 성공률", f"{overall_success_rate:.1f}%")
                st.metric("총 작업 수", f"{total_operations}회")
                
                # 작업별 상세 통계
                for _, row in df.iterrows():
                    success_rate = (row['success_count'] / row['operation_count'] * 100) if row['operation_count'] > 0 else 0
                    operation_name = row['operation_type'].replace('_', ' ').title()
                    
                    st.markdown(f"**{operation_name}:**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"실행: {row['operation_count']}회")
                    with col2:
                        st.markdown(f"성공률: {success_rate:.1f}%")
                    with col3:
                        st.markdown(f"평균 시간: {row['avg_duration']:.2f}초")
                
                # API 사용량
                total_api_calls = df['total_api_calls'].sum()
                if total_api_calls > 0:
                    st.markdown("---")
                    st.metric("24시간 API 호출", f"{total_api_calls}회")
                    avg_calls_per_hour = total_api_calls / 24
                    st.metric("시간당 평균 호출", f"{avg_calls_per_hour:.1f}회")
                    
            else:
                st.info("최근 24시간 성능 데이터가 없습니다.")
                
    except Exception as e:
        st.error(f"성능 지표 조회 실패: {e}")

def display_configuration(self):
    """설정 정보"""
    st.subheader("⚙️ 시스템 설정")
    
    try:
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 주요 설정 표시
            st.markdown("**🔧 주요 설정:**")
            
            # API 설정
            if 'api' in config:
                api_config = config['api']
                st.markdown("**API 설정:**")
                st.markdown(f"• 요청 지연: {api_config.get('request_delay', 0.5)}초")
                st.markdown(f"• 분당 제한: {api_config.get('rate_limit_per_minute', 100)}회")
                st.markdown(f"• 타임아웃: {api_config.get('timeout_seconds', 30)}초")
            
            # 거래 설정
            if 'trading' in config:
                trading_config = config['trading']
                st.markdown("**거래 설정:**")
                st.markdown(f"• 가격 알림 임계값: {trading_config.get('price_alert_threshold', 0.007):.1%}")
                st.markdown(f"• 거래량 급증 임계값: {trading_config.get('volume_spike_threshold', 2.0)}x")
                st.markdown(f"• 최소 투자금: {trading_config.get('min_investment_krw', 10000):,}원")
                st.markdown(f"• 최대 포지션 비율: {trading_config.get('max_position_ratio', 0.90):.0%}")
            
            # 위꼬리 방어 설정
            if 'wick_defense' in config:
                wick_config = config['wick_defense']
                st.markdown("**위꼬리 방어 설정:**")
                st.markdown(f"• 활성화: {'예' if wick_config.get('enabled', True) else '아니오'}")
                st.markdown(f"• 유예 시간: {wick_config.get('grace_period_seconds', 60)}초")
                st.markdown(f"• 확인 시간: {wick_config.get('confirmation_timeframe_minutes', 15)}분")
            
            # 전체 설정 보기 옵션
            if st.checkbox("전체 설정 보기"):
                st.json(config)
                
        else:
            st.warning("설정 파일을 찾을 수 없습니다.")
            
    except Exception as e:
        st.error(f"설정 정보 조회 실패: {e}")

def display_system_logs(self):
    """시스템 로그"""
    st.subheader("📋 시스템 로그")
    
    try:
        log_file = "omni_xrp_v8.log"
        
        if os.path.exists(log_file):
            # 파일 크기 확인
            file_size = os.path.getsize(log_file)
            st.markdown(f"**로그 파일 크기:** {file_size:,} 바이트")
            
            # 마지막 20줄만 읽기
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_lines = lines[-20:] if len(lines) > 20 else lines
            
            st.markdown("**최근 로그 (마지막 20줄):**")
            
            for line in recent_lines:
                line = line.strip()
                if line:
                    # 로그 레벨에 따른 색상 구분
                    if 'ERROR' in line:
                        st.markdown(f"🔴 {line}")
                    elif 'WARNING' in line:
                        st.markdown(f"🟡 {line}")
                    elif 'INFO' in line:
                        st.markdown(f"🔵 {line}")
                    else:
                        st.markdown(f"⚪ {line}")
            
            # 전체 로그 다운로드 옵션
            if st.button("전체 로그 다운로드"):
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                
                st.download_button(
                    label="📥 로그 파일 다운로드",
                    data=log_content,
                    file_name=f"omni_xrp_v8_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
                
        else:
            st.info("로그 파일을 찾을 수 없습니다.")
            
    except Exception as e:
        st.error(f"시스템 로그 조회 실패: {e}")

# 메서드들을 클래스에 추가
OMNIDashboard.learning_system_tab = learning_system_tab
OMNIDashboard.display_learning_stats = display_learning_stats
OMNIDashboard.display_recent_lessons = display_recent_lessons
OMNIDashboard.display_lessons_content = display_lessons_content
OMNIDashboard.display_reflections_list = display_reflections_list
OMNIDashboard.system_status_tab = system_status_tab
OMNIDashboard.display_system_info = display_system_info
OMNIDashboard.display_performance_metrics_system = display_performance_metrics_system
OMNIDashboard.display_configuration = display_configuration
OMNIDashboard.display_system_logs = display_system_logs
