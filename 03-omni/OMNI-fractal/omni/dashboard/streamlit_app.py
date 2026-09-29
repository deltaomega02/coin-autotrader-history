# dashboard/streamlit_app.py
# OMNI 대시보드 - Streamlit 앱

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time
import sqlite3
import json
from pathlib import Path
import sys
import os

sys.path.append(str(Path(__file__).parent.parent))

from data.database import TradeDatabase
from data.upbit_client import UpbitClient
from core.reflector import Reflector
from config.settings import settings

# 페이지 설정
st.set_page_config(
    page_title="OMNI Trading System",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600;700;800&display=swap');
    
    /* 🤍 CLEAN WHITE BACKGROUND WITH SUBTLE TEXTURE */
    .stApp {
        background: 
            radial-gradient(circle at 20% 80%, rgba(59, 130, 246, 0.03) 0%, transparent 50%),
            radial-gradient(circle at 80% 20%, rgba(16, 185, 129, 0.02) 0%, transparent 50%),
            radial-gradient(circle at 40% 40%, rgba(139, 92, 246, 0.025) 0%, transparent 50%),
            #ffffff;
        min-height: 100vh;
        position: fixed;
        width: 100%;
        top: 0;
        left: 0;
        z-index: -1;
    }
    
    /* 🌟 SUBTLE FLOATING PARTICLES FOR DEPTH */
    .stApp::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image: 
            radial-gradient(1px 1px at 20% 30%, rgba(59, 130, 246, 0.1), transparent),
            radial-gradient(1px 1px at 40% 70%, rgba(16, 185, 129, 0.08), transparent),
            radial-gradient(1px 1px at 60% 15%, rgba(139, 92, 246, 0.06), transparent),
            radial-gradient(1px 1px at 80% 85%, rgba(236, 72, 153, 0.05), transparent),
            radial-gradient(1px 1px at 90% 40%, rgba(59, 130, 246, 0.04), transparent);
        background-size: 400px 400px, 300px 300px, 200px 200px, 150px 150px, 350px 350px;
        animation: subtleFloat 25s ease-in-out infinite;
        pointer-events: none;
        z-index: -1;
        opacity: 0.6;
    }
    
    @keyframes subtleFloat {
        0%, 100% { transform: translateY(0px) rotate(0deg); opacity: 0.6; }
        33% { transform: translateY(-10px) rotate(0.2deg); opacity: 0.8; }
        66% { transform: translateY(10px) rotate(-0.2deg); opacity: 0.4; }
    }
    
    /* 📱 MAIN CONTAINER */
    .main .block-container {
        padding-top: 3rem;
        padding-bottom: 3rem;
        max-width: 1500px;
        position: relative;
        z-index: 10;
    }
    
    /* 🔥 ULTIMATE CONTAINER STYLING */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        padding: 0 !important;
        background: transparent !important;
        position: relative;
        overflow: visible !important;
    }
    
    /* 🌟 PREMIUM ACTIVE TRADE CARD */
    .main .block-container > div:first-child > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: 
            rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(20px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(20px) saturate(180%) !important;
        border-radius: 24px !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        box-shadow: 
            0 8px 32px 0 rgba(31, 38, 135, 0.15),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset,
            0 2px 16px 0 rgba(31, 38, 135, 0.08) !important;
        padding: 40px !important;
        margin: 25px 0 !important;
        position: relative;
        overflow: hidden !important;
        transition: all 0.4s cubic-bezier(0.23, 1, 0.320, 1) !important;
    }
    
    /* 🎭 PREMIUM ACTIVE CARD GLOW */
    .main .block-container > div:first-child > div[data-testid="stVerticalBlockBorderWrapper"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(
            135deg,
            rgba(16, 185, 129, 0.1) 0%,
            rgba(34, 197, 94, 0.05) 25%,
            rgba(5, 150, 105, 0.08) 50%,
            rgba(16, 185, 129, 0.06) 75%,
            rgba(34, 197, 94, 0.1) 100%
        );
        border-radius: 24px;
        z-index: -1;
        opacity: 0.8;
        animation: subtleGlow 4s ease-in-out infinite;
    }
    
    @keyframes subtleGlow {
        0%, 100% { opacity: 0.8; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.005); }
    }
    
    /* 🌙 ELEGANT WAITING CARD */
    .waiting-state .main .block-container > div:first-child > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: 
            rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(16px) saturate(160%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(160%) !important;
        border-radius: 20px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        box-shadow: 
            0 6px 24px 0 rgba(148, 163, 184, 0.12),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset,
            0 1px 8px 0 rgba(148, 163, 184, 0.06) !important;
        padding: 35px !important;
        text-align: center;
        animation: gentlePulse 6s ease-in-out infinite;
    }
    
    @keyframes gentlePulse {
        0%, 100% { 
            transform: scale(1); 
            box-shadow: 0 6px 24px 0 rgba(148, 163, 184, 0.12);
        }
        50% { 
            transform: scale(1.002); 
            box-shadow: 0 8px 28px 0 rgba(148, 163, 184, 0.16);
        }
    }
    
    /* 💎 PREMIUM TAB CONTAINERS */
    [data-testid="stTabs"] div[data-testid="stVerticalBlockBorderWrapper"] {
        background: 
            rgba(255, 255, 255, 0.5) !important;
        backdrop-filter: blur(16px) saturate(160%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(160%) !important;
        border-radius: 18px !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        box-shadow: 
            0 4px 24px 0 rgba(31, 41, 59, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset,
            0 1px 8px 0 rgba(31, 41, 59, 0.04) !important;
        padding: 30px !important;
        margin: 20px 0 !important;
        position: relative;
        overflow: hidden !important;
        transition: all 0.3s cubic-bezier(0.23, 1, 0.320, 1) !important;
    }
    
    /* ✨ ENHANCED HOVER EFFECTS */
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-4px) !important;
        box-shadow: 
            0 12px 40px 0 rgba(31, 38, 135, 0.2),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset,
            0 4px 20px 0 rgba(31, 38, 135, 0.12) !important;
        backdrop-filter: blur(24px) saturate(200%) !important;
        -webkit-backdrop-filter: blur(24px) saturate(200%) !important;
    }
    
    /* 🏆 ULTRA PREMIUM METRICS */
    [data-testid="metric-container"] {
        background: 
            rgba(255, 255, 255, 0.4) !important;
        backdrop-filter: blur(12px) saturate(140%) !important;
        -webkit-backdrop-filter: blur(12px) saturate(140%) !important;
        border-radius: 16px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        box-shadow: 
            0 3px 16px 0 rgba(31, 41, 59, 0.06),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset,
            0 1px 4px 0 rgba(31, 41, 59, 0.03) !important;
        padding: 24px !important;
        margin: 12px !important;
        height: 140px !important;
        position: relative;
        overflow: hidden !important;
        transition: all 0.3s cubic-bezier(0.23, 1, 0.320, 1) !important;
    }
    
    [data-testid="metric-container"]:hover {
        transform: translateY(-3px) scale(1.02) !important;
        box-shadow: 
            0 6px 24px 0 rgba(31, 41, 59, 0.1),
            0 0 0 1px rgba(255, 255, 255, 0.08) inset,
            0 2px 12px 0 rgba(31, 41, 59, 0.06) !important;
        background: 
            rgba(255, 255, 255, 0.55) !important;
        backdrop-filter: blur(16px) saturate(160%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(160%) !important;
    }
    
    /* 🎨 TYPOGRAPHY EXCELLENCE */
    .main-title {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        font-size: 4.5rem !important;
        font-weight: 300 !important;
        text-align: center;
        margin-bottom: 1rem;
        letter-spacing: 0.02em;
        background: linear-gradient(135deg, 
            #1e293b 0%, 
            #475569 25%, 
            #334155 50%, 
            #1e293b 75%, 
            #0f172a 100%
        );
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        position: relative;
        z-index: 10;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .subtitle {
        font-family: 'Inter', sans-serif !important;
        text-align: center;
        color: rgba(71, 85, 105, 0.8) !important;
        margin-bottom: 3rem;
        font-size: 1.2rem !important;
        font-weight: 400 !important;
        letter-spacing: 0.02em;
        position: relative;
        z-index: 10;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    
    /* 💰 PREMIUM COIN NAME */
    .coin-name {
        font-family: 'Inter', sans-serif !important;
        font-size: 2.6rem !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, 
            #1e40af 0%, 
            #3b82f6 30%, 
            #06b6d4 60%, 
            #0891b2 100%
        );
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 12px;
        animation: subtlePulse 3s ease-in-out infinite;
    }
    
    @keyframes subtlePulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.01); }
    }
    
    /* 📊 ENHANCED PRICE DISPLAY */
    .price-display {
        font-family: 'Inter', 'SF Mono', monospace !important;
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        color: rgba(30, 41, 59, 0.9) !important;
        background: rgba(255, 255, 255, 0.3);
        padding: 8px 16px;
        border-radius: 12px;
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }
    
    /* 🏅 ULTIMATE STATUS BADGES */
    .status-badge {
        display: inline-block;
        padding: 10px 20px !important;
        border-radius: 20px !important;
        font-size: 0.85rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        position: relative;
        overflow: hidden;
        transition: all 0.3s ease;
    }
    
    .status-active {
        background: rgba(16, 185, 129, 0.15) !important;
        color: rgba(5, 150, 105, 1) !important;
        border: 1px solid rgba(16, 185, 129, 0.3) !important;
        box-shadow: 
            0 4px 16px rgba(16, 185, 129, 0.2),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
        animation: statusGlow 3s ease-in-out infinite;
    }
    
    @keyframes statusGlow {
        0%, 100% { 
            box-shadow: 0 4px 16px rgba(16, 185, 129, 0.2);
        }
        50% { 
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.3);
        }
    }
    
    .status-waiting {
        background: rgba(148, 163, 184, 0.15) !important;
        color: rgba(71, 85, 105, 1) !important;
        border: 1px solid rgba(148, 163, 184, 0.3) !important;
        box-shadow: 
            0 4px 16px rgba(148, 163, 184, 0.15),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
    }
    
    /* 💸 PROFIT/LOSS STYLING */
    .profit-positive {
        color: rgba(5, 150, 105, 1) !important;
        font-weight: 800 !important;
        text-shadow: 0 1px 3px rgba(5, 150, 105, 0.2) !important;
    }
    
    .profit-negative {
        color: rgba(220, 38, 38, 1) !important;
        font-weight: 800 !important;
        text-shadow: 0 1px 3px rgba(220, 38, 38, 0.2) !important;
    }
    
    /* 📝 SECTION HEADERS */
    .section-header {
        font-family: 'Inter', sans-serif !important;
        font-size: 2rem !important;
        font-weight: 400 !important;
        color: rgba(30, 41, 59, 0.9) !important;
        margin: 35px 0 18px 0 !important;
        padding-bottom: 12px;
        border-bottom: 2px solid rgba(226, 232, 240, 0.6);
        letter-spacing: 0.01em;
        position: relative;
    }
    
    /* 📊 STRATEGY BOXES */
    .strategy-box {
        background: rgba(255, 255, 255, 0.4);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 16px !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        box-shadow: 
            0 3px 12px rgba(0, 0, 0, 0.05),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset !important;
        padding: 20px !important;
        margin: 12px 0 !important;
        word-wrap: break-word;
        white-space: pre-wrap;
        line-height: 1.6;
        min-height: 80px;
        color: rgba(30, 41, 59, 0.9) !important;
        font-weight: 500 !important;
        font-family: 'Inter', sans-serif !important;
        transition: all 0.3s ease;
    }
    
    .strategy-box:hover {
        transform: translateY(-1px);
        box-shadow: 
            0 6px 20px rgba(0, 0, 0, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.08) inset !important;
        background: rgba(255, 255, 255, 0.5);
    }
    
    /* 📈 PREMIUM PROGRESS BARS */
    .progress-container {
        background: rgba(255, 255, 255, 0.3);
        border-radius: 25px !important;
        padding: 4px !important;
        box-shadow: 
            0 2px 8px rgba(0, 0, 0, 0.05) inset,
            0 1px 4px rgba(255, 255, 255, 0.2) inset !important;
        margin: 16px 0 !important;
        border: 1px solid rgba(255, 255, 255, 0.2);
        backdrop-filter: blur(8px);
    }
    
    .progress-bar {
        height: 20px !important;
        border-radius: 25px !important;
        background: linear-gradient(90deg, 
            #10b981 0%, 
            #059669 50%, 
            #047857 100%
        ) !important;
        box-shadow: 
            0 2px 8px rgba(16, 185, 129, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
        transition: all 0.6s cubic-bezier(0.23, 1, 0.320, 1) !important;
        position: relative;
        overflow: hidden;
    }
    
    .progress-bar::after {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, 
            transparent 0%, 
            rgba(255, 255, 255, 0.3) 50%, 
            transparent 100%
        );
        animation: progressShine 3s ease-in-out infinite;
    }
    
    @keyframes progressShine {
        0% { left: -100%; }
        100% { left: 100%; }
    }
    
    .progress-bar-negative {
        background: linear-gradient(90deg, 
            #ef4444 0%, 
            #dc2626 50%, 
            #b91c1c 100%
        ) !important;
        box-shadow: 
            0 2px 8px rgba(239, 68, 68, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
    }
    
    /* 🎯 PREMIUM TAB STYLING */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255, 255, 255, 0.4) !important;
        backdrop-filter: blur(12px) !important;
        border-radius: 16px !important;
        padding: 8px !important;
        box-shadow: 
            0 3px 16px rgba(0, 0, 0, 0.06),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        margin-bottom: 24px !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        border-radius: 12px !important;
        padding: 12px 24px !important;
        color: rgba(71, 85, 105, 0.8) !important;
        font-weight: 600 !important;
        font-family: 'Inter', sans-serif !important;
        transition: all 0.3s cubic-bezier(0.23, 1, 0.320, 1) !important;
        position: relative;
        overflow: hidden;
    }
    
    .stTabs [aria-selected="true"] {
        background: rgba(255, 255, 255, 0.7) !important;
        color: rgba(30, 41, 59, 0.9) !important;
        box-shadow: 
            0 2px 8px rgba(0, 0, 0, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
        font-weight: 700 !important;
        transform: translateY(-1px) !important;
        backdrop-filter: blur(8px) !important;
    }
    
    /* 🔘 PREMIUM BUTTONS */
    .stButton > button {
        background: rgba(255, 255, 255, 0.5) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        border-radius: 16px !important;
        padding: 12px 32px !important;
        font-weight: 700 !important;
        font-family: 'Inter', sans-serif !important;
        color: rgba(30, 41, 59, 0.9) !important;
        transition: all 0.3s cubic-bezier(0.23, 1, 0.320, 1) !important;
        box-shadow: 
            0 3px 12px rgba(0, 0, 0, 0.05),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset !important;
        text-transform: uppercase;
        letter-spacing: 0.02em;
        font-size: 0.9rem !important;
    }
    
    .stButton > button:hover {
        background: rgba(255, 255, 255, 0.7) !important;
        transform: translateY(-2px) scale(1.01) !important;
        box-shadow: 
            0 6px 20px rgba(0, 0, 0, 0.1),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
        border: 1px solid rgba(255, 255, 255, 0.4) !important;
    }
    
    /* 🎭 ANIMATIONS */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .fade-in-up {
        animation: fadeInUp 0.6s cubic-bezier(0.23, 1, 0.320, 1);
    }
    
    /* 📱 RESPONSIVE EXCELLENCE */
    @media (max-width: 768px) {
        .main-title {
            font-size: 2.8rem !important;
        }
        
        .subtitle {
            font-size: 1rem !important;
        }
        
        div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 24px !important;
            margin: 16px 0 !important;
            border-radius: 20px !important;
        }
        
        [data-testid="metric-container"] {
            height: 120px !important;
            padding: 18px !important;
        }
        
        .coin-name {
            font-size: 2rem !important;
        }
        
        .section-header {
            font-size: 1.6rem !important;
        }
    }
    
    /* 🌟 FINAL TOUCHES */
    body {
        overflow-x: hidden;
    }
    
    /* Premium Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.4);
        border-radius: 4px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: background 0.3s ease;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(148, 163, 184, 0.6);
    }
</style>
""", unsafe_allow_html=True)

def set_waiting_state():
    """대기 상태일 때 body에 클래스 추가"""
    st.markdown("""
    <script>
        document.body.classList.add('waiting-state');
    </script>
    """, unsafe_allow_html=True)

def remove_waiting_state():
    """활성 거래가 있을 때 대기 상태 클래스 제거"""
    st.markdown("""
    <script>
        document.body.classList.remove('waiting-state');
    </script>
    """, unsafe_allow_html=True)

def create_active_trade_card(trade, cumulative_profit):
    """🌟 ULTIMATE 활성 거래 카드"""
    remove_waiting_state()
    
    with st.container(border=True):
        # 🎯 PREMIUM HEADER
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown('<h2 class="section-header">🎯 현재 활성 거래</h2>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="status-badge status-active">🔥 ACTIVE</div>', unsafe_allow_html=True)
        
        # 💎 MAIN INFO SECTION
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            st.markdown(f'<div class="coin-name">{trade["coin_ticker"]}</div>', unsafe_allow_html=True)
            current_price = trade.get('current_price', 0)
            st.markdown(f'<div class="price-display">현재가: {format_price(current_price)}</div>', unsafe_allow_html=True)
        
        with col2:
            entry_price = trade.get('actual_entry_price', 0)
            current_price = trade.get('current_price', entry_price)
            volume = trade.get('actual_volume', 0)
            entry_fee = trade.get('entry_fee', 0)
            
            if entry_price > 0 and volume > 0:
                # 진입 총 비용 (매수금액 + 매수수수료)
                total_entry_cost = entry_price * volume + entry_fee
                
                # 현재 총 가치 (매도시 예상 수수료 0.05% 고려)
                current_total_value = current_price * volume
                expected_exit_fee = current_total_value * 0.0005  # 0.05%
                net_current_value = current_total_value - expected_exit_fee
                
                # 미실현 순손익
                unrealized_pnl_krw = net_current_value - total_entry_cost
                unrealized_pnl_rate = (unrealized_pnl_krw / total_entry_cost) * 100
            else:
                unrealized_pnl_krw = 0
                unrealized_pnl_rate = 0
            
            if unrealized_pnl_rate >= 0:
                st.markdown('<div style="text-align: center;"><h3 style="margin: 0; color: #059669; font-family: Inter;">📈 미실현 순수익</h3></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-size: 2.2rem; font-family: Inter;" class="profit-positive">+₩{unrealized_pnl_krw:,.0f}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-size: 1.5rem; font-family: Inter;" class="profit-positive">(+{unrealized_pnl_rate:.2f}%)</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-size: 0.8rem; color: #6b7280; font-family: Inter;">*매도수수료 0.05% 반영</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="text-align: center;"><h3 style="margin: 0; color: #dc2626; font-family: Inter;">📉 미실현 순손실</h3></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-size: 2.2rem; font-family: Inter;" class="profit-negative">₩{unrealized_pnl_krw:,.0f}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-size: 1.5rem; font-family: Inter;" class="profit-negative">({unrealized_pnl_rate:.2f}%)</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-size: 0.8rem; color: #6b7280; font-family: Inter;">*매도수수료 0.05% 반영</div>', unsafe_allow_html=True)
        
        with col3:
            st.markdown('<div style="text-align: center;"><h3 style="margin: 0; color: #374151; font-family: Inter;">💎 누적 순수익</h3></div>', unsafe_allow_html=True)
            if cumulative_profit >= 0:
                st.markdown(f'<div style="text-align: center; font-size: 1.8rem; font-family: Inter;" class="profit-positive">+₩{cumulative_profit:,.0f}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="text-align: center; font-size: 1.8rem; font-family: Inter;" class="profit-negative">₩{cumulative_profit:,.0f}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 0.8rem; color: #6b7280; font-family: Inter;">*수수료 차감 후</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 📊 DETAILED TRADE INFO
        col1, col2, col3, col4 = st.columns(4)
        
        entry_price = trade['actual_entry_price']
        target_price = trade['target_price']
        stop_loss_price = trade['stop_loss_price']
        
        target_rate = (target_price - entry_price) / entry_price * 100
        stop_rate = (stop_loss_price - entry_price) / entry_price * 100
        
        with col1:
            st.markdown('<div style="text-align: center;"><h4 style="color: #059669; margin: 0; font-family: Inter;">🎯 목표가</h4></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 1.3rem; font-weight: 700; color: #374151; font-family: Inter;">{format_price(target_price)}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-family: Inter;" class="profit-positive">+{target_rate:.2f}%</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div style="text-align: center;"><h4 style="color: #dc2626; margin: 0; font-family: Inter;">🛑 손절가</h4></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 1.3rem; font-weight: 700; color: #374151; font-family: Inter;">{format_price(stop_loss_price)}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-family: Inter;" class="profit-negative">{stop_rate:.2f}%</div>', unsafe_allow_html=True)
        
        with col3:
            st.markdown('<div style="text-align: center;"><h4 style="color: #3b82f6; margin: 0; font-family: Inter;">💰 매수가</h4></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 1.3rem; font-weight: 700; color: #374151; font-family: Inter;">{format_price(entry_price)}</div>', unsafe_allow_html=True)
            if trade.get('entry_fee'):
                st.markdown(f'<div style="text-align: center; font-size: 0.9rem; color: #6b7280; font-family: Inter;">수수료: ₩{trade["entry_fee"]:,.0f}</div>', unsafe_allow_html=True)
        
        with col4:
            st.markdown('<div style="text-align: center;"><h4 style="color: #8b5cf6; margin: 0; font-family: Inter;">📊 보유량</h4></div>', unsafe_allow_html=True)
            if trade.get('actual_volume'):
                st.markdown(f'<div style="text-align: center; font-size: 1.1rem; font-weight: 700; color: #374151; font-family: Inter;">{trade["actual_volume"]:.6f}개</div>', unsafe_allow_html=True)
            executed_amount = (entry_price * trade.get('actual_volume', 0)) if trade.get('actual_volume') else 0
            st.markdown(f'<div style="text-align: center; font-size: 0.9rem; color: #6b7280; font-family: Inter;">₩{executed_amount:,.0f}</div>', unsafe_allow_html=True)
        
        # 📈 ULTIMATE PROGRESS BAR
        st.markdown('<h4 style="color: #374151; margin: 25px 0 15px 0; font-family: Inter;">📈 목표 달성 진행도</h4>', unsafe_allow_html=True)
        
        current_price = trade.get('current_price', entry_price)
        if current_price >= entry_price:
            progress = (current_price - entry_price) / (target_price - entry_price) * 100
            progress_value = min(progress / 100, 1.0)
            
            st.markdown('<div class="progress-container">', unsafe_allow_html=True)
            st.markdown(f'<div class="progress-bar" style="width: {progress_value * 100}%;"></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; margin-top: 12px; font-weight: 700; color: #059669; font-family: Inter; font-size: 1.1rem;">🚀 목표까지: {progress:.1f}% 완료</div>', unsafe_allow_html=True)
        else:
            risk = (entry_price - current_price) / (entry_price - stop_loss_price) * 100
            risk_value = min(risk / 100, 1.0)
            
            st.markdown('<div class="progress-container">', unsafe_allow_html=True)
            st.markdown(f'<div class="progress-bar progress-bar-negative" style="width: {risk_value * 100}%;"></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; margin-top: 12px; font-weight: 700; color: #dc2626; font-family: Inter; font-size: 1.1rem;">⚠️ 손실 위험도: {risk:.1f}%</div>', unsafe_allow_html=True)
        
        # 💡 STRATEGY SECTION
        st.markdown("---")
        st.markdown('<h4 style="color: #374151; margin: 25px 0 20px 0; font-family: Inter;">💡 거래 전략</h4>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<h5 style="color: #059669; font-family: Inter;">🎯 진입 근거</h5>', unsafe_allow_html=True)
            entry_reason = trade.get('entry_reason', '정보 없음')
            st.markdown(f'<div class="strategy-box">{entry_reason}</div>', unsafe_allow_html=True)
            
            st.markdown('<h5 style="color: #3b82f6; font-family: Inter;">📊 목표 설정 이유</h5>', unsafe_allow_html=True)
            target_reason = trade.get('target_reason', '정보 없음')
            st.markdown(f'<div class="strategy-box">{target_reason}</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<h5 style="color: #dc2626; font-family: Inter;">🛑 손절 기준</h5>', unsafe_allow_html=True)
            stop_loss_reason = trade.get('stop_loss_reason', '정보 없음')
            st.markdown(f'<div class="strategy-box">{stop_loss_reason}</div>', unsafe_allow_html=True)
            
            if trade.get('timestamp'):
                st.markdown('<h5 style="color: #8b5cf6; font-family: Inter;">⏰ 거래 정보</h5>', unsafe_allow_html=True)
                start_time = pd.to_datetime(trade['timestamp'])
                elapsed = datetime.now() - start_time.to_pydatetime()
                elapsed_hours = elapsed.total_seconds() / 3600
                
                time_info = f"시작: {start_time.strftime('%m/%d %H:%M')}\n경과: {elapsed_hours:.1f}시간"
                st.markdown(f'<div class="strategy-box">{time_info}</div>', unsafe_allow_html=True)

def create_waiting_card(krw_balance, cumulative_profit, total_fees):
    """🌙 ELEGANT 대기 상태 카드"""
    set_waiting_state()
    
    with st.container(border=True):
        st.markdown('<h2 class="section-header">⏸️ 거래 대기 중</h2>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown('<div style="text-align: center;"><h4 style="color: #374151; font-family: Inter;">💰 KRW 잔고</h4></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 2.2rem; font-weight: 700; color: #3b82f6; font-family: Inter;">₩{krw_balance:,.0f}</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div style="text-align: center;"><h4 style="color: #374151; font-family: Inter;">💎 누적 순수익</h4></div>', unsafe_allow_html=True)
            if cumulative_profit >= 0:
                st.markdown(f'<div style="text-align: center; font-size: 2.2rem; font-family: Inter;" class="profit-positive">+₩{cumulative_profit:,.0f}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="text-align: center; font-size: 2.2rem; font-family: Inter;" class="profit-negative">₩{cumulative_profit:,.0f}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 0.8rem; color: #6b7280; font-family: Inter;">*수수료 차감 후</div>', unsafe_allow_html=True)
        
        with col3:
            st.markdown('<div style="text-align: center;"><h4 style="color: #374151; font-family: Inter;">💸 총 수수료</h4></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 2.2rem; font-weight: 700; color: #6b7280; font-family: Inter;">₩{total_fees:,.0f}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: center; font-size: 0.8rem; color: #6b7280; font-family: Inter;">매수+매도 0.1%</div>', unsafe_allow_html=True)
        
        st.markdown('<div style="text-align: center; margin-top: 30px; font-size: 1.3rem; color: #6b7280; font-style: italic; font-family: Inter;">✨ 다음 거래 기회를 분석하고 있습니다...</div>', unsafe_allow_html=True)



# 기존 데이터 로드 함수들 유지
@st.cache_data(ttl=60)
def load_trade_history():
    """거래 기록 로드 (CANCELLED 포함)"""
    try:
        db = TradeDatabase()
        trades = db.get_recent_trades(limit=100)  # limit을 100으로 증가
        if trades:
            df = pd.DataFrame(trades)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['exit_timestamp'] = pd.to_datetime(df['exit_timestamp'], errors='coerce')
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=10)
def get_current_status():
    """현재 시스템 상태"""
    try:
        client = UpbitClient()
        krw_balance = client.get_balance("KRW")
        
        db = TradeDatabase()
        recent_trades = db.get_recent_trades(limit=1)
        active_trade = None
        
        if recent_trades and recent_trades[0]['status'] == 'ACTIVE':
            active_trade = recent_trades[0]
            if active_trade['coin_ticker']:
                current_price = client.get_current_price(active_trade['coin_ticker'])
                if current_price and active_trade['actual_entry_price']:
                    active_trade['current_price'] = current_price
                    
                    # 🔧 기존 미실현 손익 계산 수정
                    entry_price = active_trade['actual_entry_price']
                    volume = active_trade.get('actual_volume', 0)
                    entry_fee = active_trade.get('entry_fee', 0)
                    
                    if volume > 0:
                        # 진입 총 비용
                        total_entry_cost = entry_price * volume + entry_fee
                        
                        # 현재 총 가치 (예상 매도수수료 고려)
                        current_total_value = current_price * volume
                        expected_exit_fee = current_total_value * 0.0005  # 0.05%
                        net_current_value = current_total_value - expected_exit_fee
                        
                        # 미실현 순손익
                        active_trade['unrealized_profit_krw'] = net_current_value - total_entry_cost
                        active_trade['unrealized_pnl'] = (net_current_value - total_entry_cost) / total_entry_cost * 100
                    else:
                        # 🔧 기존 계산 방식을 백업으로 유지
                        active_trade['unrealized_pnl'] = (current_price - entry_price) / entry_price * 100
                        active_trade['unrealized_profit_krw'] = 0
        
        return {
            'krw_balance': krw_balance,
            'active_trade': active_trade,
            'last_update': datetime.now()
        }
    except Exception as e:
        return {
            'krw_balance': 0,
            'active_trade': None,
            'last_update': datetime.now(),
            'error': str(e)
        }


def get_cumulative_profit():
    """누적 수익 계산 (CANCELLED는 실제 거래가 아니므로 제외)"""
    try:
        db = TradeDatabase()
        stats = db.get_statistics_with_fees()
        # database.py의 get_statistics_with_fees()에서 이미 CANCELLED 제외
        return stats.get('total_profit_loss', 0), stats.get('total_fees', 0)
    except:
        return 0, 0

def format_price(price):
    """가격 포맷팅 (2025/7/31 신규 호가 단위 반영)"""
    try:
        price = float(price)
        
        # 새로운 호가 단위에 맞춘 표시 정밀도
        if price >= 1000000:
            # 100만원 이상: 1000원 단위이므로 정수 표시
            return f"₩{price:,.0f}"
        elif price >= 100000:
            # 10만원 이상: 100원 단위이므로 정수 표시
            return f"₩{price:,.0f}"
        elif price >= 10000:
            # 1만원 이상: 50원 또는 10원 단위이므로 정수 표시
            return f"₩{price:,.0f}"
        elif price >= 1000:
            # 1천원 이상: 5원 또는 1원 단위이므로 정수 표시
            return f"₩{price:,.0f}"
        elif price >= 100:
            # 100원 이상: 1원 단위이므로 정수 표시
            return f"₩{price:,.0f}"
        elif price >= 10:
            # 10원 이상: 0.1원 단위이므로 소수점 1자리
            return f"₩{price:,.1f}"
        elif price >= 1:
            # 1원 이상: 0.01원 단위이므로 소수점 2자리
            return f"₩{price:,.2f}"
        elif price >= 0.1:
            # 0.1원 이상: 0.001원 단위이므로 소수점 3자리
            return f"₩{price:.3f}"
        else:
            # 0.1원 미만: 0.0001원 단위이므로 소수점 4자리
            return f"₩{price:.4f}"
    except:
        return f"₩{price}"

def create_profit_chart(df):
    """🎨 ULTIMATE 수익률 차트 (COMPLETED만 사용)"""
    if df.empty:
        return None
    
    # COMPLETED 상태만 필터링 (이미 필터링된 df를 받지만 안전장치)
    completed_trades = df[df['status'] == 'COMPLETED'].copy()
    if completed_trades.empty:
        return None
    
    completed_trades = completed_trades.sort_values('exit_timestamp')
    completed_trades['cumulative_profit'] = completed_trades['profit_loss'].cumsum()
    
    fig = go.Figure()
    
    # 🌈 GRADIENT BAR COLORS
    colors = []
    for x in completed_trades['profit_rate']:
        if x > 10:
            colors.append('rgba(5, 150, 105, 0.9)')
        elif x > 0:
            colors.append('rgba(16, 185, 129, 0.8)')
        elif x > -5:
            colors.append('rgba(245, 158, 11, 0.8)')
        else:
            colors.append('rgba(220, 38, 38, 0.8)')
    
    fig.add_trace(go.Bar(
        x=completed_trades['exit_timestamp'],
        y=completed_trades['profit_rate'],
        name='개별 수익률',
        marker=dict(
            color=colors,
            line=dict(color='rgba(255, 255, 255, 0.8)', width=2)
        ),
        yaxis='y',
        opacity=0.95,
        hovertemplate='<b>수익률</b>: %{y:.2f}%<br><b>날짜</b>: %{x}<extra></extra>'
    ))
    
    # ✨ GLOWING CUMULATIVE LINE
    fig.add_trace(go.Scatter(
        x=completed_trades['exit_timestamp'],
        y=completed_trades['cumulative_profit'],
        name='누적 수익금',
        line=dict(
            color='rgba(59, 130, 246, 1)',
            width=5,
            shape='spline'
        ),
        yaxis='y2',
        hovertemplate='<b>누적 수익</b>: ₩%{y:,.0f}<br><b>날짜</b>: %{x}<extra></extra>',
        fill='tonexty',
        fillcolor='rgba(59, 130, 246, 0.15)'
    ))
    
    fig.update_layout(
        title=dict(
            text="💰 거래 수익률 성과 분석 (완료된 거래만)",
            font=dict(size=28, color='#1e1b4b', family='Inter', weight=300),
            x=0.5
        ),
        yaxis=dict(
            title=dict(text='개별 수익률 (%)', font=dict(color='#374151', family='Inter')),
            side='left', showgrid=True, gridcolor='rgba(148, 163, 184, 0.2)',
            gridwidth=1, zeroline=True, zerolinecolor='rgba(148, 163, 184, 0.4)',
            tickfont=dict(color='#374151', family='Inter')
        ),
        yaxis2=dict(
            title=dict(text='누적 수익금 (₩)', font=dict(color='#3b82f6', family='Inter')),
            side='right', overlaying='y', showgrid=False,
            tickfont=dict(color='#3b82f6', family='Inter')
        ),
        xaxis=dict(
            title=dict(text='거래 종료 시간', font=dict(color='#374151', family='Inter')),
            showgrid=True, gridcolor='rgba(148, 163, 184, 0.2)',
            tickfont=dict(color='#374151', family='Inter')
        ),
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(255,255,255,0.05)',
        font=dict(color='#374151', family='Inter'),
        legend=dict(
            bgcolor='rgba(255, 255, 255, 0.9)',
            bordercolor='rgba(148, 163, 184, 0.3)',
            borderwidth=2,
            font=dict(color='#374151', family='Inter'),
            x=0.02, y=0.98
        ),
        margin=dict(l=60, r=60, t=100, b=60),
        height=500
    )
    
    return fig

def create_win_rate_gauge(win_rate):
    """🎯 PREMIUM 승률 게이지"""
    if win_rate >= 80:
        gauge_color = "rgba(5, 150, 105, 0.9)"
        ring_color = "rgba(5, 150, 105, 0.3)"
    elif win_rate >= 60:
        gauge_color = "rgba(59, 130, 246, 0.9)"
        ring_color = "rgba(59, 130, 246, 0.3)"
    elif win_rate >= 40:
        gauge_color = "rgba(245, 158, 11, 0.9)"
        ring_color = "rgba(245, 158, 11, 0.3)"
    else:
        gauge_color = "rgba(220, 38, 38, 0.9)"
        ring_color = "rgba(220, 38, 38, 0.3)"
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=win_rate,
        title={'text': "🎯 승률", 'font': {'size': 24, 'color': '#1e1b4b', 'family': 'Inter'}},
        delta={'reference': 50, 'increasing': {'color': gauge_color}},
        number={'font': {'size': 52, 'color': '#1e1b4b', 'family': 'Inter'}},
        gauge={
            'axis': {
                'range': [None, 100], 
                'tickcolor': "#94a3b8",
                'tickfont': {'color': '#64748b', 'size': 14, 'family': 'Inter'}
            },
            'bar': {'color': gauge_color, 'thickness': 0.9},
            'bgcolor': "rgba(255,255,255,0.4)",
            'borderwidth': 3,
            'bordercolor': "rgba(148, 163, 184, 0.4)",
            'steps': [
                {'range': [0, 30], 'color': "rgba(220, 38, 38, 0.15)"},
                {'range': [30, 50], 'color': "rgba(245, 158, 11, 0.15)"},
                {'range': [50, 70], 'color': "rgba(59, 130, 246, 0.15)"},
                {'range': [70, 100], 'color': "rgba(5, 150, 105, 0.15)"}
            ],
            'threshold': {
                'line': {'color': "rgba(148, 163, 184, 0.8)", 'width': 4},
                'thickness': 0.9,
                'value': 80
            }
        }
    ))
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': "#1e1b4b", 'size': 16, 'family': 'Inter'},
        height=320,
        margin=dict(l=30, r=30, t=80, b=30)
    )
    
    return fig

def load_reflection_data():
    """회고 데이터 로드 - 프로젝트 구조에 맞는 경로"""
    try:
        # dashboard/ 에서 실행하므로 상위 디렉토리로 이동 필요
        import os
        current_dir = os.getcwd()
        print(f"현재 디렉토리: {current_dir}")
        
        # 프로젝트 구조에 맞는 경로
        if 'dashboard' in current_dir:
            # dashboard에서 실행 중
            reflection_path = '../memory/Reflection.md'
        else:
            # 루트에서 실행 중
            reflection_path = 'memory/Reflection.md'
        
        print(f"회고 파일 경로: {reflection_path}")
        
        if os.path.exists(reflection_path):
            print(f"✅ 회고 파일 발견: {reflection_path}")
            with open(reflection_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"📄 파일 크기: {len(content)} 문자")
            return content
        else:
            print(f"❌ 회고 파일 없음: {reflection_path}")
            return ""
        
    except Exception as e:
        print(f"회고 데이터 로드 오류: {e}")
        return ""

def load_principles_data():
    """핵심 원칙 데이터 로드 - 프로젝트 구조에 맞는 경로"""
    try:
        import os
        current_dir = os.getcwd()
        
        # 프로젝트 구조에 맞는 경로
        if 'dashboard' in current_dir:
            # dashboard에서 실행 중
            principles_path = '../memory/Principles.md'
        else:
            # 루트에서 실행 중
            principles_path = 'memory/Principles.md'
        
        print(f"원칙 파일 경로: {principles_path}")
        
        if os.path.exists(principles_path):
            print(f"✅ 원칙 파일 발견: {principles_path}")
            with open(principles_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        else:
            print(f"❌ 원칙 파일 없음: {principles_path}")
            return ""
        
    except Exception as e:
        print(f"원칙 데이터 로드 오류: {e}")
        return ""

def create_reflection_display(reflection_content):
    """회고 내용 표시 - MD 내용 그대로 표시"""
    with st.container(border=True):
        st.markdown('<h3 style="color: #1e1b4b; margin-bottom: 25px; font-family: Inter;">🧠 거래 회고</h3>', unsafe_allow_html=True)
        
        if reflection_content and reflection_content.strip():
            # Markdown 내용을 그대로 표시
            st.markdown(reflection_content, unsafe_allow_html=False)
        else:
            st.markdown('<div style="text-align: center; padding: 40px; color: #6b7280; font-family: Inter;">📝 아직 회고 데이터가 없습니다. 거래가 완료되면 AI가 자동으로 회고를 생성합니다.</div>', unsafe_allow_html=True)

def create_principles_display(principles_content):
    """원칙 표시 - 전체 내용을 한번에 표시"""
    with st.container(border=True):
        st.markdown('<h3 style="color: #1e1b4b; margin-bottom: 25px; font-family: Inter;">📜 현재 거래 원칙</h3>', unsafe_allow_html=True)
        
        if principles_content and principles_content.strip():
            # Principles.md 내용을 통째로 표시
            # 스타일을 적용한 컨테이너에 전체 내용 표시
            st.markdown(
                f'''
                <div style="
                    background: rgba(255, 255, 255, 0.7);
                    backdrop-filter: blur(10px);
                    border: 2px solid rgba(148, 163, 184, 0.2);
                    border-radius: 16px;
                    padding: 30px;
                    font-family: Inter;
                    line-height: 1.8;
                    color: #1e1b4b;
                    max-height: 800px;
                    overflow-y: auto;
                    box-shadow: 
                        0 4px 6px -1px rgba(0, 0, 0, 0.05),
                        0 2px 4px -1px rgba(0, 0, 0, 0.03);
                ">
                ''',
                unsafe_allow_html=True
            )
            
            # Markdown 내용을 그대로 렌더링
            st.markdown(principles_content)
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 원칙 업데이트 정보 표시
            st.markdown("---")
            
            # 파일 정보 표시
            try:
                import os
                from datetime import datetime
                
                current_dir = os.getcwd()
                if 'dashboard' in current_dir:
                    principles_file = '../memory/Principles.md'
                else:
                    principles_file = 'memory/Principles.md'
                
                if os.path.exists(principles_file):
                    file_stat = os.stat(principles_file)
                    last_modified = datetime.fromtimestamp(file_stat.st_mtime)
                    file_size = file_stat.st_size
                    
                    # 원칙 수 카운트 (##으로 시작하는 섹션 수)
                    section_count = principles_content.count('\n## ')
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown(
                            f'''
                            <div style="
                                background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(139, 92, 246, 0.05) 100%);
                                padding: 15px;
                                border-radius: 12px;
                                border: 1px solid rgba(59, 130, 246, 0.2);
                            ">
                                <div style="color: #3b82f6; font-size: 12px; font-weight: 500; margin-bottom: 5px;">
                                    📅 마지막 업데이트
                                </div>
                                <div style="color: #1e1b4b; font-size: 16px; font-weight: 600;">
                                    {last_modified.strftime('%Y-%m-%d %H:%M')}
                                </div>
                            </div>
                            ''',
                            unsafe_allow_html=True
                        )
                    
                    with col2:
                        st.markdown(
                            f'''
                            <div style="
                                background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(5, 150, 105, 0.05) 100%);
                                padding: 15px;
                                border-radius: 12px;
                                border: 1px solid rgba(16, 185, 129, 0.2);
                            ">
                                <div style="color: #10b981; font-size: 12px; font-weight: 500; margin-bottom: 5px;">
                                    📊 원칙 섹션 수
                                </div>
                                <div style="color: #1e1b4b; font-size: 16px; font-weight: 600;">
                                    {section_count}개
                                </div>
                            </div>
                            ''',
                            unsafe_allow_html=True
                        )
                    
                    with col3:
                        st.markdown(
                            f'''
                            <div style="
                                background: linear-gradient(135deg, rgba(139, 92, 246, 0.08) 0%, rgba(168, 85, 247, 0.05) 100%);
                                padding: 15px;
                                border-radius: 12px;
                                border: 1px solid rgba(139, 92, 246, 0.2);
                            ">
                                <div style="color: #8b5cf6; font-size: 12px; font-weight: 500; margin-bottom: 5px;">
                                    💾 파일 크기
                                </div>
                                <div style="color: #1e1b4b; font-size: 16px; font-weight: 600;">
                                    {file_size / 1024:.1f} KB
                                </div>
                            </div>
                            ''',
                            unsafe_allow_html=True
                        )
                        
            except Exception as e:
                st.error(f"원칙 파일 정보를 읽을 수 없습니다: {e}")
        
        else:
            # 원칙이 없을 때 표시
            st.markdown(
                '''
                <div style="
                    text-align: center;
                    padding: 60px 20px;
                    background: linear-gradient(135deg, rgba(148, 163, 184, 0.05) 0%, rgba(203, 213, 225, 0.05) 100%);
                    border-radius: 16px;
                    border: 2px dashed rgba(148, 163, 184, 0.3);
                ">
                    <div style="font-size: 48px; margin-bottom: 20px;">📝</div>
                    <h3 style="color: #64748b; font-family: Inter; margin-bottom: 10px;">
                        아직 학습된 원칙이 없습니다
                    </h3>
                    <p style="color: #94a3b8; font-family: Inter; font-size: 14px;">
                        거래가 진행되면 AI가 자동으로 원칙을 생성하고 업데이트합니다.
                    </p>
                </div>
                ''',
                unsafe_allow_html=True
            )

def create_learning_progress_chart(reflection_content):
    """간단한 통계 차트 - 문자열 기반"""
    if not reflection_content or not reflection_content.strip():
        return None
    
    # 문자열에서 직접 통계 추출
    trade_count = reflection_content.count('### 알트코인 거래 Log:')
    success_count = reflection_content.count('**SUCCESS**')
    failure_count = reflection_content.count('**FAILURE**')
    
    # 실패 카운트가 0이면 전체에서 성공을 뺀 값으로 계산
    if failure_count == 0 and trade_count > success_count:
        failure_count = trade_count - success_count
    
    if trade_count == 0:
        return None
    
    # 차트 생성
    fig = go.Figure(data=[
        go.Bar(
            x=['성공', '실패'],
            y=[success_count, failure_count],
            marker=dict(
                color=['#10b981', '#ef4444'],
                line=dict(color='rgba(255, 255, 255, 0.8)', width=2)
            ),
            text=[success_count, failure_count],
            textposition='auto',
            hovertemplate='<b>%{x}</b>: %{y}회<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title=dict(
            text=f"🧠 거래 성과 요약 (총 {trade_count}회)",
            font=dict(size=20, color='#1e1b4b', family='Inter'),
            x=0.5
        ),
        yaxis=dict(
            title='거래 수',
            showgrid=True,
            gridcolor='rgba(148, 163, 184, 0.2)'
        ),
        xaxis=dict(
            title='결과'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(255,255,255,0.05)',
        font=dict(color='#374151', family='Inter'),
        height=300,
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    return fig

# 🎨 메인 앱 함수 완성
def main():
    # 🌟 EPIC HEADER
    st.markdown('<h1 class="main-title fade-in-up">OMNI Trading System</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle fade-in-up">powered by 운영자</p>', unsafe_allow_html=True)
    
    # 현재 상태 로드
    status = get_current_status()
    cumulative_profit, total_fees = get_cumulative_profit()
    
    # 🔥 ULTIMATE 카드 생성
    if status['active_trade']:
        create_active_trade_card(status['active_trade'], cumulative_profit)
    else:
        create_waiting_card(status['krw_balance'], cumulative_profit, total_fees)
    
    # ⏰ 상태 정보
    st.markdown(f'<div style="text-align: center; margin: 30px 0; color: rgba(100, 116, 139, 0.8); font-size: 1rem; font-family: Inter; background: rgba(255, 255, 255, 0.2); padding: 10px 20px; border-radius: 20px; backdrop-filter: blur(10px);">⏰ 마지막 업데이트: {status["last_update"].strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
    
    # 🎯 PREMIUM TABS - 회고 탭 추가
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Overview", "📈 Performance", "📜 History", "🧠 Reflections", "📚 Principles", "🔄 새로고침"])
    
    # 거래 기록 및 회고 데이터 로드
    df_trades = load_trade_history()
    reflection_content = load_reflection_data()
    principles = load_principles_data()
    
    with tab1:
        if not df_trades.empty:
            completed = df_trades[df_trades['status'] == 'COMPLETED']
            cancelled = df_trades[df_trades['status'] == 'CANCELLED']
            active = df_trades[df_trades['status'] == 'ACTIVE']
            waiting = df_trades[df_trades['status'] == 'WAITING_ENTRY']
            
            # 🏆 PREMIUM METRICS (CANCELLED 포함)
            with st.container(border=True):
                col1, col2, col3, col4, col5 = st.columns(5)
                
                total_completed = len(completed)
                total_cancelled = len(cancelled)
                profitable = len(completed[completed['profit_rate'] > 0]) if not completed.empty else 0
                win_rate = (profitable / total_completed * 100) if total_completed > 0 else 0
                avg_profit = completed['profit_rate'].mean() if not completed.empty else 0
                
                with col1:
                    st.metric("완료된 거래", total_completed, delta=f"+{len(active)} 진행중", delta_color="normal")
                
                with col2:
                    st.metric("취소된 거래", total_cancelled, delta="진입가 미달성", delta_color="off")
                
                with col3:
                    if total_completed > 0:
                        st.metric("승률", f"{win_rate:.1f}%", delta=f"{profitable}/{total_completed}", delta_color="normal")
                    else:
                        st.metric("승률", "0.0%", delta="0/0", delta_color="normal")
                
                with col4:
                    if not completed.empty:
                        st.metric("평균 수익률", f"{avg_profit:+.2f}%", delta=f"최고: {completed['profit_rate'].max():.1f}%", delta_color="normal")
                        # 🆕 추가 정보: 순손익 표시
                        if cumulative_profit >= 0:
                            st.markdown(f'<div style="text-align: center; font-size: 0.9rem; color: #059669; margin-top: 8px;">순손익: +₩{cumulative_profit:,.0f}</div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div style="text-align: center; font-size: 0.9rem; color: #dc2626; margin-top: 8px;">순손익: ₩{cumulative_profit:,.0f}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div style="text-align: center; font-size: 0.8rem; color: #6b7280;">*수수료 ₩{total_fees:,.0f} 차감후</div>', unsafe_allow_html=True)
                    else:
                        st.metric("평균 수익률", "0.00%", delta="데이터 없음", delta_color="normal")
                
                with col5:
                    st.metric("총 손익", f"₩{cumulative_profit:,.0f}", delta=f"-₩{total_fees:,.0f} 수수료", delta_color="inverse")
            
            # 📊 최근 10개 거래 차트 (모든 상태 포함)
            with st.container(border=True):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    if not completed.empty:
                        gauge_fig = create_win_rate_gauge(win_rate)
                        if gauge_fig:
                            st.plotly_chart(gauge_fig, use_container_width=True)
                    else:
                        st.markdown('<div style="text-align: center; padding: 40px; color: #6b7280;">📊 승률 데이터 없음</div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown("### 🎨 최근 10개 거래 현황")
                    
                    # 모든 상태 포함하여 최근 10개 선택
                    recent_10 = df_trades.tail(10)
                    
                    if not recent_10.empty:
                        # 색상, 값, 라벨, 호버 텍스트 설정
                        colors = []
                        values = []
                        labels = []
                        hover_texts = []
                        
                        for _, row in recent_10.iterrows():
                            if row['status'] == 'CANCELLED':
                                colors.append('#9ca3af')  # 회색
                                values.append(0)
                                labels.append(row['timestamp'].strftime('%m/%d %H:%M'))
                                hover_texts.append(f"<b>상태</b>: 취소됨<br><b>코인</b>: {row['coin_ticker']}<br><b>사유</b>: 진입가 미달성<br><b>시간</b>: {row['timestamp'].strftime('%Y-%m-%d %H:%M')}")
                            
                            elif row['status'] == 'COMPLETED':
                                profit_rate = row['profit_rate']
                                if profit_rate > 10:
                                    colors.append('#059669')
                                elif profit_rate > 0:
                                    colors.append('#10b981')
                                elif profit_rate > -5:
                                    colors.append('#f59e0b')
                                else:
                                    colors.append('#dc2626')
                                values.append(profit_rate)
                                
                                if pd.notna(row['exit_timestamp']):
                                    labels.append(row['exit_timestamp'].strftime('%m/%d %H:%M'))
                                    hover_texts.append(f"<b>수익률</b>: {profit_rate:.2f}%<br><b>코인</b>: {row['coin_ticker']}<br><b>종료</b>: {row['exit_timestamp'].strftime('%Y-%m-%d %H:%M')}")
                                else:
                                    labels.append(row['timestamp'].strftime('%m/%d %H:%M'))
                                    hover_texts.append(f"<b>수익률</b>: {profit_rate:.2f}%<br><b>코인</b>: {row['coin_ticker']}<br><b>완료</b>: 종료시간 없음")
                            
                            elif row['status'] == 'ACTIVE':
                                colors.append('#3b82f6')  # 파란색
                                values.append(0)
                                labels.append(row['timestamp'].strftime('%m/%d %H:%M'))
                                hover_texts.append(f"<b>상태</b>: 거래 진행중<br><b>코인</b>: {row['coin_ticker']}<br><b>시작</b>: {row['timestamp'].strftime('%Y-%m-%d %H:%M')}")
                            
                            else:  # WAITING_ENTRY 등
                                colors.append('#f59e0b')  # 주황색
                                values.append(0)
                                labels.append(row['timestamp'].strftime('%m/%d %H:%M'))
                                hover_texts.append(f"<b>상태</b>: {row['status']}<br><b>코인</b>: {row['coin_ticker']}<br><b>시작</b>: {row['timestamp'].strftime('%Y-%m-%d %H:%M')}")
                        
                        # 차트 생성
                        fig = go.Figure(data=[
                            go.Bar(
                                x=labels,
                                y=values,
                                marker_color=colors,
                                marker_line=dict(color='rgba(255, 255, 255, 0.8)', width=2),
                                text=[f"{x:.1f}%" if x != 0 else "취소" if colors[i] == '#9ca3af' else "진행중" if colors[i] == '#3b82f6' else "대기" for i, x in enumerate(values)],
                                textposition='outside',
                                textfont=dict(family='Inter', size=10, color='#374151'),
                                hovertemplate='%{customdata}<extra></extra>',
                                customdata=hover_texts
                            )
                        ])
                        
                        fig.update_layout(
                            height=320,
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(255,255,255,0.05)',
                            xaxis=dict(
                                title=dict(text="거래 시간", font=dict(family='Inter', color='#374151')),
                                showgrid=True, gridcolor='rgba(148, 163, 184, 0.2)',
                                tickfont=dict(family='Inter', color='#374151')
                            ),
                            yaxis=dict(
                                title=dict(text="수익률 (%)", font=dict(family='Inter', color='#374151')),
                                showgrid=True, gridcolor='rgba(148, 163, 184, 0.2)',
                                zeroline=True, zerolinecolor='rgba(148, 163, 184, 0.4)',
                                tickfont=dict(family='Inter', color='#374151')
                            ),
                            font=dict(color='#374151', family='Inter'),
                            margin=dict(l=50, r=30, t=60, b=50)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.markdown('<div style="text-align: center; padding: 40px; color: #6b7280;">📊 거래 데이터 없음</div>', unsafe_allow_html=True)
            
            # 📈 취소된 거래 요약 (있을 때만 표시)
            if not cancelled.empty:
                with st.container(border=True):
                    st.markdown('<h4 style="color: #6b7280; margin-bottom: 20px; font-family: Inter;">⏰ 최근 취소된 거래</h4>', unsafe_allow_html=True)
                    
                    for _, trade in cancelled.tail(3).iterrows():  # 최근 3개만
                        coin = trade['coin_ticker']
                        planned_entry = trade['entry_price']
                        timestamp = trade['timestamp'].strftime('%m/%d %H:%M')
                        
                        st.markdown(f"""
                        <div style="background: rgba(156, 163, 175, 0.1); padding: 16px; border-radius: 12px; margin-bottom: 12px; border-left: 4px solid #9ca3af;">
                            <div style="font-weight: 600; color: #374151; margin-bottom: 8px;">
                                📅 {timestamp} | {coin} | 계획 진입가: {format_price(planned_entry)}
                            </div>
                            <div style="font-size: 0.9rem; color: #6b7280;">
                                🚫 <strong>취소 사유:</strong> 1시간 내 진입가 미달성으로 자동 취소
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
        
        else:
            with st.container(border=True):
                st.markdown('<h3 style="color: #6b7280; text-align: center; font-family: Inter; margin: 40px 0;">📊 거래 데이터가 없습니다</h3>', unsafe_allow_html=True)
                st.markdown('<p style="color: #9ca3af; text-align: center; font-family: Inter;">첫 거래가 시작되면 데이터가 표시됩니다.</p>', unsafe_allow_html=True)
                
    with tab2:
        if not df_trades.empty:
            # CANCELLED는 실제 거래가 아니므로 성과 분석에서 제외
            completed_only = df_trades[df_trades['status'] == 'COMPLETED']
            cancelled_count = len(df_trades[df_trades['status'] == 'CANCELLED'])
            total_decisions = len(df_trades[df_trades['status'].isin(['COMPLETED', 'CANCELLED'])])
            
            # AI 의사결정 분석 (취소 거래가 있을 때만)
            if cancelled_count > 0 and total_decisions > 0:
                with st.container(border=True):
                    st.markdown('<h4 style="color: #374151; margin-bottom: 20px; font-family: Inter;">🤖 AI 의사결정 분석</h4>', unsafe_allow_html=True)
                    
                    col1, col2, col3 = st.columns(3)
                    
                    execution_rate = (len(completed_only) / total_decisions * 100)
                    
                    with col1:
                        st.metric("거래 실행률", f"{execution_rate:.1f}%", delta=f"{len(completed_only)}/{total_decisions}", delta_color="normal")
                    
                    with col2:
                        st.metric("진입가 미달성", f"{cancelled_count}회", delta="1시간 타임아웃", delta_color="off")
                    
                    with col3:
                        st.metric("평균 대기시간", "1.0시간", delta="최대 타임아웃", delta_color="normal")
                    
                    st.markdown(f"""
                    <div style="background: rgba(156, 163, 175, 0.1); padding: 16px; border-radius: 12px; margin-top: 16px;">
                        <p style="margin: 0; color: #374151; font-size: 0.95rem; line-height: 1.5;">
                        📊 <strong>취소율 {(cancelled_count/total_decisions*100):.1f}%</strong>: AI가 계획한 진입가에 1시간 내 도달하지 못해 자동 취소된 거래입니다. 
                        무리한 진입을 피하고 더 확실한 기회를 기다리는 것입니다.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
            
            # 성과 차트 (완료된 거래만)
            if len(completed_only) > 0:
                with st.container(border=True):
                    profit_chart = create_profit_chart(completed_only)
                    if profit_chart:
                        st.plotly_chart(profit_chart, use_container_width=True)
                
                # 월별 통계 (완료된 거래만)
                completed_trades = completed_only.copy()
                completed_trades['month'] = completed_trades['exit_timestamp'].dt.to_period('M')
                
                monthly_stats = completed_trades.groupby('month').agg({
                    'profit_rate': ['mean', 'sum', 'count'],
                    'profit_loss': 'sum',
                    'entry_fee': 'sum',
                    'exit_fee': 'sum'
                }).round(2)
                
                if not monthly_stats.empty:
                    with st.container(border=True):
                        st.markdown('<h3 style="color: #1e1b4b; margin-bottom: 25px; font-family: Inter;">📅 월별 성과 분석</h3>', unsafe_allow_html=True)
                        
                        monthly_df = pd.DataFrame({
                            '거래 횟수': monthly_stats[('profit_rate', 'count')],
                            '평균 수익률': monthly_stats[('profit_rate', 'mean')].apply(lambda x: f"{x:+.2f}%"),
                            '누적 수익률': monthly_stats[('profit_rate', 'sum')].apply(lambda x: f"{x:+.2f}%"),
                            '손익 (KRW)': monthly_stats[('profit_loss', 'sum')].apply(lambda x: f"₩{x:,.0f}"),
                            '총 수수료': (monthly_stats[('entry_fee', 'sum')] + monthly_stats[('exit_fee', 'sum')]).apply(lambda x: f"₩{x:,.0f}")
                        })
                        
                        st.dataframe(monthly_df, use_container_width=True)
            else:
                with st.container(border=True):
                    st.markdown('<h3 style="color: #6b7280; text-align: center; font-family: Inter; margin: 40px 0;">📈 성과 데이터가 충분하지 않습니다</h3>', unsafe_allow_html=True)
                    st.markdown('<p style="color: #9ca3af; text-align: center; font-family: Inter;">더 많은 거래가 완료되면 상세한 성과 분석을 제공합니다.</p>', unsafe_allow_html=True)
        else:
            with st.container(border=True):
                st.markdown('<h3 style="color: #6b7280; text-align: center; font-family: Inter; margin: 40px 0;">📈 성과 데이터가 없습니다</h3>', unsafe_allow_html=True)

    with tab3:
        if not df_trades.empty:
            with st.container(border=True):
                st.markdown('<h3 style="color: #1e1b4b; margin-bottom: 25px; font-family: Inter;">📜 전체 거래 내역</h3>', unsafe_allow_html=True)
                
                # 상태별 통계
                completed_count = len(df_trades[df_trades['status'] == 'COMPLETED'])
                cancelled_count = len(df_trades[df_trades['status'] == 'CANCELLED'])
                active_count = len(df_trades[df_trades['status'] == 'ACTIVE'])
                waiting_count = len(df_trades[df_trades['status'] == 'WAITING_ENTRY'])
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f'<div style="text-align: center; padding: 12px; background: rgba(16, 185, 129, 0.1); border-radius: 8px;"><strong>{completed_count}</strong><br>완료</div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f'<div style="text-align: center; padding: 12px; background: rgba(156, 163, 175, 0.1); border-radius: 8px;"><strong>{cancelled_count}</strong><br>취소</div>', unsafe_allow_html=True)
                
                with col3:
                    st.markdown(f'<div style="text-align: center; padding: 12px; background: rgba(59, 130, 246, 0.1); border-radius: 8px;"><strong>{active_count}</strong><br>진행중</div>', unsafe_allow_html=True)
                
                with col4:
                    st.markdown(f'<div style="text-align: center; padding: 12px; background: rgba(245, 158, 11, 0.1); border-radius: 8px;"><strong>{waiting_count}</strong><br>진입대기</div>', unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # 거래 내역 테이블
                display_df = df_trades[['timestamp', 'coin_ticker', 'status', 'entry_price', 
                                    'actual_entry_price', 'actual_exit_price', 
                                    'entry_fee', 'exit_fee', 'profit_rate', 'profit_loss']].copy()
                
                display_df = display_df.sort_values('timestamp', ascending=False).head(50)
                
                # 포맷팅
                display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                display_df['entry_price'] = display_df['entry_price'].apply(lambda x: format_price(x) if pd.notna(x) else "-")
                display_df['actual_entry_price'] = display_df['actual_entry_price'].apply(lambda x: format_price(x) if pd.notna(x) else "-")
                display_df['actual_exit_price'] = display_df['actual_exit_price'].apply(lambda x: format_price(x) if pd.notna(x) else "-")
                display_df['entry_fee'] = display_df['entry_fee'].apply(lambda x: f"₩{x:,.0f}" if pd.notna(x) and x > 0 else "-")
                display_df['exit_fee'] = display_df['exit_fee'].apply(lambda x: f"₩{x:,.0f}" if pd.notna(x) and x > 0 else "-")
                display_df['profit_rate'] = display_df['profit_rate'].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "-")
                display_df['profit_loss'] = display_df['profit_loss'].apply(lambda x: f"₩{x:,.0f}" if pd.notna(x) else "-")
                
                st.dataframe(
                    display_df,
                    column_config={
                        "timestamp": "시간",
                        "coin_ticker": "코인",
                        "status": "상태",
                        "entry_price": "계획 진입가",
                        "actual_entry_price": "실제 매수가",
                        "actual_exit_price": "실제 매도가",
                        "entry_fee": "매수 수수료",
                        "exit_fee": "매도 수수료",
                        "profit_rate": "수익률",
                        "profit_loss": "손익"
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # 취소 거래 상세 설명
                if cancelled_count > 0:
                    st.markdown('<h4 style="color: #6b7280; margin-top: 30px; font-family: Inter;">📋 CANCELLED 상태 설명</h4>', unsafe_allow_html=True)
                    st.markdown("""
                    <div style="background: rgba(156, 163, 175, 0.1); padding: 20px; border-radius: 12px; border-left: 4px solid #9ca3af;">
                        <p style="margin: 0; color: #374151; line-height: 1.6;">
                        <strong>CANCELLED</strong> 상태는 다음과 같은 경우에 발생합니다:<br><br>
                        • ⏰ <strong>1시간 타임아웃:</strong> AI가 계획한 진입가 근처(±0.2%)에 1시간 내 가격이 도달하지 못함<br>
                        • 🎯 <strong>정확한 조건:</strong> 예를 들어 계획 진입가가 100,000원이면 99,800원~100,200원 범위에 1시간 내 미도달<br>
                        • 🔄 <strong>시스템 동작:</strong> 타임아웃 후 자동으로 Phase 1부터 새로운 분석 시작<br><br>
                        <strong>이는 손실이 아니라 무리한 진입을 피한 현명한 선택입니다.</strong>
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            with st.container(border=True):
                st.markdown('<h3 style="color: #6b7280; text-align: center; font-family: Inter; margin: 40px 0;">📜 거래 내역이 없습니다</h3>', unsafe_allow_html=True)
                st.markdown('<p style="color: #9ca3af; text-align: center; font-family: Inter;">첫 거래가 시작되면 내역이 표시됩니다.</p>', unsafe_allow_html=True)


    # ========== 새로 추가된 회고 탭 ==========
    with tab4:
        st.markdown('<h2 style="color: #1e1b4b; margin-bottom: 30px; font-family: Inter; text-align: center;">🧠 AI 학습 및 거래 회고</h2>', unsafe_allow_html=True)
        
        if reflection_content and reflection_content.strip():
            # 간단한 통계 차트
            learning_chart = create_learning_progress_chart(reflection_content)
            if learning_chart:
                with st.container(border=True):
                    st.plotly_chart(learning_chart, use_container_width=True)
            
            # 회고 내용 전체 표시
            create_reflection_display(reflection_content)
        
        else:
            with st.container(border=True):
                st.markdown('<h3 style="color: #6b7280; text-align: center; font-family: Inter; margin: 40px 0;">🧠 아직 회고 데이터가 없습니다</h3>', unsafe_allow_html=True)
                st.markdown('<p style="color: #9ca3af; text-align: center; font-family: Inter;">거래가 완료되면 AI가 자동으로 회고를 생성합니다.</p>', unsafe_allow_html=True)
    
    # ========== 새로 추가된 원칙 탭 ==========
    with tab5:
        st.markdown('<h2 style="color: #1e1b4b; margin-bottom: 30px; font-family: Inter; text-align: center;">📚 AI 학습 원칙</h2>', unsafe_allow_html=True)
        
        create_principles_display(principles)
        
        # 원칙 업데이트 정보
        if principles:
            with st.container(border=True):
                st.markdown('<h3 style="color: #374151; margin-bottom: 20px; font-family: Inter;">🔄 원칙 업데이트 정보</h3>', unsafe_allow_html=True)
                
                # 원칙 파일 정보
                try:
                    principles_file = settings.PRINCIPLES_FILE
                    if os.path.exists(principles_file):
                        file_stat = os.stat(principles_file)
                        last_modified = datetime.fromtimestamp(file_stat.st_mtime)
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**📅 마지막 업데이트:**")
                            st.markdown(f'<div style="background: rgba(59, 130, 246, 0.1); padding: 12px; border-radius: 8px; font-family: Inter;">{last_modified.strftime("%Y-%m-%d %H:%M:%S")}</div>', unsafe_allow_html=True)
                        
                        with col2:
                            st.markdown("**📊 원칙 파일 크기:**")
                            file_size_kb = file_stat.st_size / 1024
                            st.markdown(f'<div style="background: rgba(16, 185, 129, 0.1); padding: 12px; border-radius: 8px; font-family: Inter;">{file_size_kb:.1f} KB</div>', unsafe_allow_html=True)
                        
                        # 다음 업데이트 예정 (일요일 23:00)
                        now = datetime.now()
                        next_sunday = now + timedelta(days=(6 - now.weekday()))
                        next_update = next_sunday.replace(hour=23, minute=0, second=0, microsecond=0)
                        
                        if next_update <= now:
                            next_update += timedelta(days=7)
                        
                        st.markdown("**⏰ 다음 자동 업데이트:**")
                        st.markdown(f'<div style="background: rgba(139, 92, 246, 0.1); padding: 12px; border-radius: 8px; font-family: Inter;">{next_update.strftime("%Y-%m-%d %H:%M:%S")} (매주 일요일 23시)</div>', unsafe_allow_html=True)
                
                except Exception as e:
                    st.error(f"원칙 파일 정보 조회 오류: {e}")
    
    with tab6:
        # 기존 새로고침 탭 코드 유지
        with st.container(border=True):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔄 데이터 새로고침", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()
            
            st.markdown('<div style="margin-top: 40px; color: rgba(107, 114, 128, 0.8); font-size: 1rem; text-align: center; font-family: Inter;">', unsafe_allow_html=True)
            st.markdown("💡 <strong>자동 새로고침이 비활성화되었습니다</strong>", unsafe_allow_html=True)
            st.markdown("필요시 위 버튼을 클릭하여 최신 데이터를 불러오세요.", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
