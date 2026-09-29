import os
import json
import time
import logging
import sqlite3
import pandas as pd
import pandas_ta as ta
import numpy as np
import re
from datetime import datetime, timedelta
import schedule
import pyupbit
from openai import OpenAI
from dotenv import load_dotenv
import time

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('omni_xrp.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """NumPy 타입을 Python 기본 타입으로 변환"""
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    else:
        return obj


class OMNIXRPSystem:
    """OMNI-XRP: 포지션 인식 + 시장체제 분석 OODA-R 루프 기반 XRP 전문 거래 시스템"""
    
    def __init__(self):
        """시스템 초기화"""
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.upbit = pyupbit.Upbit(
            os.getenv("UPBIT_ACCESS_KEY"), 
            os.getenv("UPBIT_SECRET_KEY")
        )
        self.db_path = 'omni_xrp_trades.sqlite'
        self.current_active_plan_id = None

        # 급변동 감지 위한 변수
        self.price_alert_threshold = 0.007  # 0.7% 변동 시 알림
        self.volume_spike_threshold = 2   # 거래량 2배 시 추가 알림
        self.emergency_cooldown = 180      # 3분 쿨다운
        self.last_emergency_time = None

        # 동적 분석 주기 관련 변수들
        self.current_analysis_interval = 30  # 현재 분석 주기 (분)
        self.last_regime_check = None        # 마지막 체제 확인 시간
        self.regime_change_cooldown = 300    # 5분 쿨다운 (너무 자주 변경 방지)
        self.last_interval_change = None     # 마지막 주기 변경 시간

        self.initialize_database()
        logger.info("🎯 OMNI-XRP 포지션 인식 + 시장체제 분석 시스템이 초기화되었습니다.")

    def initialize_database(self):
        """PostgreSQL 호환 SQLite 데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # trades 테이블 생성
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_ticker TEXT NOT NULL DEFAULT 'XRP',
                    status TEXT NOT NULL CHECK (status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED', 'SUPERSEDED')),
                    
                    -- 계획 단계 데이터
                    plan_timestamp TEXT NOT NULL,
                    planned_entry_price REAL NOT NULL,
                    planned_target_price REAL NOT NULL,
                    planned_stop_loss REAL NOT NULL,
                    entry_reason TEXT NOT NULL,
                    target_reason TEXT NOT NULL,
                    stop_loss_reason TEXT NOT NULL,
                    
                    -- 실행 단계 데이터
                    position_size_xrp REAL,
                    entry_timestamp TEXT,
                    actual_entry_price REAL,
                    exit_timestamp TEXT,
                    actual_exit_price REAL,
                    
                    -- 결과 단계 데이터
                    trade_result TEXT CHECK (trade_result IN ('PROFIT_TAKE', 'STOP_LOSS', 'MANUAL_EXIT')),
                    commission_krw REAL DEFAULT 0.0,
                    net_profit_krw REAL,
                    profit_rate_pct REAL
                )
            ''')
            
            conn.commit()
            logger.info("📊 데이터베이스가 초기화되었습니다.")

# =============================================================================
    # 2. 포지션 상태 관리
    # =============================================================================
    
    def check_current_position(self):
        """현재 XRP 보유 상태 확인"""
        try:
            # 업비트 잔고 확인
            xrp_balance = self.upbit.get_balance("XRP")
            
            # 활성 거래 확인
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT trade_id, actual_entry_price, planned_target_price, planned_stop_loss
                    FROM trades 
                    WHERE status = 'ACTIVE'
                    ORDER BY entry_timestamp DESC
                    LIMIT 1
                ''')
                active_trade = cursor.fetchone()
            
            has_position = xrp_balance > 0.0001  # 최소 보유량 기준
            has_active_trade = active_trade is not None
            
            return {
                'has_position': has_position,
                'xrp_balance': xrp_balance,
                'has_active_trade': has_active_trade,
                'active_trade_info': active_trade
            }
            
        except Exception as e:
            logger.error(f"❌ 현재 포지션 확인 중 오류: {e}")
            return {'has_position': False, 'xrp_balance': 0, 'has_active_trade': False, 'active_trade_info': None}

    def deactivate_all_planned_trades(self):
        """모든 PLANNED 상태 거래를 CANCELLED로 변경"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 현재 PLANNED 상태인 거래들 조회
                cursor.execute('''
                    SELECT trade_id FROM trades 
                    WHERE status = 'PLANNED'
                ''')
                planned_trades = cursor.fetchall()
                
                if planned_trades:
                    # 모든 PLANNED 거래를 CANCELLED로 변경
                    cursor.execute('''
                        UPDATE trades 
                        SET status = 'CANCELLED' 
                        WHERE status = 'PLANNED'
                    ''')
                    conn.commit()
                    
                    cancelled_count = len(planned_trades)
                    cancelled_ids = [str(trade[0]) for trade in planned_trades]
                    
                    logger.info(f"🚫 이전 거래 계획 {cancelled_count}개 비활성화: {', '.join(cancelled_ids)}")
                    return cancelled_count
                else:
                    logger.info("📝 비활성화할 거래 계획이 없습니다.")
                    return 0
                    
        except Exception as e:
            logger.error(f"❌ 거래 계획 비활성화 중 오류: {e}")
            return 0

    def _validate_and_cleanup_existing_plans(self):
        """시스템 시작 시 실제 포지션에 맞춰 DB 상태를 검증 및 정리 (강화된 버전)"""
        try:
            logger.info("🛡️ 시스템 시작 - DB 상태 검증 및 정리 작업 시작...")
            
            # 1. 실제 포지션 상태 확인
            position_status = self.check_current_position()
            has_position = position_status.get('has_position', False)
            xrp_balance = position_status.get('xrp_balance', 0)
            
            logger.info(f"💰 실제 XRP 보유 상태: {'보유 중' if has_position else '미보유'}")
            if has_position:
                logger.info(f"   보유량: {xrp_balance:.4f} XRP")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 현재 DB 상태 조회
                cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'PLANNED'")
                planned_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'ACTIVE'")
                active_count = cursor.fetchone()[0]
                
                logger.info(f"📊 현재 DB 상태: PLANNED={planned_count}개, ACTIVE={active_count}개")
                
                if has_position:
                    # [상황 A] 실제 XRP 보유 중
                    logger.info("🎯 XRP 보유 중 - ACTIVE 거래는 유지, PLANNED 거래는 모두 취소")
                    
                    # PLANNED 상태의 모든 거래를 CANCELLED로 변경
                    cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status = 'PLANNED'")
                    cancelled_planned = cursor.rowcount
                    
                    if cancelled_planned > 0:
                        logger.info(f"🗑️ 불필요한 PLANNED 거래 {cancelled_planned}개 정리 완료")
                    
                    # ACTIVE 거래 상태 확인
                    if active_count == 0:
                        logger.warning("⚠️ XRP 보유 중이지만 ACTIVE 거래가 없음 - 첫 전략 분석에서 처리 예정")
                    elif active_count > 1:
                        logger.warning(f"⚠️ ACTIVE 거래가 {active_count}개 - 최신 것만 유지")
                        # 가장 최근 ACTIVE만 남기고 나머지는 SUPERSEDED로 변경
                        cursor.execute('''
                            UPDATE trades 
                            SET status = 'SUPERSEDED' 
                            WHERE status = 'ACTIVE' 
                            AND trade_id NOT IN (
                                SELECT trade_id FROM trades 
                                WHERE status = 'ACTIVE' 
                                ORDER BY entry_timestamp DESC 
                                LIMIT 1
                            )
                        ''')
                        cleaned_count = cursor.rowcount
                        logger.info(f"🔧 중복 ACTIVE 거래 {cleaned_count}개를 SUPERSEDED로 정리")
                    else:
                        logger.info("✅ ACTIVE 거래 상태 정상")

                else:
                    # [상황 B] 실제 XRP 미보유
                    logger.info("💸 XRP 미보유 - 모든 ACTIVE 및 PLANNED 거래 정리")
                    
                    # ACTIVE 또는 PLANNED 상태의 모든 거래를 CANCELLED로 변경
                    cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status IN ('ACTIVE', 'PLANNED')")
                    cancelled_total = cursor.rowcount
                    
                    if cancelled_total > 0:
                        logger.info(f"👻 유령 거래/계획 {cancelled_total}개 정리 완료")
                    else:
                        logger.info("✅ 정리할 거래 없음 - 깨끗한 상태")
                
                conn.commit()
                logger.info("🛡️ DB 상태 검증 및 정리 완료. 시스템이 안전한 상태에서 시작됩니다.")
                
        except Exception as e:
            logger.error(f"❌ 시스템 시작 검증 중 치명적 오류: {e}")
            # 오류 발생 시 안전을 위해 모든 계획 비활성화
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status IN ('PLANNED', 'ACTIVE')")
                    conn.commit()
                logger.info("🚨 오류 발생으로 인한 안전 조치: 모든 계획 비활성화")
            except:
                logger.error("❌ 안전 조치마저 실패")

# =============================================================================
    # 3. OBSERVE - 시장 데이터 관찰
    # =============================================================================
    
    def observe_market_data(self):
        """관찰(Observe): XRP 시장 데이터 수집"""
        try:
            logger.info("🔍 시장 데이터 관찰 중...")
            
            # 현재 시간 및 가격
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 잔고 정보
            balances = self.upbit.get_balances()
            xrp_balance = 0
            krw_balance = 0
            xrp_avg_buy_price = 0
            
            for balance in balances:
                if balance['currency'] == "XRP":
                    xrp_balance = float(balance['balance'])
                    xrp_avg_buy_price = float(balance['avg_buy_price'])
                elif balance['currency'] == "KRW":
                    krw_balance = float(balance['balance'])
            
            # 포지션 상태 확인 추가
            position_status = self.check_current_position()
            
            # 다중 시간대 OHLCV 데이터
            df_5m = pyupbit.get_ohlcv("KRW-XRP", interval="minute5", count=200)
            time.sleep(0.5)
            df_15m = pyupbit.get_ohlcv("KRW-XRP", interval="minute15", count=200)
            time.sleep(0.5)
            df_1h = pyupbit.get_ohlcv("KRW-XRP", interval="minute60", count=200)
            time.sleep(0.5)
            df_4h = pyupbit.get_ohlcv("KRW-XRP", interval="minute240", count=200)
            time.sleep(0.5)
            df_day = pyupbit.get_ohlcv("KRW-XRP", interval="day", count=200)
            time.sleep(0.5)
            
            # A-D 그룹 기술적 지표 계산
            market_data = {
                'current_time': current_time,
                'current_price': current_price,
                'xrp_balance': xrp_balance,
                'krw_balance': krw_balance,
                'xrp_avg_buy_price': xrp_avg_buy_price,
                'position_status': position_status,  # 포지션 상태 추가
                'technical_indicators': self._calculate_comprehensive_indicators(
                    df_5m, df_15m, df_1h, df_4h, df_day
                )
            }
            
            logger.info(f"✅ 시장 데이터 수집 완료 - 현재가: {current_price:,.0f}원")
            return market_data
            
        except Exception as e:
            logger.error(f"❌ 시장 데이터 관찰 중 오류: {e}")
            return None
    
    def _calculate_comprehensive_indicators(self, df_5m, df_15m, df_1h, df_4h, df_day):
        """A-D 지표 그룹 종합 계산"""
        indicators = {}
        timeframes = {'5m': df_5m, '15m': df_15m, '1h': df_1h, '4h': df_4h, 'day': df_day}
        
        for tf, df in timeframes.items():
            try:
                current_price = float(df['close'].iloc[-1])
                
                # A. 추세 지표
                sma_20 = ta.sma(df['close'], length=20)
                sma_60 = ta.sma(df['close'], length=60)
                ema_12 = ta.ema(df['close'], length=12)
                ema_26 = ta.ema(df['close'], length=26)
                ema_60 = ta.ema(df['close'], length=60)
                macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
                
                trend_strength = 0
                if not pd.isna(sma_20.iloc[-1]) and not pd.isna(sma_60.iloc[-1]):
                    if current_price > sma_20.iloc[-1] > sma_60.iloc[-1]:
                        # 완벽한 상승 배열 - 강도 측정
                        strength_ratio = (current_price - sma_60.iloc[-1]) / sma_60.iloc[-1]
                        if strength_ratio > 0.05:  # 5% 이상 괴리
                            trend_strength = 2  # 강한 상승
                        else:
                            trend_strength = 1  # 약한 상승
                    elif current_price < sma_20.iloc[-1] < sma_60.iloc[-1]:
                        # 완벽한 하락 배열 - 강도 측정  
                        strength_ratio = (sma_60.iloc[-1] - current_price) / sma_60.iloc[-1]
                        if strength_ratio > 0.05:  # 5% 이상 괴리
                            trend_strength = -2  # 강한 하락
                        else:
                            trend_strength = -1  # 약한 하락
                
                golden_cross = False
                death_cross = False
                if len(sma_20) >= 2 and len(sma_60) >= 2:
                    golden_cross = (sma_20.iloc[-1] > sma_60.iloc[-1] and sma_20.iloc[-2] <= sma_60.iloc[-2])
                    death_cross = (sma_20.iloc[-1] < sma_60.iloc[-1] and sma_20.iloc[-2] >= sma_60.iloc[-2])
                
                macd_bullish = False
                macd_bearish = False
                if macd is not None and len(macd) >= 2:
                    try:
                        macd_line = macd['MACD_12_26_9']
                        macd_signal = macd['MACDs_12_26_9']
                        if not pd.isna(macd_line.iloc[-1]) and not pd.isna(macd_signal.iloc[-1]):
                            macd_bullish = (macd_line.iloc[-1] > macd_signal.iloc[-1] and 
                                           macd_line.iloc[-2] <= macd_signal.iloc[-2])
                            macd_bearish = (macd_line.iloc[-1] < macd_signal.iloc[-1] and 
                                           macd_line.iloc[-2] >= macd_signal.iloc[-2])
                    except KeyError:
                        pass
                
                # B. 모멘텀 지표
                rsi_14 = ta.rsi(df['close'], length=14)
                stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3)
                willr = ta.willr(df['high'], df['low'], df['close'], length=14)
                rsi_divergence = self._detect_rsi_divergence(df['close'], rsi_14)
                
                # C. 변동성 지표
                bbands = ta.bbands(df['close'], length=20, std=2)
                atr = ta.atr(df['high'], df['low'], df['close'], length=14)
                bb_squeeze = self._detect_bb_squeeze(bbands)
                bb_position = self._calculate_bb_position(current_price, bbands)
                
                # D. 거래량 지표
                volume_sma_20 = ta.sma(df['volume'], length=20)
                volume_ratio = 1.0
                if not pd.isna(volume_sma_20.iloc[-1]) and volume_sma_20.iloc[-1] > 0:
                    volume_ratio = df['volume'].iloc[-1] / volume_sma_20.iloc[-1]
                
                obv = ta.obv(df['close'], df['volume'])
                vwap = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
                
                volume_spike = volume_ratio > 2.0
                volume_confirmation = volume_ratio > 1.5
                
                # 통합 지표 저장 (안전한 변환)
                indicators[tf] = {
                    'trend': {
                        'sma_20': self._safe_float(sma_20.iloc[-1], current_price),
                        'sma_60': self._safe_float(sma_60.iloc[-1], current_price),
                        'ema_12': self._safe_float(ema_12.iloc[-1], current_price),
                        'ema_26': self._safe_float(ema_26.iloc[-1], current_price),
                        'ema_60': self._safe_float(ema_60.iloc[-1], current_price), 
                        'trend_strength': int(trend_strength),
                        'golden_cross': bool(golden_cross),
                        'death_cross': bool(death_cross),
                        'macd_line': self._safe_float(macd['MACD_12_26_9'].iloc[-1] if macd is not None else 0, 0),
                        'macd_signal': self._safe_float(macd['MACDs_12_26_9'].iloc[-1] if macd is not None else 0, 0),
                        'macd_histogram': self._safe_float(macd['MACDh_12_26_9'].iloc[-1] if macd is not None else 0, 0),
                        'macd_bullish': bool(macd_bullish),
                        'macd_bearish': bool(macd_bearish)
                    },
                    'momentum': {
                        'rsi': self._safe_float(rsi_14.iloc[-1], 50),
                        'rsi_oversold': bool(self._safe_float(rsi_14.iloc[-1], 50) < 30),
                        'rsi_overbought': bool(self._safe_float(rsi_14.iloc[-1], 50) > 70),
                        'rsi_divergence': rsi_divergence,
                        'stoch_k': self._safe_float(stoch['STOCHk_14_3_3'].iloc[-1] if stoch is not None else 50, 50),
                        'stoch_d': self._safe_float(stoch['STOCHd_14_3_3'].iloc[-1] if stoch is not None else 50, 50),
                        'willr': self._safe_float(willr.iloc[-1], -50)
                    },
                    'volatility': {
                        'bb_upper': self._safe_float(bbands['BBU_20_2.0'].iloc[-1] if bbands is not None else current_price * 1.02, current_price * 1.02),
                        'bb_middle': self._safe_float(bbands['BBM_20_2.0'].iloc[-1] if bbands is not None else current_price, current_price),
                        'bb_lower': self._safe_float(bbands['BBL_20_2.0'].iloc[-1] if bbands is not None else current_price * 0.98, current_price * 0.98),
                        'bb_position': float(bb_position),
                        'bb_squeeze': bool(bb_squeeze),
                        'atr': self._safe_float(atr.iloc[-1], 0),
                        'atr_ratio': float(self._safe_float(atr.iloc[-1], 0) / current_price * 100) if current_price > 0 else 0
                    },
                    'volume': {
                        'current_volume': float(df['volume'].iloc[-1]),
                        'volume_sma_20': self._safe_float(volume_sma_20.iloc[-1], 0),
                        'volume_ratio': float(volume_ratio),
                        'volume_spike': bool(volume_spike),
                        'volume_confirmation': bool(volume_confirmation),
                        'obv': self._safe_float(obv.iloc[-1], 0),
                        'vwap': self._safe_float(vwap.iloc[-1], current_price)
                    },
                    'ohlc': {
                        'open': float(df['open'].iloc[-1]),
                        'high': float(df['high'].iloc[-1]),
                        'low': float(df['low'].iloc[-1]),
                        'close': current_price
                    }
                }
                
            except Exception as e:
                logger.warning(f"⚠️ {tf} 지표 계산 중 오류: {e}")
                current_price = float(df['close'].iloc[-1])
                indicators[tf] = self._get_fallback_indicators(current_price)
        
        return indicators
    
    def _safe_float(self, value, default):
        """안전한 float 변환"""
        try:
            if pd.isna(value):
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)
    
    def _detect_rsi_divergence(self, price_series, rsi_series, lookback=10):
        """RSI 다이버전스 감지"""
        try:
            if len(price_series) < lookback or len(rsi_series) < lookback:
                return "none"
            
            recent_prices = price_series.tail(lookback)
            recent_rsi = rsi_series.tail(lookback)
            
            # 상승 다이버전스: 가격↓, RSI↑
            if (recent_prices.iloc[-1] < recent_prices.iloc[0] and 
                recent_rsi.iloc[-1] > recent_rsi.iloc[0]):
                return "bullish"
            # 하락 다이버전스: 가격↑, RSI↓
            elif (recent_prices.iloc[-1] > recent_prices.iloc[0] and 
                  recent_rsi.iloc[-1] < recent_rsi.iloc[0]):
                return "bearish"
            
            return "none"
        except Exception:
            return "none"
    
    def _detect_bb_squeeze(self, bbands, threshold=0.7):
        """볼린저 밴드 스퀴즈 감지"""
        try:
            if bbands is None or len(bbands) < 20:
                return False
            
            current_width = (bbands['BBU_20_2.0'].iloc[-1] - bbands['BBL_20_2.0'].iloc[-1])
            avg_width = ((bbands['BBU_20_2.0'] - bbands['BBL_20_2.0']).tail(20).mean())
            
            return current_width < avg_width * threshold
        except Exception:
            return False
    
    def _calculate_bb_position(self, current_price, bbands):
        """볼린저 밴드 내 현재가 위치 (0~1)"""
        try:
            if bbands is None:
                return 0.5
            
            bb_upper = bbands['BBU_20_2.0'].iloc[-1]
            bb_lower = bbands['BBL_20_2.0'].iloc[-1]
            
            if bb_upper == bb_lower:
                return 0.5
            
            position = (current_price - bb_lower) / (bb_upper - bb_lower)
            return max(0, min(1, position))
        except Exception:
            return 0.5
    
    def _get_fallback_indicators(self, current_price):
        """지표 계산 실패 시 기본값"""
        return {
            'trend': {
                'sma_20': current_price, 'sma_60': current_price,
                'ema_12': current_price, 'ema_26': current_price, 'ema_60': current_price, 
                'trend_strength': 0, 'golden_cross': False, 'death_cross': False,
                'macd_line': 0, 'macd_signal': 0, 'macd_histogram': 0,
                'macd_bullish': False, 'macd_bearish': False
            },
            'momentum': {
                'rsi': 50, 'rsi_oversold': False, 'rsi_overbought': False,
                'rsi_divergence': 'none', 'stoch_k': 50, 'stoch_d': 50, 'willr': -50
            },
            'volatility': {
                'bb_upper': current_price * 1.02, 'bb_middle': current_price,
                'bb_lower': current_price * 0.98, 'bb_position': 0.5,
                'bb_squeeze': False, 'atr': 0, 'atr_ratio': 0
            },
            'volume': {
                'current_volume': 0, 'volume_sma_20': 0, 'volume_ratio': 1,
                'volume_spike': False, 'volume_confirmation': False,
                'obv': 0, 'vwap': current_price
            },
            'ohlc': {
                'open': current_price, 'high': current_price,
                'low': current_price, 'close': current_price
            }
        }

# =============================================================================
    # 4. 시장체제 분석 (신규 핵심 기능)
    # =============================================================================
    
    def _analyze_market_regime(self, market_data):
        """다중 시간프레임 균형 잡힌 시장체제 분석 (디버깅 로그 강화)"""
        try:
            indicators = market_data['technical_indicators']
            current_price = market_data['current_price']
            
            logger.info("🎯 시장체제 분석 시작")
            logger.info(f"기준 현재가: {current_price:,.0f}원")
            
            # 각 시간프레임별 상세 분석 및 로깅
            for tf in ['5m', '15m', '1h', '4h', 'day']:
                if tf in indicators:
                    tf_trend = indicators[tf]['trend']
                    sma_20 = tf_trend.get('sma_20', current_price)
                    sma_60 = tf_trend.get('sma_60', current_price)
                    ema_60 = tf_trend.get('ema_60', current_price)
                    trend_strength = tf_trend.get('trend_strength', 0)
                    
                    # 추세 배열 분석
                    if current_price > sma_20 > sma_60:
                        trend_desc = "✅ 상승 배열"
                    elif current_price < sma_20 < sma_60:
                        trend_desc = "❌ 하락 배열"
                    else:
                        trend_desc = "🔄 혼조 배열"
                        
                    logger.info(f"📊 {tf} 분석:")
                    logger.info(f"   현재가: {current_price:,.0f}원")
                    logger.info(f"   SMA20: {sma_20:,.0f}원")
                    logger.info(f"   SMA60: {sma_60:,.0f}원")
                    logger.info(f"   EMA60: {ema_60:,.0f}원")
                    logger.info(f"   {trend_desc}")
                    logger.info(f"   추세강도: {trend_strength}")
        
            # 균등 가중치 시간프레임별 점수 계산
            timeframe_scores = {}
            timeframe_weights = {
                '5m': 0.15,   # 단기 신호 중요도 증가
                '15m': 0.20,  # 단기 신호 중요도 증가  
                '1h': 0.25,   # 중기 신호 중요도 증가
                '4h': 0.25,   # 중기 신호 중요도 유지
                'day': 0.15   # 장기 신호 중요도 감소 (기존 80% → 15%)
            }
            
            total_weighted_score = 0
            logger.info("🧮 시간프레임별 점수 계산:")
            
            for tf, weight in timeframe_weights.items():
                if tf not in indicators:
                    continue
                    
                tf_data = indicators[tf]['trend']
                sma_20 = tf_data.get('sma_20', current_price)
                sma_60 = tf_data.get('sma_60', current_price)
                ema_60 = tf_data.get('ema_60', current_price)
                
                # 각 시간프레임별 추세 점수 (-3 ~ +3)
                tf_score = 0
                
                # 정교한 추세 점수 계산
                if current_price > sma_20 > sma_60:
                    # 완벽한 상승 배열 - 강도에 따라 차등 점수
                    strength_ratio = (current_price - sma_60) / sma_60
                    if strength_ratio > 0.05:  # 5% 이상 괴리
                        tf_score = 3  # 강한 상승
                    else:
                        tf_score = 2  # 약한 상승
                elif current_price < sma_20 < sma_60:
                    # 완벽한 하락 배열 - 강도에 따라 차등 점수
                    strength_ratio = (sma_60 - current_price) / sma_60
                    if strength_ratio > 0.05:  # 5% 이상 괴리
                        tf_score = -3  # 강한 하락
                    else:
                        tf_score = -2  # 약한 하락
                elif current_price > ema_60:
                    tf_score = 1  # 장기 상승
                elif current_price < ema_60:
                    tf_score = -1  # 장기 하락
                
                # 골든/데스크로스 추가 점수
                if tf_data.get('golden_cross', False):
                    tf_score += 1
                elif tf_data.get('death_cross', False):
                    tf_score -= 1
                
                timeframe_scores[tf] = tf_score
                weighted_contribution = tf_score * weight
                total_weighted_score += weighted_contribution
                
                logger.info(f"   {tf}: 점수={tf_score}, 가중치={weight:.2f}, 기여도={weighted_contribution:.2f}")
            
            # 하락 배열 페널티 (단기 시간대 중심)
            downtrend_penalty = 0
            short_term_frames = ['5m', '15m', '1h']
            downtrend_count = 0
            
            for tf in short_term_frames:
                if tf in timeframe_scores and timeframe_scores[tf] <= -2:
                    downtrend_count += 1
                    downtrend_penalty -= 0.5  # 단기 강하락마다 -0.5점
            
            # 3개 시간대 모두 하락이면 추가 페널티
            if downtrend_count >= 3:
                downtrend_penalty -= 1.0  # 추가 -1점
            
            # 변동성 분석
            h4_indicators = indicators.get('4h', {})
            day_indicators = indicators.get('day', {})
            
            h4_volatility = h4_indicators.get('volatility', {})
            day_volatility = day_indicators.get('volatility', {})
            
            h4_atr_ratio = h4_volatility.get('atr_ratio', 2.0)
            day_atr_ratio = day_volatility.get('atr_ratio', 2.0)
            bb_squeeze = day_volatility.get('bb_squeeze', False)
            
            is_sideways = (h4_atr_ratio < 1.2 and day_atr_ratio < 1.5) or bb_squeeze
            is_high_volatility = h4_atr_ratio > 3.0 or day_atr_ratio > 3.0
            
            # 최종 점수 계산
            final_score = total_weighted_score + downtrend_penalty
            
            logger.info(f"🧮 체제 점수 상세:")
            logger.info(f"   기본 가중 점수: {total_weighted_score:.2f}")
            logger.info(f"   하락 배열 페널티: {downtrend_penalty:.2f} (하락프레임: {downtrend_count}개)")
            logger.info(f"   최종 점수: {final_score:.2f}")
            logger.info(f"   변동성 상태: 횡보={is_sideways}, 고변동={is_high_volatility}")
            
            # 비트코인 분석
            btc_analysis = self._analyze_bitcoin_correlation(market_data)
            structure_analysis = self._check_market_structure_shift(market_data)
            
            # 비트코인 조정
            adjusted_regime_score = final_score
            confidence_modifiers = []
            
            if btc_analysis['btc_influence'] == "높음":
                btc_1h_change = btc_analysis.get('btc_1h_change', 0)
                if btc_1h_change < -2:
                    adjusted_regime_score -= 1
                    confidence_modifiers.append("BTC강하락위험")
                    logger.info(f"🔻 비트코인 강하락({btc_1h_change:.2f}%) 감지 - 체제 점수 하향 조정")
                elif btc_1h_change > 2:
                    adjusted_regime_score += 1
                    logger.info(f"🔺 비트코인 강상승({btc_1h_change:.2f}%) 감지 - 체제 점수 상향 조정")
            
            if structure_analysis['structure_shift_risk'] == "높음":
                adjusted_regime_score -= 1
                confidence_modifiers.append("구조변화위험")
            
            confidence = "높음"
            
            if adjusted_regime_score <= -2.0 and not is_sideways:  
                market_regime = "명백한_하락장"
                risk_level = "매우높음"
                trading_approach = "매매금지"
            elif adjusted_regime_score >= 2.0 and not is_sideways:  
                market_regime = "명백한_상승장" 
                risk_level = "보통"
                trading_approach = "적극매매"
            elif is_sideways:
                market_regime = "횡보_박스권"
                risk_level = "보통"
                trading_approach = "단기매매"
                confidence = "중간"
            elif is_high_volatility:
                market_regime = "고변동성_혼조장"
                risk_level = "높음"
                trading_approach = "신중매매"
                confidence = "낮음"
            elif abs(adjusted_regime_score) < 0.5:  
                market_regime = "애매한_혼조장"
                risk_level = "높음"
                trading_approach = "신중매매"
                confidence = "낮음"
            else:
                market_regime = "혼조장"
                risk_level = "높음"
                trading_approach = "신중매매"
                confidence = "낮음"
            
            # 신뢰도 조정
            if confidence_modifiers:
                if confidence == "높음":
                    confidence = "중간"
                elif confidence == "중간":
                    confidence = "낮음"
                else:
                    confidence = "매우낮음"
            
            # 신뢰도 점수 계산
            reliability_score = self._calculate_reliability_score(
                {'regime': market_regime, 'confidence': confidence}, 
                btc_analysis, 
                structure_analysis
            )
            
            logger.info(f"🎯 최종 체제 결정:")
            logger.info(f"   최종 체제 점수: {adjusted_regime_score:.2f}/5")
            logger.info(f"   ✅ 결정: {market_regime}")
            logger.info(f"   접근법: {trading_approach}")
            logger.info(f"   신뢰도: {confidence}")
            
            # 결과 반환 (기존 구조 유지)
            return {
                'regime': market_regime,
                'risk_level': risk_level,
                'approach': trading_approach,
                'confidence': confidence,
                'regime_score': adjusted_regime_score,
                'original_score': final_score,
                'timeframe_scores': timeframe_scores,  
                'downtrend_penalty': downtrend_penalty,  
                'long_term_trend': 'up' if timeframe_scores.get('day', 0) > 0 else 'down',
                'short_term_trend': 'up' if timeframe_scores.get('5m', 0) > 0 else 'down', 
                'ma_alignment': "상승" if final_score > 0 else "하락",
                'volatility_state': 'compressed' if is_sideways else 'high' if is_high_volatility else 'normal',
                'key_signals': {
                    'golden_cross': any(indicators.get(tf, {}).get('trend', {}).get('golden_cross', False) for tf in ['1h', '4h']),
                    'death_cross': any(indicators.get(tf, {}).get('trend', {}).get('death_cross', False) for tf in ['1h', '4h']),
                    'bb_squeeze': bb_squeeze,
                    'atr_ratio_4h': h4_atr_ratio,
                    'atr_ratio_day': day_atr_ratio
                },
                'btc_analysis': btc_analysis,
                'structure_analysis': structure_analysis,
                'confidence_modifiers': confidence_modifiers,
                'reliability_score': reliability_score
            }
            
        except Exception as e:
            logger.error(f"강화된 시장 체제 분석 중 오류: {e}")
            return {
                'regime': '분석실패',
                'risk_level': '매우높음',
                'approach': '매매금지',
                'confidence': '없음',
                'regime_score': 0,
                'reliability_score': 0
            }

    def _calculate_dynamic_prices_with_atr(self, market_data, entry_type="conservative"):
        """ATR 기반 동적 가격 계산"""
        try:
            current_price = market_data['current_price']
            
            # ATR 값 가져오기 (4시간봉 우선, 없으면 1시간봉)
            h4_atr = market_data['technical_indicators'].get('4h', {}).get('volatility', {}).get('atr', 0)
            h1_atr = market_data['technical_indicators'].get('1h', {}).get('volatility', {}).get('atr', 0)
            
            # ATR이 없으면 현재가의 2%로 추정
            atr = h4_atr if h4_atr > 0 else h1_atr if h1_atr > 0 else current_price * 0.02
            
            if entry_type == "conservative":  # 하락장용
                entry_price = current_price - (atr * 0.5)  # ATR의 0.5배 아래서 진입
                target_price = current_price + (atr * 0.8)  # ATR의 0.8배 목표
                stop_loss = entry_price - (atr * 1.2)      # ATR의 1.2배 손절
                
            elif entry_type == "sideways":   # 횡보장용
                bb_lower = market_data['technical_indicators'].get('1h', {}).get('volatility', {}).get('bb_lower', current_price * 0.98)
                bb_middle = market_data['technical_indicators'].get('1h', {}).get('volatility', {}).get('bb_middle', current_price)
                
                entry_price = max(bb_lower, current_price - (atr * 0.3))  # 밴드 하단과 ATR 중 더 보수적인 값
                target_price = bb_middle
                stop_loss = bb_lower - (atr * 0.5)  # 밴드 이탈 + ATR 버퍼
                
            else:  # "aggressive" - 상승장용
                entry_price = current_price + (atr * 0.2)  # 약간의 추격 매수
                target_price = current_price + (atr * 2.0)  # ATR의 2배 목표
                stop_loss = current_price - (atr * 1.0)    # ATR의 1배 손절
            
            return {
                'entry_price': round(entry_price, 0),
                'target_price': round(target_price, 0),
                'stop_loss': round(stop_loss, 0),
                'atr_used': round(atr, 0),
                'atr_ratio': round(atr / current_price * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"ATR 기반 가격 계산 중 오류: {e}")
            return None

    def _create_no_trade_response(self, market_regime, reason):
        """매매 금지 응답 생성"""
        return {
            "market_analysis": {
                "trend_group": f"시장체제: {market_regime['regime']}",
                "momentum_group": f"체제 점수: {market_regime.get('regime_score', 0)}",
                "volatility_group": f"변동성: {market_regime.get('volatility_state', 'unknown')}",
                "volume_group": "매매 금지로 거래량 분석 불필요",
                "overall_confidence": "매매 금지",
                "market_condition": "약세장"
            },
            "risk_assessment": {
                "risk_level": "매우높음",
                "position_size": "매매 금지",
                "max_holding_time": "해당없음",
                "key_risks": f"시장체제 '{market_regime['regime']}'에서 매수는 위험"
            },
            "entry_price": 0,
            "target_price": 0,
            "stop_loss_price": 0,
            "entry_reason": f"OMNI 시스템 1차 진단: {market_regime['regime']} → {reason}",
            "target_reason": "매매 금지 상황으로 목표가 설정 불필요",
            "stop_loss_reason": "매매하지 않으므로 손절가 설정 불필요",
            "sell_strategy": "기존 포지션이 있다면 시장 상황에 따른 방어적 매도 검토",
            "lessons_applied": f"시장체제 인식을 통한 선제적 리스크 회피 (체제: {market_regime['regime']})"
        }

    def _get_regime_specific_guidance(self, market_regime):
        """체제별 구체적 가이던스"""
        regime_guidance = {
            "명백한_하락장": """
⚠️ **하드코딩 안전 규칙 발동**: 떨어지는 칼날을 잡지 마라
- 원칙: 매매 금지 (entry_price = 0)
- 예외: 4시간+일봉 동시 골든크로스 + RSI 과매도 + 거래량 급증 시에만 극소량 고려
- 리스크: 데드캣 바운스에 속을 위험 항상 염두""",
            
            "횡보_박스권": """
📊 **Mean Reversion 전략 권장**
- 우선순위: 볼린저밴드 하단(30% 이하) + RSI 과매도(40 이하) 조합
- 목표: 밴드 중심선, 손절: 밴드 하단 이탈
- 주의: 박스권 돌파 시 즉시 손절 (추세 전환 가능성)""",
            
            "명백한_상승장": """
🚀 **추세 추종 전략 권장**
- 우선순위: 기존 OMNI의 A-D 지표 종합 분석 최대 활용
- 접근: 적극적 매수, 긴 목표가, 추세 기반 손절
- 기회: 다중 시간대 상승 신호 일치 시 포지션 확대 고려""",
            
            "고변동성_혼조장": """
⚡ **신중한 기회주의 전략**
- 원칙: 매우 명확한 신호에서만 단기 매매
- 조건: 3개 이상 시간대에서 동일 방향 신호 + 거래량 확인
- 리스크: 변동성이 크므로 ATR 기반 넓은 손절""",
            
            "애매한_혼조장": """
🤔 **대기 우선 전략**
- 원칙: 명확한 방향성 확인까지 대기 우선
- 조건: 특별히 강한 신호 조합에서만 제한적 진입
- 포지션: 평소의 50% 이하 소량으로 제한"""
        }
        
        return regime_guidance.get(market_regime['regime'], "해당 체제 가이던스 없음")

    def _analyze_bitcoin_correlation(self, market_data):
        """비트코인과의 상관관계 분석 (XRP는 비트코인 영향 크게 받음)"""
        try:
            # 비트코인 데이터 수집
            btc_1h = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=50)
            time.sleep(0.5)
            xrp_1h = pyupbit.get_ohlcv("KRW-XRP", interval="minute60", count=50)
            time.sleep(0.5)
            
            # 수익률 계산
            btc_returns = btc_1h['close'].pct_change().dropna()
            xrp_returns = xrp_1h['close'].pct_change().dropna()
            
            # 상관계수 계산
            correlation = btc_returns.corr(xrp_returns)
            
            # 비트코인 추세 확인
            btc_current = float(btc_1h['close'].iloc[-1])
            btc_sma20 = btc_1h['close'].rolling(20).mean().iloc[-1]
            btc_trend = "상승" if btc_current > btc_sma20 else "하락"
            
            # 비트코인 단기 변동 확인 (중요!)
            btc_1h_change = ((btc_current - btc_1h['close'].iloc[-2]) / btc_1h['close'].iloc[-2] * 100)
            
            return {
                'correlation': correlation,
                'btc_trend': btc_trend,
                'btc_1h_change': btc_1h_change,
                'btc_influence': "높음" if abs(correlation) > 0.7 else "보통" if abs(correlation) > 0.4 else "낮음"
            }
            
        except Exception as e:
            logger.error(f"비트코인 상관관계 분석 중 오류: {e}")
            return {'correlation': 0.5, 'btc_trend': '알수없음', 'btc_1h_change': 0, 'btc_influence': '분석실패'}

    def _check_market_structure_shift(self, market_data):
        """시장 구조 변화 감지 (단순 기술적 분석으로 놓칠 수 있는 패러다임 변화)"""
        try:
            indicators = market_data['technical_indicators']
            
            # 다중 시간대 divergence 확인
            divergence_signals = 0
            timeframes = ['1h', '4h', 'day']
            
            for tf in timeframes:
                if tf in indicators:
                    tf_data = indicators[tf]
                    # RSI와 가격의 divergence
                    rsi_div = tf_data.get('momentum', {}).get('rsi_divergence', 'none')
                    if rsi_div in ['bullish', 'bearish']:
                        divergence_signals += 1
            
            # 거래량 패턴 이상 감지
            volume_anomaly = False
            if 'day' in indicators:
                recent_volume = indicators['day']['volume']['volume_ratio']
                if recent_volume > 3.0 or recent_volume < 0.3:  # 극단적 거래량
                    volume_anomaly = True
            
            # 변동성 급변 감지
            volatility_spike = False
            if 'day' in indicators:
                atr_ratio = indicators['day']['volatility']['atr_ratio']
                if atr_ratio > 5.0:  # 일일 변동성이 5% 초과
                    volatility_spike = True
            
            structure_shift_risk = "높음" if (divergence_signals >= 2 or volume_anomaly or volatility_spike) else "낮음"
            
            return {
                'divergence_signals': divergence_signals,
                'volume_anomaly': volume_anomaly,
                'volatility_spike': volatility_spike,
                'structure_shift_risk': structure_shift_risk
            }
            
        except Exception as e:
            logger.error(f"시장 구조 변화 감지 중 오류: {e}")
            return {'structure_shift_risk': '분석실패'}

    def _calculate_reliability_score(self, base_regime, btc_analysis, structure_analysis):
        """시장 판단의 신뢰도 점수 (0-100)"""
        score = 70  # 기본 점수
        
        # 기존 분석 신뢰도
        if base_regime['confidence'] == "높음":
            score += 20
        elif base_regime['confidence'] == "중간":
            score += 10
        elif base_regime['confidence'] == "낮음":
            score -= 10
        
        # 비트코인 일치성
        if btc_analysis['btc_influence'] == "높음":
            if ((base_regime['regime'] in ["명백한_상승장", "횡보_박스권"] and btc_analysis['btc_trend'] == "상승") or
                (base_regime['regime'] == "명백한_하락장" and btc_analysis['btc_trend'] == "하락")):
                score += 15  # 일치하면 가점
            else:
                score -= 20  # 불일치하면 큰 감점
        
        # 구조적 위험
        if structure_analysis['structure_shift_risk'] == "높음":
            score -= 25
        
        return max(0, min(100, score))

# =============================================================================
    # 5. ORIENT & DECIDE - 포지션 인식 + 시장체제 전략 수립
    # =============================================================================
    
    def orient_and_decide(self, market_data):
        """판단(Orient) & 결정(Decide): 포지션 인식 + 시장체제 고도화된 전략 수립"""
        try:
            logger.info("🧠 포지션 인식 + 시장체제 AI 전략 수립 중...")
            
            # 포지션 상태 확인
            position_status = market_data.get('position_status', {})
            has_position = position_status.get('has_position', False)
            
            if has_position:
                logger.info("🎯 XRP 보유 중 - 포지션 관리 조언 모드")
                return self._generate_position_management_advice(market_data)
            else:
                logger.info("💰 XRP 미보유 - 시장체제 분석 기반 신규 매수 전략 수립 모드")
                return self._generate_new_entry_strategy(market_data)
                
        except Exception as e:
            logger.error(f"❌ 포지션 인식 + 시장체제 전략 수립 중 오류: {e}")
            return None
    
    def _generate_position_management_advice(self, market_data):
        """XRP 보유 중일 때 시장체제 분석 기반 포지션 관리 조언"""
        try:
            # 1. 시장체제 분석 (보유 중에도 체제 변화 감지)
            market_regime = self._analyze_market_regime(market_data)
            logger.info(f"🎯 포지션 관리 - 현재 체제: {market_regime['regime']} (접근법: {market_regime['approach']})")
            
            # NumPy 타입을 Python 기본 타입으로 변환
            market_data_serializable = convert_numpy_types(market_data)
            
            # 현재 활성 거래 정보
            position_status = market_data.get('position_status', {})
            active_trade = position_status.get('active_trade_info')
            current_price = market_data['current_price']
            
            # 수익/손실 상태 계산
            profit_status = "알수없음"
            profit_rate = 0
            if active_trade and len(active_trade) >= 2 and active_trade[1]:
                entry_price = active_trade[1]
                profit_rate = ((current_price - entry_price) / entry_price * 100)
                if profit_rate > 0:
                    profit_status = f"수익권 (+{profit_rate:.2f}%)"
                else:
                    profit_status = f"손실권 ({profit_rate:.2f}%)"
            
            market_context = self._analyze_current_market_context(market_data)
            learned_lessons = self._extract_learned_lessons()
            position_prompt = self.load_position_management_prompt()
            
            # 시장체제별 특화 포지션 관리 가이던스
            regime_guidance = self._get_position_management_guidance(market_regime, profit_rate)
            
            # 포지션 관리 전용 프롬프트 (시장체제 분석 통합)
            management_prompt = f"""
{position_prompt}

## 🎯 현재 포지션 상황 분석
- **현재가**: {current_price:,.0f}원
- **수익 상태**: {profit_status}  
- **시장 체제**: {market_regime['regime']} (접근법: {market_regime['approach']})
- **체제 신뢰도**: {market_regime['confidence']}
- **체제 점수**: {market_regime.get('regime_score', 0)}/5

## 🔬 실시간 시장 데이터
{json.dumps(market_data_serializable, indent=2, ensure_ascii=False)}

## 🎯 현재 활성 거래 정보
- 거래 ID: {active_trade[0] if active_trade else 'N/A'}
- 진입가: {active_trade[1]:,.0f}원 ({active_trade} else 'N/A')
- 목표가: {active_trade[2]:,.0f}원 ({active_trade} else 'N/A')
- 손절가: {active_trade[3]:,.0f}원 ({active_trade} else 'N/A')
- XRP 보유량: {position_status.get('xrp_balance', 0):.4f} XRP

## 💡 시장체제별 포지션 관리 전략
{regime_guidance}

## 🧠 시장 맥락 분석
{market_context}

## 🎓 축적된 핵심 교훈
{learned_lessons}

⚠️ **엄격한 리스크 관리 원칙**:
- 손실액과 손실률을 종합 고려한 빠른 탈출 검토
- "기술적 반등 기대"보다는 "추가 손실 방지" 우선  
- 불확실한 시장에서는 보수적 손절가 조정
- 하락장 전환 시 즉시 방어적 매도 검토
- 손실권에서는 트레일링보다 손절 우선

🚀 **적극적 자본 회전 철학**:
- 손실 거래 빠른 정리 → 즉시 새로운 기회 탐색
- 시장은 항상 새로운 기회 제공: 과거에 매몰되지 말 것
- 3-5% 손실로 멈추고 10-20% 수익 기회 포착이 우월
- 감정적 애착 금지: 차가운 계산으로 자본 효율성 극대화
- "이번 거래 살리기"보다 "다음 거래 성공"에 집중

⚠️ **중요**: entry_price는 반드시 0으로 설정 (보유 중이므로 진입 불필요)

현재 시장체제 '{market_regime['regime']}'에서 {profit_status} 상황에 최적화된 포지션 관리 조언을 JSON 형식으로 제시하세요.
"""
            
            # GPT 호출 (포지션 관리 JSON Schema)
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system", 
                        "content": f"""당신은 OMNI-XRP의 시장체제 분석 기반 포지션 관리 전문 AI입니다.

    현재 시장체제: {market_regime['regime']} (접근법: {market_regime['approach']})
    현재 수익상태: {profit_status}

    핵심 역할:
    1. 시장체제 변화에 따른 포지션 관리 최적화
    2. 체제별 특화된 목표가/손절가 동적 조정
    3. 수익 상황과 체제를 종합한 최선의 매도 타이밍 제시
    4. 새로운 매수 계획 절대 금지

    특별 지침:
    - 하락장으로 전환 시: 수익권이면 방어적 매도 우선 고려
    - 상승장 지속 시: Trailing Stop으로 수익 극대화
    - 횡보장에서: Mean Reversion 완료 시점 포착"""
                    },
                    {"role": "user", "content": management_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "omni_xrp_position_management",  
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "market_analysis": {
                                    "type": "object",
                                    "properties": {
                                        "regime_impact": {"type": "string"},
                                        "trend_group": {"type": "string"},
                                        "momentum_group": {"type": "string"},
                                        "volatility_group": {"type": "string"},
                                        "volume_group": {"type": "string"},
                                        "overall_confidence": {"type": "string"},
                                        "market_condition": {
                                            "type": "string",
                                            "enum": ["강세장", "약세장", "횡보장", "변동성장"]
                                        }
                                    },
                                    "required": ["regime_impact", "trend_group", "momentum_group", "volatility_group", "volume_group", "overall_confidence", "market_condition"],
                                    "additionalProperties": False
                                },
                                "risk_assessment": {
                                    "type": "object", 
                                    "properties": {
                                        "risk_level": {
                                            "type": "string",
                                            "enum": ["낮음", "보통", "높음", "매우높음"]
                                        },
                                        "position_size": {"type": "string"},
                                        "max_holding_time": {"type": "string"},
                                        "key_risks": {"type": "string"}
                                    },
                                    "required": ["risk_level", "position_size", "max_holding_time", "key_risks"],
                                    "additionalProperties": False
                                },
                                "entry_price": {"type": "number"},      
                                "target_price": {"type": "number"},     
                                "stop_loss_price": {"type": "number"},  
                                "entry_reason": {"type": "string"},     
                                "target_reason": {"type": "string"},
                                "stop_loss_reason": {"type": "string"},
                                "sell_strategy": {"type": "string"},
                                "lessons_applied": {"type": "string"},
                                "regime_specific_action": {"type": "string"}
                            },
                            "required": [
                                "market_analysis", "risk_assessment", "entry_price", "target_price", 
                                "stop_loss_price", "entry_reason", "target_reason", "stop_loss_reason", 
                                "sell_strategy", "lessons_applied", "regime_specific_action"
                            ],
                            "additionalProperties": False
                        }
                    }
                },
                max_tokens=1800,
                temperature=0.1
            )
            
            management_advice = json.loads(response.choices[0].message.content)
            logger.info(f"✅ {market_regime['regime']} 체제 기반 포지션 관리 조언 생성 완료")
            return management_advice
            
        except Exception as e:
            logger.error(f"❌ 시장체제 기반 포지션 관리 조언 생성 중 오류: {e}")
            return None

    def _get_position_management_guidance(self, market_regime, current_profit_rate):
        """시장체제별 포지션 관리 특화 가이던스"""
        regime = market_regime['regime']
        approach = market_regime['approach']
        
        guidance_map = {
            "명백한_하락장": f"""
    🚨 **하락장 감지 - 방어적 포지션 관리 우선**
    - 현재 수익률: {current_profit_rate:+.2f}%
    - 우선순위: 수익권이면 즉시 매도, 손실권이면 빠른 손절 검토
    - 목표가 조정: 현재가 근처로 하향 조정 (빠른 탈출)
    - 손절가 조정: 더 타이트하게 설정 (추가 하락 방지)
    - 핵심 원칙: 하락장에서는 욕심내지 말고 자본 보존이 최우선""",

            "횡보_박스권": f"""
    📊 **횡보장 - Mean Reversion 완료 시점 포착**
    - 현재 수익률: {current_profit_rate:+.2f}%
    - 우선순위: 볼린저밴드 중심선 도달 시 매도 고려
    - 목표가 조정: 밴드 상단보다는 중심선을 현실적 목표로
    - 손절가 조정: 밴드 하단 이탈 시 박스권 붕괴로 판단
    - 핵심 원칙: 횡보장에서는 욕심부리지 말고 적당한 선에서 매도""",

            "명백한_상승장": f"""
    🚀 **상승장 지속 - 수익 극대화 전략**
    - 현재 수익률: {current_profit_rate:+.2f}%
    - 우선순위: Trailing Stop으로 상승 추세 최대한 활용
    - 목표가 조정: 상향 조정 고려 (단, 과욕 금지)
    - 손절가 조정: 현재가의 ATR만큼 상향 조정 (Trailing)
    - 핵심 원칙: 상승장에서는 추세를 따라가되 과욕은 금물""",

            "고변동성_혼조장": f"""
    ⚡ **고변동성 - 신중한 수익 확보**
    - 현재 수익률: {current_profit_rate:+.2f}%
    - 우선순위: 변동성이 큰 만큼 적당한 수익에서 매도 검토
    - 목표가 조정: 보수적으로 설정 (변동성 감안)
    - 손절가 조정: ATR 기반으로 여유있게 설정
    - 핵심 원칙: 변동성장에서는 확실한 수익 확보가 우선""",

            "애매한_혼조장": f"""
    🤔 **애매한 상황 - 안전 우선**
    - 현재 수익률: {current_profit_rate:+.2f}%
    - 우선순위: 명확한 방향성 확인까지 현상 유지 또는 보수적 매도
    - 목표가 조정: 현재가 근처로 보수적 조정
    - 손절가 조정: 타이트하게 설정
    - 핵심 원칙: 불확실한 상황에서는 안전이 최우선"""
        }
        
        return guidance_map.get(regime, f"시장체제 '{regime}'에 대한 가이던스를 찾을 수 없습니다.")

    def _generate_new_entry_strategy(self, market_data):
        """궁극의 전략: 시스템 진단 + AI 정교 분석 통합"""
        try:
            # 1단계: OMNI 시스템의 1차 시장 체제 진단
            market_regime = self._analyze_market_regime(market_data)
            btc_info = market_regime.get('btc_analysis', {})
            reliability = market_regime.get('reliability_score', 0)
            logger.info(f"🎯 OMNI 강화 진단: {market_regime['regime']} (신뢰도: {market_regime['confidence']}, 점수: {reliability}/100)")
            if btc_info.get('btc_influence') == "높음":
                btc_change = btc_info.get('btc_1h_change', 0)
                logger.info(f"   🔗 BTC 영향: {btc_info.get('btc_trend', '알수없음')} ({btc_change:+.2f}%), 상관관계: {btc_info.get('correlation', 0):.2f}")
            if market_regime.get('confidence_modifiers'):
                logger.info(f"   ⚠️ 위험요소: {', '.join(market_regime.get('confidence_modifiers', []))}")
            
            # 2단계: 체제별 하드코딩 규칙 적용 (안전장치)
            if market_regime['approach'] == "매매금지" and market_regime['confidence'] == "높음":
                # 명백한 하락장 → AI 판단 없이 즉시 매매 금지
                logger.info("🚫 명백한 하락장 감지 - AI 분석 없이 매매 금지 적용")
                return self._create_no_trade_response(market_regime, "하드코딩 안전 규칙")
            
            # 3단계: AI에게 시스템 진단 결과를 전달하여 정교한 분석 요청
            logger.info(f"🧠 {market_regime['regime']} 상황에서 AI 정교 분석 시작")
            return self._request_ai_analysis_with_regime(market_data, market_regime)
            
        except Exception as e:
            logger.error(f"❌ 궁극 전략 수립 중 오류: {e}")
            return None

    def _request_ai_analysis_with_regime(self, market_data, market_regime):
        """시스템 진단 결과를 AI에게 전달하여 정교한 분석 수행"""
        try:
            # NumPy 타입 변환
            market_data_serializable = convert_numpy_types(market_data)
            
            # ATR 기반 동적 가격 사전 계산
            dynamic_prices = None
            if market_regime['approach'] == "단기매매":
                dynamic_prices = self._calculate_dynamic_prices_with_atr(market_data, "sideways")
            elif market_regime['approach'] == "신중매매":
                dynamic_prices = self._calculate_dynamic_prices_with_atr(market_data, "conservative")
            else:  # 적극매매
                dynamic_prices = self._calculate_dynamic_prices_with_atr(market_data, "aggressive")
            
            # 과거 교훈 및 시장 맥락
            past_trades = self._get_recent_trades_with_lessons(limit=10)
            market_context = self._analyze_current_market_context(market_data)
            learned_lessons = self._extract_learned_lessons()
            entry_prompt = self.load_entry_strategy_prompt()
            
            # 강화된 AI 프롬프트 (시스템 진단 결과 포함)
            enhanced_prompt = f"""
{entry_prompt}


## 🎯 OMNI 시스템의 1차 시장 체제 진단 결과 (최우선 참고사항)

### 📊 시장 체제 분석 결과
- **진단된 시장 체제**: {market_regime['regime']}
- **시스템 권장 접근법**: {market_regime['approach']}
- **진단 신뢰도**: {market_regime['confidence']}
- **체제 점수**: {market_regime.get('regime_score', 0)}/5 (음수=약세, 양수=강세)

### 🔍 세부 진단 근거
- **장기 추세**: {market_regime['long_term_trend']} (일봉 EMA60 기준)
- **단기 추세**: {market_regime['short_term_trend']} (일봉 SMA20 기준)
- **이평선 배열**: {market_regime['ma_alignment']}
- **변동성 상태**: {market_regime['volatility_state']}
- **핵심 신호들**:
  * 골든크로스: {market_regime['key_signals']['golden_cross']}
  * 데스크로스: {market_regime['key_signals']['death_cross']}
  * BB 스퀴즈: {market_regime['key_signals']['bb_squeeze']}
  * 4시간 ATR 비율: {market_regime['key_signals']['atr_ratio_4h']:.2f}%

### 💡 OMNI 시스템의 권고사항
{self._get_regime_specific_guidance(market_regime)}

### 🧮 ATR 기반 동적 가격 제안 (참고용)
{json.dumps(dynamic_prices, indent=2, ensure_ascii=False) if dynamic_prices else "가격 계산 실패"}

### 📊 실시간 시장 데이터
{json.dumps(market_data_serializable, indent=2, ensure_ascii=False)}

### 🧠 시장 맥락 분석
{market_context}

### 📚 과거 거래 성과 (학습 데이터)
{json.dumps(past_trades, indent=2, ensure_ascii=False)}

### 🎓 축적된 핵심 교훈
{learned_lessons}

---

## 🎯 AI 정교 분석 요청사항

위의 **OMNI 시스템 1차 진단 결과**를 **가장 중요한 판단 근거**로 삼아서:

1. **시장 체제 진단 검증**: OMNI 시스템의 '{market_regime['regime']}' 진단이 실시간 A-D 지표들과 일치하는지 재검증
2. **접근법 최적화**: '{market_regime['approach']}' 권고를 바탕으로 하되, 미묘한 시장 신호들을 고려한 미세 조정
3. **동적 가격 활용**: 제공된 ATR 기반 동적 가격들을 참고하되, 현재 시장 상황에 맞게 조정
4. **과거 교훈 통합**: 유사한 시장 체제에서의 과거 성공/실패 패턴을 반영

**특별 지시사항**:
- 만약 시스템 진단이 '매매금지'라면, 매우 강력한 반전 신호가 복수로 확인되지 않는 한 entry_price를 0으로 설정하세요
- '단기매매' 체제라면 Mean Reversion 전략에 집중하고, 볼린저 밴드와 RSI 조합을 우선 고려하세요
- '적극매매' 체제라면 기존 OMNI의 강점인 다중 시간대 추세 추종을 최대한 활용하세요

현재 체제 '{market_regime['regime']}'에 최적화된 거래 전략을 JSON 형식으로 제시하세요.
"""
            
            # GPT 호출
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": f"""당신은 OMNI-XRP의 궁극 진화형 AI입니다.

핵심 역할:
1. OMNI 시스템의 1차 시장체제 진단 결과를 최우선으로 존중
2. 진단된 체제(강세/약세/횡보/혼조)에 특화된 정교한 전략 수립
3. 하드코딩 안전규칙과 AI 미세분석의 완벽한 조화
4. ATR 기반 동적 가격과 과거 교훈의 유기적 결합

현재 진단된 시장체제: {market_regime['regime']}
권장 접근법: {market_regime['approach']}

이 진단을 기반으로 최적의 전략을 수립하세요."""
                    },
                    {"role": "user", "content": enhanced_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "omni_xrp_ultimate_strategy",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "market_analysis": {
                                    "type": "object",
                                    "properties": {
                                        "regime_verification": {"type": "string"},
                                        "trend_group": {"type": "string"},
                                        "momentum_group": {"type": "string"},
                                        "volatility_group": {"type": "string"},
                                        "volume_group": {"type": "string"},
                                        "overall_confidence": {"type": "string"},
                                        "market_condition": {
                                            "type": "string",
                                            "enum": ["강세장", "약세장", "횡보장", "변동성장"]
                                        }
                                    },
                                    "required": ["regime_verification", "trend_group", "momentum_group", "volatility_group", "volume_group", "overall_confidence", "market_condition"],
                                    "additionalProperties": False
                                },
                                "risk_assessment": {
                                    "type": "object",
                                    "properties": {
                                        "risk_level": {
                                            "type": "string",
                                            "enum": ["낮음", "보통", "높음", "매우높음"]
                                        },
                                        "position_size": {"type": "string"},
                                        "max_holding_time": {"type": "string"},
                                        "key_risks": {"type": "string"}
                                    },
                                    "required": ["risk_level", "position_size", "max_holding_time", "key_risks"],
                                    "additionalProperties": False
                                },
                                "entry_price": {"type": "number"},
                                "target_price": {"type": "number"},
                                "stop_loss_price": {"type": "number"},
                                "entry_reason": {"type": "string"},
                                "target_reason": {"type": "string"},
                                "stop_loss_reason": {"type": "string"},
                                "sell_strategy": {"type": "string"},
                                "lessons_applied": {"type": "string"},
                                "regime_adaptation": {"type": "string"}
                            },
                            "required": [
                                "market_analysis", "risk_assessment", "entry_price", "target_price",
                                "stop_loss_price", "entry_reason", "target_reason", "stop_loss_reason",
                                "sell_strategy", "lessons_applied", "regime_adaptation"
                            ],
                            "additionalProperties": False
                        }
                    }
                },
                max_tokens=2500,
                temperature=0.1
            )
            
            ai_strategy = json.loads(response.choices[0].message.content)
            logger.info(f"✅ {market_regime['regime']} 체제 맞춤 AI 전략 생성 완료")
            
            # 최종 안전 검증
            return self._final_safety_check(ai_strategy, market_regime)
            
        except Exception as e:
            logger.error(f"❌ AI 정교 분석 요청 중 오류: {e}")
            return None

    def _final_safety_check(self, ai_strategy, market_regime):
        """AI 전략에 대한 최종 안전성 검증"""
        try:
            # 1. 하락장에서 진입가가 0이 아닌 경우 재검토
            if market_regime['approach'] == "매매금지" and ai_strategy.get('entry_price', 0) > 0:
                logger.warning("🚨 안전 검증: 하락장인데 AI가 매수 전략 제시 - 재검토")
                
                # AI의 판단 근거 확인
                regime_verification = ai_strategy.get('market_analysis', {}).get('regime_verification', '')
                
                if "강력한 반전" not in regime_verification and "복수 신호" not in regime_verification:
                    logger.warning("🛡️ 안전장치 발동: 하락장 매수 차단")
                    ai_strategy['entry_price'] = 0
                    ai_strategy['entry_reason'] = "OMNI 안전장치: 하락장에서 충분한 반전 근거 부족으로 매수 차단"
            
            # 2. 진입가가 현재가와 너무 차이나는 경우 조정
            current_price = market_regime.get('current_price')
            entry_price = ai_strategy.get('entry_price', 0)
            
            if entry_price > 0 and current_price:
                price_diff_pct = abs(entry_price - current_price) / current_price * 100
                if price_diff_pct > 5:  # 5% 이상 차이
                    logger.warning(f"⚠️ 진입가 검증: 현재가 대비 {price_diff_pct:.1f}% 차이 - 조정 고려")
            
            # 3. 목표가/손절가 비율 검증
            target_price = ai_strategy.get('target_price', 0)
            stop_loss = ai_strategy.get('stop_loss_price', 0)
            
            if entry_price > 0 and target_price > 0 and stop_loss > 0:
                reward_ratio = (target_price - entry_price) / (entry_price - stop_loss)
                if reward_ratio < 1.2:  # 수익:손실 비율이 1.2:1 미만
                    logger.warning(f"⚠️ 리스크/보상 비율 검증: {reward_ratio:.2f}:1 - 개선 권장")
            
            logger.info("✅ 최종 안전성 검증 완료")
            return ai_strategy
            
        except Exception as e:
            logger.error(f"❌ 안전성 검증 중 오류: {e}")
            return ai_strategy
    
    def load_strategy_prompt(self, filename="omni_xrp_strategy.txt"):
        """외부 프롬프트 파일 로드"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"⚠️ 프롬프트 파일 {filename}을 찾을 수 없어 기본 프롬프트를 사용합니다.")
            return self._get_default_prompt()

    def load_position_management_prompt(self):
        """포지션 관리 전용 프롬프트 로드"""
        try:
            with open('omni_position_management.txt', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("⚠️ 포지션 관리 프롬프트 파일을 찾을 수 없어 기본값을 사용합니다.")
            return self._get_default_position_prompt()

    def load_entry_strategy_prompt(self):
        """신규 진입 전용 프롬프트 로드"""
        try:
            with open('omni_entry_strategy.txt', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("⚠️ 진입 전략 프롬프트 파일을 찾을 수 없어 기본값을 사용합니다.")
            return self._get_default_entry_prompt()

    def load_stop_analysis_prompt(self):
        """손절 재분석 전용 프롬프트 로드"""
        try:
            with open('omni_stop_analysis.txt', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("⚠️ 손절 분석 프롬프트 파일을 찾을 수 없어 기본값을 사용합니다.")
            return self._get_default_stop_prompt()

    def _get_default_position_prompt(self):
        """포지션 관리 기본 프롬프트"""
        return """
    # OMNI-XRP 포지션 관리 가이드

    ## 수익률별 전략
    - +10% 이상: 손절가 점진적 상향 조정
    - +20% 이상: 일부 매도 고려
    - -5% 이하: 빠른 탈출 검토

    ## 핵심 고려사항
    - 수익권 + 상승 추세 → 손절가 점진적 상향 조정
    - 손실권 + 하락 추세 → 빠른 탈출 우선
    - 목표가 달성률 80% 이상 → 일부 매도 고려
    """

    def _get_default_entry_prompt(self):
        """신규 진입 기본 프롬프트"""
        return """
    # OMNI-XRP 신규 진입 가이드

    ## 시장체제별 접근
    - 상승장: 추세 추종 + 적극적 포지션
    - 횡보장: Mean Reversion + 중간 포지션  
    - 하락장: 매매 금지

    ## XRP 특화 고려사항
    - BTC 상관관계 확인
    - 변동성 수준 체크
    - 뉴스 이벤트 회피
    """

    def _get_default_stop_prompt(self):
        """손절 재분석 기본 프롬프트"""
        return """
    # OMNI-XRP 손절 재분석 가이드

    ## 즉시 매도 조건
    - 하락장 전환 확실
    - BTC 동반 급락
    - 손실률 -8% 이상

    ## 손절가 조정 조건
    - 일시적 조정 판단
    - 상승 추세 유지
    - 지지선 근처 반등
    """


    def _get_default_prompt(self):
        """기본 전략 프롬프트"""
        return """
# OMNI-XRP 전략 프롬프트 v5.0 - 포지션 인식 + 시장체제 분석 완전 통합 시스템

당신은 OMNI-XRP 시스템의 최고 전략 수립 AI입니다. A-D 지표 그룹과 과거 교훈을 완벽히 통합하여 **현재 포지션 상태와 시장체제에 따른** 최적의 XRP 거래 전략을 수립합니다.

## 🎯 핵심 철학: OMNI의 완전한 의미
- **OMNI**: '단일 자산(XRP)에 대한 모든 관점의 데이터를 종합' + '과거 모든 경험의 교훈 통합' + '현재 포지션 상태 완전 인식' + '시장체제별 차별화 전략'
- **A-D 지표 그룹**: 추세(A) + 모멘텀(B) + 변동성(C) + 거래량(D) = 완벽한 현재 분석
- **학습 통합**: 과거 성공 패턴 재활용 + 실패 패턴 완전 회피
- **포지션 인식**: 보유 상태에 따른 차별화된 전략 (매수 vs 보유관리)
- **시장체제 분석**: 강세/약세/횡보/혼조별 전문화된 접근법
- **XRP 특화**: 극변동성 대응 ATR 기반 동적 리스크 관리

모든 결정은 시장체제 진단 → A-D 지표 그룹의 종합적 합의 → 과거 학습 교훈 → 현재 포지션 상태를 통해 신뢰도 높은 전략을 수립하세요.
"""
    
    def _get_recent_trades_with_lessons(self, limit=10):
        """성과와 교훈이 포함된 최근 거래 기록"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT trade_id, status, planned_entry_price, planned_target_price, 
                           actual_entry_price, actual_exit_price, trade_result, net_profit_krw,
                           entry_reason, target_reason, stop_loss_reason
                    FROM trades 
                    WHERE status IN ('COMPLETED', 'ACTIVE')
                    ORDER BY plan_timestamp DESC 
                    LIMIT ?
                ''', (limit,))
                
                rows = cursor.fetchall()
                trades = []
                for row in rows:
                    profit_rate = 0
                    if row[4] and row[5] and row[4] > 0:
                        profit_rate = ((row[5] - row[4]) / row[4] * 100)
                    
                    trades.append({
                        'trade_id': row[0],
                        'status': row[1],
                        'planned_entry': row[2],
                        'planned_target': row[3],
                        'actual_entry': row[4],
                        'actual_exit': row[5],
                        'result': row[6],
                        'profit_krw': row[7],
                        'profit_rate': round(profit_rate, 2) if profit_rate else 0,
                        'entry_strategy': row[8][:100] + "..." if row[8] else "",
                        'success_pattern': "성공" if row[7] and row[7] > 0 else "실패"
                    })
                return trades
        except Exception as e:
            logger.error(f"❌ 과거 거래 조회 중 오류: {e}")
            return []
    
    def _analyze_current_market_context(self, market_data):
        """현재 시장 맥락 종합 분석"""
        try:
            indicators = market_data['technical_indicators']
            current_price = market_data['current_price']
            
            # 다중 시간대 추세 합의도
            trend_consensus = 0
            for tf in ['5m', '15m', '1h', '4h', 'day']:
                if tf in indicators:
                    if indicators[tf]['trend']['trend_strength'] > 0:
                        trend_consensus += 1
                    elif indicators[tf]['trend']['trend_strength'] < 0:
                        trend_consensus -= 1
            
            # 모멘텀/변동성/거래량 상태
            momentum_state = "중립"
            if indicators.get('1h', {}).get('momentum', {}).get('rsi_overbought'):
                momentum_state = "과매수"
            elif indicators.get('1h', {}).get('momentum', {}).get('rsi_oversold'):
                momentum_state = "과매도"
            
            volatility_level = "보통"
            atr_ratio = indicators.get('1h', {}).get('volatility', {}).get('atr_ratio', 0)
            if atr_ratio > 4:
                volatility_level = "매우높음"
            elif atr_ratio > 2:
                volatility_level = "높음"
            elif atr_ratio < 1:
                volatility_level = "낮음"
            
            volume_state = "정상"
            volume_ratio = indicators.get('1h', {}).get('volume', {}).get('volume_ratio', 1)
            if volume_ratio > 2:
                volume_state = "급증"
            elif volume_ratio < 0.5:
                volume_state = "위축"
            
            context = f"""
현재 시장 종합 상황:
- 다중 시간대 추세 합의: {trend_consensus}/5 (양수=상승, 음수=하락)
- 모멘텀 상태: {momentum_state}
- 변동성 수준: {volatility_level} (ATR 비율: {atr_ratio:.2f}%)
- 거래량 상태: {volume_state} (평균 대비 {volume_ratio:.1f}배)
- 현재 가격: {current_price:,.0f}원
- 전반적 시장 성격: {"상승 추세" if trend_consensus > 2 else "하락 추세" if trend_consensus < -2 else "횡보/혼조"}
"""
            return context
            
        except Exception as e:
            logger.error(f"시장 맥락 분석 중 오류: {e}")
            return "시장 맥락 분석 실패"
    
    def _extract_learned_lessons(self):
        """Reflection.md에서 핵심 교훈 추출"""
        try:
            if not os.path.exists('Reflection.md'):
                return "축적된 교훈이 없습니다. 첫 거래를 시작합니다."
            
            with open('Reflection.md', 'r', encoding='utf-8') as f:
                reflection_content = f.read()
            
            lessons = []
            lesson_patterns = [
                r'핵심 교훈[:\s]*([^\n]+)',
                r'교훈[:\s]*([^\n]+)', 
                r'개선점[:\s]*([^\n]+)',
                r'다음 거래[:\s]*([^\n]+)'
            ]
            
            for pattern in lesson_patterns:
                matches = re.findall(pattern, reflection_content, re.IGNORECASE)
                lessons.extend(matches[-3:])
            
            if lessons:
                unique_lessons = list(set(lessons))[:5]
                return "최근 학습한 핵심 교훈들:\n" + "\n".join([f"- {lesson}" for lesson in unique_lessons])
            else:
                return "구체적 교훈 추출 실패. 일반적 신중함으로 접근하세요."
                
        except Exception as e:
            logger.error(f"교훈 추출 중 오류: {e}")
            return "교훈 추출 실패. 보수적 접근하세요."

# =============================================================================
    # 6. ACT - 거래 실행 및 관리
    # =============================================================================
    
    def save_trade_plan(self, trade_plan):
        """개선된 거래 계획 저장: 포지션 상태에 따른 스마트 처리"""
        try:
            if not trade_plan or 'entry_price' not in trade_plan:
                logger.warning("⚠️ 유효한 거래 계획이 아닙니다.")
                return None
            
            # 포지션 상태 재확인
            position_status = self.check_current_position()
            has_position = position_status.get('has_position', False)
            
            if has_position:
                # XRP 보유 중 - 포지션 관리 모드
                return self._update_position_management(trade_plan)
            else:
                # XRP 미보유 - 신규 진입 계획 모드
                return self._create_new_entry_plan(trade_plan)
                
        except Exception as e:
            logger.error(f"❌ 거래 계획 저장 중 오류: {e}")
            return None

    def _update_position_management(self, trade_plan):
        """XRP 보유 중일 때: 기존 ACTIVE 거래의 목표가/손절가 업데이트"""
        try:
            # 진입가 강제 0 설정
            if trade_plan.get('entry_price', 0) != 0:
                logger.warning("🚫 XRP 보유 중인데 진입가가 0이 아님 - 강제 수정")
                trade_plan['entry_price'] = 0
                trade_plan['entry_reason'] = "XRP 보유 중 - 진입 불필요"
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1단계: 현재 ACTIVE 거래 조회
                cursor.execute('''
                    SELECT trade_id, position_size_xrp, actual_entry_price, 
                        entry_timestamp, commission_krw
                    FROM trades 
                    WHERE status = 'ACTIVE'
                    ORDER BY entry_timestamp DESC
                    LIMIT 1
                ''')
                
                active_trade = cursor.fetchone()
                
                if not active_trade:
                    logger.warning("⚠️ XRP 보유 중이지만 ACTIVE 거래가 없습니다. 스킵합니다.")
                    return None
                
                old_trade_id, position_size, entry_price, entry_time, commission = active_trade
                
                # 2단계: 기존 ACTIVE를 SUPERSEDED로 변경
                cursor.execute('''
                    UPDATE trades SET 
                        status = 'SUPERSEDED',
                        target_reason = target_reason || ' [새로운 관리계획으로 대체됨]',
                        stop_loss_reason = stop_loss_reason || ' [새로운 관리계획으로 대체됨]'
                    WHERE trade_id = ?
                ''', (old_trade_id,))
                
                # 3단계: 새로운 ACTIVE 거래 생성 (기존 정보 + 새로운 목표가/손절가)
                plan_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    INSERT INTO trades (
                        asset_ticker, status, plan_timestamp,
                        planned_entry_price, planned_target_price, planned_stop_loss,
                        entry_reason, target_reason, stop_loss_reason,
                        position_size_xrp, entry_timestamp, actual_entry_price, commission_krw
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'XRP', 'ACTIVE', plan_timestamp,
                    0,  # 진입가는 0
                    trade_plan['target_price'], 
                    trade_plan['stop_loss_price'],
                    trade_plan['entry_reason'],
                    f"[관리계획 업데이트] {trade_plan['target_reason']}",
                    f"[관리계획 업데이트] {trade_plan['stop_loss_reason']}",
                    position_size, entry_time, entry_price, commission
                ))
                
                new_trade_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"🔄 포지션 관리 계획 업데이트 완료:")
                logger.info(f"   이전 거래 ID {old_trade_id} → SUPERSEDED")
                logger.info(f"   새로운 거래 ID {new_trade_id} → ACTIVE")
                logger.info(f"   새 목표가: {trade_plan['target_price']:,.0f}원")
                logger.info(f"   새 손절가: {trade_plan['stop_loss_price']:,.0f}원")
                
                return new_trade_id
                
        except Exception as e:
            logger.error(f"❌ 포지션 관리 업데이트 중 오류: {e}")
            return None

    def _create_new_entry_plan(self, trade_plan):
        """XRP 미보유일 때: 기존 모든 계획 정리 후 신규 진입 계획 생성"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1단계: 모든 기존 계획/활성 거래 정리
                cursor.execute('''
                    UPDATE trades 
                    SET status = 'CANCELLED' 
                    WHERE status IN ('PLANNED', 'ACTIVE')
                ''')
                
                cancelled_count = cursor.rowcount
                
                # 2단계: 새로운 진입 계획 저장
                plan_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    INSERT INTO trades (
                        asset_ticker, status, plan_timestamp,
                        planned_entry_price, planned_target_price, planned_stop_loss,
                        entry_reason, target_reason, stop_loss_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'XRP', 'PLANNED', plan_timestamp,
                    trade_plan['entry_price'],
                    trade_plan['target_price'], 
                    trade_plan['stop_loss_price'],
                    trade_plan['entry_reason'],
                    trade_plan['target_reason'],
                    trade_plan['stop_loss_reason']
                ))
                
                new_trade_id = cursor.lastrowid
                conn.commit()
                
                if cancelled_count > 0:
                    logger.info(f"🗑️ 기존 계획 {cancelled_count}개 정리 완료")
                logger.info(f"📝 새로운 진입 계획 저장 완료 (ID: {new_trade_id})")
                logger.info(f"   진입가: {trade_plan['entry_price']:,.0f}원")
                logger.info(f"   목표가: {trade_plan['target_price']:,.0f}원")
                
                return new_trade_id
                
        except Exception as e:
            logger.error(f"❌ 신규 진입 계획 생성 중 오류: {e}")
            return None

    def monitor_planned_trades(self):
        """개선된 계획 거래 모니터링: 현재 활성 계획만 처리"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 현재 활성 계획만 조회 (가장 최근 PLANNED 거래)
                cursor.execute('''
                    SELECT trade_id, planned_entry_price
                    FROM trades 
                    WHERE status = 'PLANNED'
                    ORDER BY plan_timestamp DESC
                    LIMIT 1
                ''')
                
                current_plan = cursor.fetchone()
            
            if not current_plan:
                return
            
            trade_id, planned_entry_price = current_plan
            
            # 현재 가격 확인
            orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 진입 조건 확인 (±0.5% 범위)
            if planned_entry_price == 0:
                # 진입가가 0이면 매수하지 않음 (XRP 보유 중)
                return
            entry_range = planned_entry_price * 0.005
            if abs(current_price - planned_entry_price) <= entry_range:
                logger.info(f"🎯 현재 활성 계획 #{trade_id} 진입 조건 만족 - 매수 실행")
                success = self._execute_buy_order(trade_id, current_price)
                if success:
                    self.current_active_plan_id = None  # 계획 실행 완료
                    logger.info(f"✅ 거래 #{trade_id} 매수 완료 - PLANNED → ACTIVE")
                else:
                    logger.warning(f"⚠️ 거래 #{trade_id} 매수 실패")
                        
        except Exception as e:
            logger.error(f"❌ 개선된 계획 거래 모니터링 중 오류: {e}")
    
    def _calculate_dynamic_position_size(self, krw_balance, market_regime):
        """비트코인 분석 반영한 시장 체제 기반 동적 투자 비중 결정"""
        try:
            regime = market_regime.get('regime', '분석실패')
            confidence = market_regime.get('confidence', '없음')
            reliability_score = market_regime.get('reliability_score', 50)
            confidence_modifiers = market_regime.get('confidence_modifiers', [])
            
            # 1. 기본 투자 비중 결정
            if regime == "명백한_상승장" and confidence == "높음":
                base_risk_pct = 0.95  # 적극적 매매
                risk_level = "적극적"
            elif regime == "명백한_상승장":
                base_risk_pct = 0.80  # 신뢰도가 낮은 상승장
                risk_level = "중간-적극"
            elif regime == "횡보_박스권":
                base_risk_pct = 0.60  # 중립적 매매 (Mean Reversion)
                risk_level = "중립적"
            elif regime == "고변동성_혼조장":
                base_risk_pct = 0.40  # 보수적 매매
                risk_level = "보수적"
            elif regime == "애매한_혼조장":
                base_risk_pct = 0.30  # 매우 보수적
                risk_level = "매우보수적"
            else:  # "명백한_하락장" 또는 "분석실패"
                base_risk_pct = 0.0   # 매매 금지
                risk_level = "매매금지"
            
            # 2. 비트코인 분석 기반 조정
            btc_adjustment = 1.0
            btc_analysis = market_regime.get('btc_analysis', {})
            
            if btc_analysis.get('btc_influence') == "높음":
                btc_1h_change = btc_analysis.get('btc_1h_change', 0)
                
                # 비트코인 강하락 시 투자 비중 대폭 감소
                if btc_1h_change < -3:
                    btc_adjustment = 0.3  # 70% 감소
                    risk_level += "+BTC급락위험"
                elif btc_1h_change < -1.5:
                    btc_adjustment = 0.7  # 30% 감소
                    risk_level += "+BTC하락주의"
                # 비트코인 강상승 시 투자 비중 소폭 증가
                elif btc_1h_change > 2:
                    btc_adjustment = 1.2  # 20% 증가 (과욕 방지)
                    risk_level += "+BTC상승지원"
            
            # 3. 신뢰도 점수 기반 추가 조정
            reliability_adjustment = 1.0
            if reliability_score < 60:
                reliability_adjustment = 0.6  # 신뢰도 낮으면 40% 감소
                risk_level += "+신뢰도낮음"
            elif reliability_score > 80:
                reliability_adjustment = 1.1  # 신뢰도 높으면 10% 증가
                risk_level += "+신뢰도높음"
            
            # 4. 위험 수정자 기반 조정
            modifier_adjustment = 1.0
            if "BTC강하락위험" in confidence_modifiers:
                modifier_adjustment *= 0.5  # 50% 감소
                risk_level += "+BTC리스크"
            if "구조변화위험" in confidence_modifiers:
                modifier_adjustment *= 0.7  # 30% 감소
                risk_level += "+구조리스크"
            if "BTC추세불일치" in confidence_modifiers:
                modifier_adjustment *= 0.8  # 20% 감소
                risk_level += "+추세불일치"
            
            # 5. 최종 투자 비중 계산
            final_risk_pct = base_risk_pct * btc_adjustment * reliability_adjustment * modifier_adjustment
            
            # 6. 안전 한계 적용
            final_risk_pct = max(0.0, min(0.95, final_risk_pct))  # 0~95% 범위 제한
            
            # 추가 안전 조건 확인
            regime_score = market_regime.get('regime_score', 0)
            if regime_score <= -2:  # 강한 하락 신호
                final_risk_pct = min(final_risk_pct, 0.20)  # 최대 20%로 제한
                risk_level += "+강하락제한"
            
            invest_amount = krw_balance * final_risk_pct
            
            logger.info(f"💰 강화된 동적 포지션 사이징:")
            logger.info(f"   체제={regime}, 기본비중={base_risk_pct:.0%}")
            logger.info(f"   BTC조정={btc_adjustment:.2f}, 신뢰도조정={reliability_adjustment:.2f}")
            logger.info(f"   최종비중={final_risk_pct:.0%}, 투자금={invest_amount:,.0f}원")
            logger.info(f"   리스크레벨={risk_level}")
            
            return {
                'invest_amount': invest_amount,
                'risk_percentage': final_risk_pct,
                'base_risk_percentage': base_risk_pct,
                'btc_adjustment': btc_adjustment,
                'reliability_adjustment': reliability_adjustment,
                'modifier_adjustment': modifier_adjustment,
                'risk_level': risk_level,
                'regime': regime,
                'reliability_score': reliability_score
            }
            
        except Exception as e:
            logger.error(f"❌ 강화된 동적 포지션 사이징 계산 중 오류: {e}")
            return {
                'invest_amount': krw_balance * 0.20,  # 안전한 기본값
                'risk_percentage': 0.20,
                'risk_level': "오류발생-안전모드",
                'regime': "계산실패"
            }

    def _determine_entry_strategy(self, target_entry_price, current_ask, current_bid):
        """진입 전략 결정 (즉시/지정가/취소)"""
        try:
            price_tolerance = 0.003  # 0.3% 허용 오차
            
            # 목표 진입가와 현재 매도호가 비교
            price_diff_pct = abs(target_entry_price - current_ask) / current_ask
            
            if target_entry_price >= current_ask * (1 - price_tolerance):
                # 목표가가 현재 매도호가보다 높거나 비슷 → 즉시 체결 가능
                return {
                    'action': 'IMMEDIATE',
                    'price': current_ask,
                    'reason': f'목표가({target_entry_price:,.0f}) >= 현재매도호가({current_ask:,.0f}) - 즉시 체결'
                }
            elif target_entry_price >= current_bid and target_entry_price < current_ask:
                # 목표가가 매수호가와 매도호가 사이 → 지정가 주문
                return {
                    'action': 'LIMIT_ORDER',
                    'price': target_entry_price,
                    'reason': f'호가 범위 내 목표가 - 지정가 주문 등록'
                }
            elif target_entry_price < current_bid * (1 - price_tolerance):
                # 목표가가 현재 매수호가보다 훨씬 낮음 → 지정가 주문 (대기)
                return {
                    'action': 'LIMIT_ORDER',
                    'price': target_entry_price,
                    'reason': f'목표가가 현재가보다 낮음 - 하락 대기'
                }
            else:
                # 목표가가 너무 높음 → 계획 취소
                return {
                    'action': 'CANCEL',
                    'price': 0,
                    'reason': f'목표가({target_entry_price:,.0f})가 현재가({current_ask:,.0f})보다 과도하게 높음'
                }
                
        except Exception as e:
            logger.error(f"진입 전략 결정 중 오류: {e}")
            return {'action': 'CANCEL', 'price': 0, 'reason': '전략 결정 실패'}

    def _execute_immediate_buy(self, trade_id, invest_amount, entry_strategy):
        """즉시 매수 실행 (시장가)"""
        try:
            logger.info(f"🚀 즉시 매수 실행: {invest_amount:,.0f}원")
            
            # 시장가 매수 주문
            order_result = self.upbit.buy_market_order("KRW-XRP", invest_amount)
            
            if not order_result or 'uuid' not in order_result:
                logger.error("❌ 시장가 매수 주문 실패")
                return False
            
            # 주문 완료 대기
            time.sleep(3)
            
            # 실제 체결 정보 가져오기
            return self._process_buy_order_result(trade_id, order_result['uuid'], invest_amount)
            
        except Exception as e:
            logger.error(f"❌ 즉시 매수 실행 중 오류: {e}")
            return False

    def _execute_limit_buy_with_monitoring(self, trade_id, invest_amount, entry_strategy):
        """지정가 매수 주문 등록 및 모니터링"""
        try:
            target_price = entry_strategy['price']
            target_quantity = invest_amount / target_price
            
            logger.info(f"📊 지정가 매수 주문: {target_price:,.0f}원 × {target_quantity:.4f} XRP")
            
            # 지정가 매수 주문
            order_result = self.upbit.buy_limit_order("KRW-XRP", target_price, target_quantity)
            
            if not order_result or 'uuid' not in order_result:
                logger.error("❌ 지정가 매수 주문 실패")
                return False
            
            order_uuid = order_result['uuid']
            logger.info(f"✅ 지정가 주문 등록 완료 (UUID: {order_uuid})")
            
            # 주문 상태 모니터링 (최대 5분)
            return self._monitor_limit_order(trade_id, order_uuid, invest_amount, 300)
            
        except Exception as e:
            logger.error(f"❌ 지정가 매수 주문 중 오류: {e}")
            return False

    def _monitor_limit_order(self, trade_id, order_uuid, invest_amount, timeout_seconds):
        """지정가 주문 모니터링"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                # 주문 상태 확인
                order_info = self.upbit.get_order(order_uuid)
                
                if not order_info:
                    logger.warning("⚠️ 주문 정보 조회 실패")
                    time.sleep(10)
                    continue
                
                state = order_info.get('state', '')
                
                if state == 'done':
                    # 주문 완료
                    logger.info("✅ 지정가 주문 체결 완료!")
                    return self._process_buy_order_result(trade_id, order_uuid, invest_amount)
                    
                elif state == 'cancel':
                    # 주문 취소됨
                    logger.warning("⚠️ 지정가 주문이 취소되었습니다")
                    return False
                    
                elif state in ['wait', 'watch']:
                    # 대기 중
                    executed_volume = float(order_info.get('executed_volume', 0))
                    trades_count = int(order_info.get('trades_count', 0))
                    
                    if trades_count > 0:
                        logger.info(f"📈 부분 체결 진행 중: {executed_volume:.4f} XRP")
                    
                    time.sleep(10)  # 10초마다 체크
                    continue
                    
                else:
                    logger.warning(f"⚠️ 알 수 없는 주문 상태: {state}")
                    time.sleep(10)
                    continue
            
            # 타임아웃 - 주문 취소
            logger.warning(f"⏰ 지정가 주문 타임아웃 ({timeout_seconds}초) - 주문 취소 시도")
            
            try:
                cancel_result = self.upbit.cancel_order(order_uuid)
                if cancel_result:
                    logger.info("✅ 지정가 주문 취소 완료")
                else:
                    logger.warning("⚠️ 주문 취소 실패 - 수동 확인 필요")
            except Exception as e:
                logger.error(f"❌ 주문 취소 중 오류: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 지정가 주문 모니터링 중 오류: {e}")
            return False

    def _process_buy_order_result(self, trade_id, order_uuid, original_invest_amount):
        """매수 주문 결과 처리 (정확한 수익률 계산용)"""
        try:
            # 주문 상세 정보 가져오기
            order_details = self.upbit.get_order(order_uuid)
            
            if not order_details:
                logger.error("❌ 주문 상세 정보 조회 실패")
                return False
            
            # 실제 체결 정보 추출
            executed_volume = float(order_details.get('executed_volume', 0))
            paid_fee = float(order_details.get('paid_fee', 0))
            
            if executed_volume <= 0:
                logger.error("❌ 체결된 물량이 없습니다")
                return False
            
            # 실제 체결 단가 계산
            total_paid = 0
            trades = order_details.get('trades', [])
            
            if trades:
                # 개별 체결 내역에서 정확한 평균 단가 계산
                total_paid = sum(float(trade['price']) * float(trade['volume']) for trade in trades)
                actual_entry_price = total_paid / executed_volume
            else:
                # trades 정보가 없으면 대략적 계산
                total_paid = float(order_details.get('price', 0)) * executed_volume
                actual_entry_price = float(order_details.get('price', 0))
            
            # 실제 수수료 반영 총 투자금액
            total_cost = total_paid + paid_fee
            
            # 데이터베이스 업데이트
            entry_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE trades SET 
                        status = 'ACTIVE',
                        position_size_xrp = ?,
                        entry_timestamp = ?,
                        actual_entry_price = ?,
                        commission_krw = ?,
                        entry_reason = COALESCE(entry_reason, '') || ' [실제체결: ' || ? || '원]'
                    WHERE trade_id = ?
                ''', (executed_volume, entry_timestamp, actual_entry_price, paid_fee, 
                    round(actual_entry_price), trade_id))
                conn.commit()
            
            logger.info(f"✅ 정확한 매수 완료:")
            logger.info(f"   체결량: {executed_volume:.4f} XRP")
            logger.info(f"   실제 평단가: {actual_entry_price:,.0f}원")
            logger.info(f"   총 비용: {total_cost:,.0f}원 (수수료: {paid_fee:,.0f}원)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 매수 주문 결과 처리 중 오류: {e}")
            return False

    def _execute_buy_order(self, trade_id, target_entry_price):
            """개선된 매수 주문 실행 (지정가 우선 + 정확한 수익률 계산)"""
            try:
                logger.info(f"🎯 개선된 매수 주문 시작 - 목표가: {target_entry_price:,.0f}원")
                
                # 1. 실행 직전 시장 체제 재분석 (최종 안전 확인)
                market_data = self.observe_market_data()
                if not market_data:
                    logger.error("❌ 실행 직전 시장 데이터 수집 실패. 주문 취소.")
                    return False
                
                market_regime = self._analyze_market_regime(market_data)
                logger.info(f"🔍 매수 직전 체제 재확인: {market_regime['regime']} (접근법: {market_regime['approach']})")
                
                # 2. 최종 안전 검증 - 하락장으로 급변한 경우 매수 취소
                if market_regime['approach'] == "매매금지":
                    logger.warning("🚨 매수 직전 하락장 감지 - 안전을 위해 매수 취소")
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE trades SET 
                                status = 'CANCELLED',
                                entry_reason = COALESCE(entry_reason, '') || ' [매수직전 하락장감지로 취소]'
                            WHERE trade_id = ?
                        ''', (trade_id,))
                        conn.commit()
                    return False
                
                # 3. 동적 포지션 사이징 적용
                krw_balance = self.upbit.get_balance("KRW")
                position_info = self._calculate_dynamic_position_size(krw_balance, market_regime)
                invest_amount = position_info['invest_amount']
                
                # 4. 최소 주문 금액 검증
                if invest_amount < 10000:
                    logger.warning(f"⚠️ 동적 투자 금액({invest_amount:,.0f}원)이 최소 주문 금액 미만. 계획 취소.")
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE trades SET 
                                status = 'CANCELLED',
                                entry_reason = COALESCE(entry_reason, '') || ' [투자금액부족으로 취소]'
                            WHERE trade_id = ?
                        ''', (trade_id,))
                        conn.commit()
                    return False
                
                # 5. 현재 시장 상황 확인
                orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
                current_ask = float(orderbook['orderbook_units'][0]['ask_price'])  # 매도호가
                current_bid = float(orderbook['orderbook_units'][0]['bid_price'])  # 매수호가
                
                logger.info(f"📊 현재 호가: 매도 {current_ask:,.0f}원, 매수 {current_bid:,.0f}원")
                
                # 6. 진입 전략 결정
                entry_strategy = self._determine_entry_strategy(target_entry_price, current_ask, current_bid)
                
                logger.info(f"🎯 {position_info['risk_level']} 매수 전략: {entry_strategy['action']}")
                logger.info(f"   투자금: {invest_amount:,.0f}원 ({position_info['risk_percentage']:.0%})")
                logger.info(f"   사유: {entry_strategy['reason']}")
                
                # 7. 전략에 따른 주문 실행
                if entry_strategy['action'] == 'IMMEDIATE':
                    # 즉시 체결 (시장가)
                    success = self._execute_immediate_buy(trade_id, invest_amount, entry_strategy)
                elif entry_strategy['action'] == 'LIMIT_ORDER':
                    # 지정가 주문
                    success = self._execute_limit_buy_with_monitoring(trade_id, invest_amount, entry_strategy)
                else:  # 'CANCEL'
                    # 주문 취소
                    logger.info(f"🚫 매수 조건 불만족으로 주문 취소: {entry_strategy['reason']}")
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE trades SET 
                                status = 'CANCELLED',
                                entry_reason = COALESCE(entry_reason, '') || ' [' || ? || ']'
                            WHERE trade_id = ?
                        ''', (entry_strategy['reason'], trade_id))
                        conn.commit()
                    return False
                
                if success:
                    logger.info(f"✅ 개선된 매수 완료! (거래 ID: {trade_id})")
                    return True
                else:
                    logger.error(f"❌ 매수 실패 (거래 ID: {trade_id})")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ 개선된 매수 주문 실행 중 오류: {e}")
                return False

    def monitor_active_trades(self):
            """활성 거래 모니터링 - 손절 재분석 완전 제거"""
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # 최신 ACTIVE 거래 하나만 조회
                    cursor.execute('''
                        SELECT trade_id, planned_target_price, planned_stop_loss, 
                            position_size_xrp, actual_entry_price
                        FROM trades 
                        WHERE status = 'ACTIVE'
                        ORDER BY entry_timestamp DESC
                        LIMIT 1
                    ''')
                    
                    active_trade = cursor.fetchone()
                
                if not active_trade:
                    return
                
                # 현재 가격 확인
                orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
                current_price = float(orderbook['orderbook_units'][0]['ask_price'])
                
                trade_id, target_price, stop_loss, position_size, entry_price = active_trade
                
                # 🎯 목표가 도달 - 즉시 매도
                if current_price >= target_price:
                    logger.info(f"🎯 거래 ID {trade_id} 목표가 도달 - 매도 실행")
                    self._execute_sell_order(trade_id, current_price, "PROFIT_TAKE")
                    return
                
                # 🛑 손절가 도달 - 즉시 매도 (재분석 없음)
                if current_price <= stop_loss:
                    logger.info(f"🛑 거래 ID {trade_id} 손절가 도달 - 즉시 매도 실행")
                    self._execute_sell_order(trade_id, current_price, "STOP_LOSS")
                    return
                        
            except Exception as e:
                logger.error(f"❌ 활성 거래 모니터링 중 오류: {e}")

    def _execute_sell_order(self, trade_id, current_price, trade_result):
        """매도 주문 실행 - 스케줄링 로직 단순화"""
        try:
            logger.info(f"🎯 매도 주문 실행 중... (가격: {current_price:,.0f}원, 유형: {trade_result})")
            
            xrp_balance = self.upbit.get_balance("XRP")
            
            if xrp_balance < 0.0001:
                logger.warning("⚠️ 매도할 XRP가 부족합니다.")
                return False
            
            # 시장가 매도 주문 실행
            order_result = self.upbit.sell_market_order("KRW-XRP", xrp_balance)
            
            if not order_result or 'uuid' not in order_result:
                logger.error("❌ 매도 주문 실패")
                return False
            
            # 주문 완료 대기
            time.sleep(3)
            
            # 실제 매도 체결 정보 가져오기 및 DB 업데이트
            order_details = self.upbit.get_order(order_result['uuid'])
            
            if not order_details:
                logger.error("❌ 매도 주문 상세 정보 조회 실패")
                return False
                
            # 실제 매도 정보 추출
            executed_volume = float(order_details.get('executed_volume', 0))
            paid_fee = float(order_details.get('paid_fee', 0))
            
            # 실제 매도 단가 계산
            total_received = 0
            trades = order_details.get('trades', [])
            
            if trades:
                total_received = sum(float(trade['price']) * float(trade['volume']) for trade in trades)
                actual_exit_price = total_received / executed_volume
            else:
                total_received = float(order_details.get('price', 0)) * executed_volume
                actual_exit_price = float(order_details.get('price', 0))
            
            net_received = total_received - paid_fee
            exit_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 기존 거래 정보 조회 및 수익률 계산
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT position_size_xrp, actual_entry_price, commission_krw
                    FROM trades WHERE trade_id = ?
                ''', (trade_id,))
                
                row = cursor.fetchone()
                if not row:
                    logger.error("❌ 기존 거래 정보를 찾을 수 없습니다")
                    return False
                
                original_position, entry_price, buy_commission = row
                
                # 정확한 수익률 계산
                total_buy_cost = (entry_price * original_position) + buy_commission
                total_sell_received = net_received
                net_profit = total_sell_received - total_buy_cost
                profit_rate = (net_profit / total_buy_cost * 100) if total_buy_cost > 0 else 0
                total_commission = buy_commission + paid_fee
                
                # 데이터베이스 업데이트
                cursor.execute('''
                    UPDATE trades SET 
                        status = 'COMPLETED',
                        exit_timestamp = ?,
                        actual_exit_price = ?,
                        trade_result = ?,
                        commission_krw = ?,
                        net_profit_krw = ?,
                        profit_rate_pct = ?
                    WHERE trade_id = ?
                ''', (exit_timestamp, actual_exit_price, trade_result, 
                    total_commission, net_profit, profit_rate, trade_id))
                
                conn.commit()
            
            profit_emoji = "💰" if net_profit > 0 else "💸"
            logger.info(f"✅ {profit_emoji} 정확한 매도 완료:")
            logger.info(f"   실제 매도가: {actual_exit_price:,.0f}원")
            logger.info(f"   순수익: {net_profit:+,.0f}원 ({profit_rate:+.2f}%)")
            logger.info(f"   총 수수료: {total_commission:,.0f}원")
            
            # 거래 완료 즉시 회고 실행
            logger.info("📊 거래 완료 - 즉시 회고 분석 시작")
            self.reflect_single_trade(trade_id)

            # 매도 완료 후 단순화된 스케줄링: 1회성 즉시 분석만 예약
            logger.info("🚀 매도 완료 - 10초 후 즉시 새로운 매수 기회 분석 예약")
            schedule.every(10).seconds.do(self.run_strategy_analysis).tag('immediate_analysis')
            
            # 주기 재평가 쿨다운 리셋 (5분마다 실행되는 정규 재평가가 자동으로 최적화)
            self.last_regime_check = None
            logger.info("✅ 주기 재평가 쿨다운 리셋 - 정규 재평가가 자동으로 최적화 진행")

            return True
                    
        except Exception as e:
            logger.error(f"❌ 매도 주문 실행 중 오류: {e}")
            return False

    def _check_immediate_buy_opportunity(self, trade_id):
        """새로운 계획 저장 직후 즉시 매수 조건 체크"""
        try:
            logger.info(f"🔍 신규 계획 ID {trade_id} 즉시 매수 조건 체크")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT planned_entry_price
                    FROM trades 
                    WHERE trade_id = ? AND status = 'PLANNED'
                ''', (trade_id,))
                
                result = cursor.fetchone()
            
            if not result:
                logger.info("💡 즉시 매수 조건 체크 대상 계획 없음")
                return
            
            planned_entry_price = result[0]
            
            # 진입가가 0이면 매수 금지 상태
            if planned_entry_price == 0:
                logger.info("🚫 진입가 0 - 매수 금지 상태")
                return
            
            # 현재 가격 확인
            orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 즉시 매수 조건 확인 (±1% 범위로 더 넓게)
            entry_range = planned_entry_price * 0.01  # 1% 범위
            price_diff = abs(current_price - planned_entry_price)
            
            if price_diff <= entry_range:
                logger.info(f"🎯 즉시 매수 조건 만족! (계획: {planned_entry_price:,.0f}원, 현재: {current_price:,.0f}원)")
                logger.info(f"   가격 차이: {price_diff:,.0f}원 (허용 범위: {entry_range:,.0f}원)")
                
                # 매수 실행
                success = self._execute_buy_order(trade_id, planned_entry_price)
                if success:
                    logger.info(f"✅ 매도 완료 후 즉시 매수 성공! (거래 ID: {trade_id})")
                else:
                    logger.warning(f"⚠️ 매도 완료 후 즉시 매수 실패 (거래 ID: {trade_id})")
            else:
                logger.info(f"⏳ 즉시 매수 조건 미달성 (차이: {price_diff:,.0f}원 > 허용: {entry_range:,.0f}원)")
                logger.info(f"   정기 모니터링에서 재확인 예정")
                
        except Exception as e:
            logger.error(f"❌ 즉시 매수 조건 체크 중 오류: {e}")

    def get_dynamic_analysis_interval(self, position_status, market_regime):
        """(개선안) 포지션 상태와 시장체제에 따른 동적 분석 주기 결정"""
        try:
            has_position = position_status.get('has_position', False)
            regime = market_regime.get('regime', '분석실패')
            confidence = market_regime.get('confidence', '낮음')
            
            if has_position:
                # XRP 보유 중일 때도 시장 상황에 따라 주기 차등화
                if regime == "명백한_상승장":
                    return 10, "포지션 관리: 강세장 추세 추종 (10분 주기)"
                elif regime == "횡보_박스권":
                    return 15, "포지션 관리: 횡보장 모니터링 (15분 주기)"
                elif regime == "명백한_하락장":
                    return 20, "포지션 관리: 하락장 방어 모드 (20분 주기)"
                else:  # 혼조장
                    return 30, "포지션 관리: 보수적 방어 모드 (30분 주기)"
            
            else:
                # XRP 미보유 - 시장체제별 차별화 (기존 로직 유지)
                if regime == "명백한_하락장":
                    return 60, "하락장 대기 모드 (1시간 주기)"
                    
                elif regime == "명백한_상승장" and confidence == "높음":
                    return 5, "강세장 기회 포착 모드 (5분 주기)"
                    
                elif regime == "횡보_박스권":
                    return 7, "횡보장 진입점 포착 모드 (7분 주기)"
                    
                elif regime in ["고변동성_혼조장", "애매한_혼조장"]:
                    return 12, "혼조장 신중 관찰 모드 (12분 주기)"
                    
                elif regime == "명백한_상승장" and confidence != "높음":
                    return 8, "약한 상승장 모니터링 (8분 주기)"
                    
                else:
                    return 30, "일반 분석 모드 (30분 주기)"
                    
        except Exception as e:
            logger.error(f"❌ 동적 주기 계산 중 오류: {e}")
            return 30, "오류 발생 - 기본 모드 (30분 주기)"

    def update_analysis_schedule(self, new_interval, mode_description):
        """분석 주기 동적 업데이트"""
        try:
            # 현재 주기와 다를 때만 업데이트
            if new_interval != self.current_analysis_interval:
                
                # 기존 스케줄 취소 (있다면)
                cleared_count = len(schedule.clear('strategy_analysis'))
                if cleared_count > 0:
                    logger.info(f"🗑️ 기존 전략 분석 스케줄 {cleared_count}개 취소")
                
                # 새로운 주기로 스케줄 등록
                schedule.every(new_interval).minutes.do(self.run_strategy_analysis).tag('strategy_analysis')
                
                # 상태 업데이트
                old_interval = self.current_analysis_interval
                self.current_analysis_interval = new_interval
                self.last_interval_change = time.time()
                
                next_run = datetime.now() + timedelta(minutes=new_interval)
                logger.info(f"📅 분석 주기 변경: {old_interval}분 → {new_interval}분")
                logger.info(f"🎯 모드: {mode_description}")
                logger.info(f"⏰ 다음 분석: {next_run.strftime('%H:%M:%S')}")
                
                return True
            else:
                # 주기 변경 없음
                return False
                
        except Exception as e:
            logger.error(f"❌ 분석 주기 업데이트 중 오류: {e}")
            return False

    def check_and_update_analysis_interval(self):
        """주기적으로 분석 주기 재평가 (5분마다 실행)"""
        try:
            current_time = time.time()
            
            # 쿨다운 체크 (너무 자주 변경 방지)
            if (self.last_regime_check and 
                current_time - self.last_regime_check < self.regime_change_cooldown):
                return
            
            # 현재 시장 상황 확인
            market_data = self.observe_market_data()
            if not market_data:
                logger.warning("⚠️ 주기 재평가용 시장 데이터 수집 실패")
                return
                
            position_status = market_data.get('position_status', {})
            market_regime = self._analyze_market_regime(market_data)
            
            # 새로운 분석 주기 계산
            new_interval, mode_description = self.get_dynamic_analysis_interval(
                position_status, market_regime
            )
            
            # 주기 업데이트 시도
            updated = self.update_analysis_schedule(new_interval, mode_description)
            
            if updated:
                self.last_regime_check = current_time
                logger.info(f"✅ 시장체제 '{market_regime['regime']}' 감지로 분석 주기 조정 완료")
            else:
                # 변경 없어도 체제 확인 시간은 업데이트
                self.last_regime_check = current_time
            
        except Exception as e:
            logger.error(f"❌ 분석 주기 재평가 중 오류: {e}")

    def _detect_price_spike(self, current_price):
        """급등/급락 감지 - 5분 전 가격과 비교"""
        try:
            # 5분봉 데이터에서 5분 전 가격 가져오기
            df_5m = pyupbit.get_ohlcv("KRW-XRP", interval="minute5", count=2)
            if len(df_5m) < 2:
                return False, 0, ""
            
            # 5분 전 종가와 현재 가격 비교
            price_5min_ago = float(df_5m['close'].iloc[-2])  # 5분 전 종가
            price_change_pct = (current_price - price_5min_ago) / price_5min_ago
            
            # 1.5% 이상 급변동 감지
            if abs(price_change_pct) >= self.price_alert_threshold:
                spike_type = "급등" if price_change_pct > 0 else "급락"
                logger.warning(f"🚨 {spike_type} 감지: {price_change_pct:+.2f}% (5분전: {price_5min_ago:,.0f}원 → 현재: {current_price:,.0f}원)")
                
                return True, price_change_pct, spike_type
            
            return False, price_change_pct, ""
            
        except Exception as e:
            logger.error(f"급변동 감지 중 오류: {e}")
            return False, 0, ""

    def _is_emergency_cooldown_active(self):
        """긴급 분석 쿨다운 체크"""
        try:
            if self.last_emergency_time is None:
                return False
            
            time_since_last = time.time() - self.last_emergency_time
            return time_since_last < self.emergency_cooldown
            
        except Exception as e:
            logger.error(f"쿨다운 체크 중 오류: {e}")
            return True  # 오류 시 안전하게 쿨다운 적용

    def monitor_price_with_spike_detection(self):
        """가격 감시 + 급변동 감지"""
        try:
            # 현재 가격 확인
            orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 급변동 감지
            is_spike, change_pct, spike_type = self._detect_price_spike(current_price)
            
            if is_spike and not self._is_emergency_cooldown_active():
                # 🚨 급변동 발생 - 즉시 분석 실행
                logger.info(f"🔥 {spike_type} 트리거 발동 ({change_pct:+.2f}%) - 즉시 전략 재분석 시작")
                self._emergency_strategy_analysis(current_price, change_pct, spike_type)
                self.last_emergency_time = time.time()  # 쿨다운 시작
            elif is_spike and self._is_emergency_cooldown_active():
                logger.info(f"⏰ {spike_type} 감지되었으나 쿨다운 중 - 무시")
            
            # 기존 모니터링 계속
            self.monitor_active_trades()
            self.monitor_planned_trades()
            
        except Exception as e:
            logger.error(f"❌ 급변동 감지 가격 감시 중 오류: {e}")

    def _emergency_strategy_analysis(self, current_price, change_pct, spike_type):
        """🚨 긴급 전략 재분석 - 스케줄링 충돌 방지"""
        try:
            logger.info("🚨 긴급 시장 상황 재분석 시작")
            
            # 시장 데이터 즉시 수집
            market_data = self.observe_market_data()
            if not market_data:
                logger.error("❌ 긴급 시장 데이터 수집 실패")
                return
            
            # 포지션 상태 확인
            position_status = market_data.get('position_status', {})
            has_position = position_status.get('has_position', False)
            
            if has_position:
                # XRP 보유 중 - 긴급 포지션 관리
                logger.info(f"🎯 XRP 보유 중 - {spike_type} 긴급 포지션 재평가")
                emergency_advice = self._generate_emergency_position_advice(market_data, change_pct, spike_type)
                
                if emergency_advice:
                    logger.info("🔄 긴급 상황 - 관리 계획 업데이트")
                    trade_id = self.save_trade_plan(emergency_advice)
                    
                    if trade_id:
                        logger.info(f"✅ 긴급 관리 계획 업데이트 완료 (새 거래 ID: {trade_id})")
                    else:
                        logger.warning("⚠️ 긴급 관리 계획 업데이트 실패")
                        
            else:
                # XRP 미보유 - 긴급 진입 기회 검토
                logger.info(f"💰 XRP 미보유 - {spike_type} 긴급 진입 기회 검토")
                emergency_strategy = self._generate_emergency_entry_strategy(market_data, change_pct, spike_type)
                
                if emergency_strategy:
                    logger.info("🔄 긴급 상황 - 진입 계획 저장")
                    trade_id = self.save_trade_plan(emergency_strategy)
                    
                    if trade_id:
                        logger.info(f"✅ 긴급 진입 계획 저장 완료 (새 거래 ID: {trade_id})")
                        # 즉시 매수 조건 체크
                        self._check_immediate_buy_opportunity(trade_id)
                    else:
                        logger.warning("⚠️ 긴급 진입 계획 저장 실패")
            
            # 🆕 급변동 후 주기 재평가 쿨다운 리셋
            self.last_regime_check = None
            logger.info("🔄 급변동 대응 완료 - 주기 재평가 쿨다운 리셋")
            
            logger.info("✅ 긴급 전략 재분석 완료 - 동적 주기로 정상 운영 재개")
            
        except Exception as e:
            logger.error(f"❌ 긴급 전략 분석 중 오류: {e}")

    def _generate_emergency_position_advice(self, market_data, change_pct, spike_type):
        """긴급 포지션 관리 조언"""
        try:
            # 시장체제 재분석
            market_regime = self._analyze_market_regime(market_data)
            
            # 현재 활성 거래 정보
            position_status = market_data.get('position_status', {})
            active_trade = position_status.get('active_trade_info')
            current_price = market_data['current_price']
            
            # 수익/손실 상태 계산
            profit_status = "알수없음"
            if active_trade and len(active_trade) >= 2 and active_trade[1]:
                entry_price = active_trade[1]
                profit_rate = ((current_price - entry_price) / entry_price * 100)
                profit_status = f"{'수익권' if profit_rate > 0 else '손실권'} ({profit_rate:+.2f}%)"
            
            emergency_prompt = f"""
    🚨 긴급 상황 분석 요청: XRP {spike_type} {change_pct:+.2f}% 발생

    현재 XRP를 보유하고 있는 상황에서 {spike_type}이 발생했습니다.
    즉시 포지션 관리 전략을 재검토해주세요.

    급변동 상황: {spike_type} {abs(change_pct):.2f}%
    현재 시장체제: {market_regime['regime']}
    접근법: {market_regime['approach']}
    현재 수익상태: {profit_status}
    현재가: {current_price:,.0f}원

    긴급 조치사항 필요:
    1. 목표가/손절가 즉시 조정 필요성
    2. 부분 매도 또는 전량 매도 검토
    3. 추가 급변동 대비 전략

    ⚠️ **중요**: entry_price는 반드시 0으로 설정 (보유 중이므로)

    JSON 형식으로 긴급 조치사항을 제시해주세요.
    """
            
            # GPT 호출로 긴급 조언 생성
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": f"당신은 급변동 상황 전문 트레이딩 조언가입니다. {spike_type} 상황에서 즉시 실행 가능한 구체적 조치사항을 제시하세요."},
                    {"role": "user", "content": emergency_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "emergency_position_advice",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "entry_price": {"type": "number"},
                                "target_price": {"type": "number"},
                                "stop_loss_price": {"type": "number"},
                                "entry_reason": {"type": "string"},
                                "target_reason": {"type": "string"},
                                "stop_loss_reason": {"type": "string"},
                                "emergency_action": {"type": "string"},
                                "urgency_level": {"type": "string"}
                            },
                            "required": ["entry_price", "target_price", "stop_loss_price", "entry_reason", "target_reason", "stop_loss_reason", "emergency_action", "urgency_level"],
                            "additionalProperties": False
                        }
                    }
                },
                max_tokens=1000,
                temperature=0.1
            )
            
            # 응답 파싱 및 반환
            emergency_advice = json.loads(response.choices[0].message.content)
            logger.info(f"🚨 {spike_type} 긴급 조언 생성 완료")
            return emergency_advice
            
        except Exception as e:
            logger.error(f"❌ 긴급 포지션 조언 생성 중 오류: {e}")
            return None

    def _generate_emergency_entry_strategy(self, market_data, change_pct, spike_type):
        """긴급 진입 전략 생성"""
        try:
            # 시장체제 재분석
            market_regime = self._analyze_market_regime(market_data)
            current_price = market_data['current_price']
            
            emergency_prompt = f"""
    🚨 긴급 진입 기회 분석: XRP {spike_type} {change_pct:+.2f}% 발생

    XRP를 보유하지 않은 상황에서 {spike_type}이 발생했습니다.
    긴급 진입 기회를 검토해주세요.

    급변동 상황: {spike_type} {abs(change_pct):.2f}%
    현재 시장체제: {market_regime['regime']}
    접근법: {market_regime['approach']}
    현재가: {current_price:,.0f}원

    검토사항:
    1. {spike_type} 이후 추가 움직임 예상
    2. 진입 타이밍의 적절성
    3. 리스크 대비 보상 비율

    {"급등" if spike_type == "급등" else "급락"} 상황에 최적화된 전략을 JSON으로 제시해주세요.
    """
            
            # GPT 호출
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": f"당신은 급변동 상황 진입 전략 전문가입니다. {spike_type} 직후의 시장 상황을 분석하여 최적의 진입 전략을 제시하세요."},
                    {"role": "user", "content": emergency_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "emergency_entry_strategy",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "entry_price": {"type": "number"},
                                "target_price": {"type": "number"},
                                "stop_loss_price": {"type": "number"},
                                "entry_reason": {"type": "string"},
                                "target_reason": {"type": "string"},
                                "stop_loss_reason": {"type": "string"},
                                "spike_analysis": {"type": "string"},
                                "recommendation": {"type": "string"}
                            },
                            "required": ["entry_price", "target_price", "stop_loss_price", "entry_reason", "target_reason", "stop_loss_reason", "spike_analysis", "recommendation"],
                            "additionalProperties": False
                        }
                    }
                },
                max_tokens=1500,
                temperature=0.1
            )
            
            emergency_strategy = json.loads(response.choices[0].message.content)
            logger.info(f"🚨 {spike_type} 긴급 진입 전략 생성 완료")
            return emergency_strategy
            
        except Exception as e:
            logger.error(f"❌ 긴급 진입 전략 생성 중 오류: {e}")
            return None

    def _reset_schedule(self):
        """스케줄 재설정 - 다음 분석을 1시간 후로"""
        try:
            # 기존 스케줄 취소
            schedule.clear('strategy_analysis')
            
            # 새로운 30분 후 스케줄 등록
            schedule.every(30).minutes.do(self.run_strategy_analysis).tag('strategy_analysis')
            
            next_run = datetime.now() + timedelta(minutes=30)
            logger.info(f"📅 다음 정기 분석: {next_run.strftime('%H:%M:%S')}")
            
        except Exception as e:
            logger.error(f"❌ 스케줄 재설정 중 오류: {e}")

    def run_strategy_analysis(self):
        """전략 분석 - 1회성 즉시 분석 처리 개선"""
        try:
            # 1회성 즉시 분석 스케줄 처리 (개선된 방식)
            cleared_jobs = schedule.clear('immediate_analysis')
            if cleared_jobs:
                logger.info(f"⚡ 매도 후 즉시 분석 실행 ({cleared_jobs}개 즉시 분석 작업 완료)")
            
            interval_info = f"(현재 주기: {self.current_analysis_interval}분)"
            logger.info(f"🧠 동적 주기 전략 분석 시작 {interval_info}")
            
            # 1. OBSERVE - 시장 데이터 관찰
            market_data = self.observe_market_data()
            if not market_data:
                logger.error("❌ 시장 데이터 수집 실패 - 전략 분석 중단")
                return
            
            # 2. ORIENT & DECIDE - 포지션 인식 + 시장체제 전략 수립
            strategy = self.orient_and_decide(market_data)
            if strategy:
                # 3. ACT - 거래 계획 저장
                trade_id = self.save_trade_plan(strategy)
                if trade_id:
                    logger.info(f"📋 새로운 거래 계획 저장 완료 (ID: {trade_id})")
                    
                    # 즉시 매수 조건 체크
                    position_status = market_data.get('position_status', {})
                    if not position_status.get('has_position', False):
                        self._check_immediate_buy_opportunity(trade_id)
                else:
                    logger.info("📋 포지션 관리 조언 또는 저장 불필요")
            
            logger.info(f"✅ 동적 주기 전략 분석 완료 {interval_info}")
            
        except Exception as e:
            logger.error(f"❌ 전략 분석 중 오류: {e}")

    def get_trading_status(self):
        """현재 거래 상태 조회"""
        try:
            position_status = self.check_current_position()
            
            # 계획된 거래 조회
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM trades WHERE status = 'PLANNED'
                ''')
                planned_count = cursor.fetchone()[0]
                
                cursor.execute('''
                    SELECT COUNT(*) FROM trades WHERE status = 'ACTIVE'
                ''')
                active_count = cursor.fetchone()[0]
                
                cursor.execute('''
                    SELECT COUNT(*), AVG(profit_rate_pct), SUM(net_profit_krw)
                    FROM trades WHERE status = 'COMPLETED'
                ''')
                completed_data = cursor.fetchone()
                completed_count, avg_profit_rate, total_profit = completed_data
            
            status = {
                'position': {
                    'has_xrp': position_status['has_position'],
                    'xrp_balance': position_status['xrp_balance'],
                    'has_active_trade': position_status['has_active_trade']
                },
                'trades': {
                    'planned': planned_count,
                    'active': active_count,
                    'completed': completed_count or 0
                },
                'performance': {
                    'avg_profit_rate': round(avg_profit_rate or 0, 2),
                    'total_profit_krw': total_profit or 0
                }
            }
            
            return status
            
        except Exception as e:
            logger.error(f"❌ 거래 상태 조회 중 오류: {e}")
            return None

    def show_system_status(self):
        """시스템 현재 상태를 콘솔에 출력 (포지션 정보 포함)"""
        try:
            status = self.get_trading_status()
            position_status = self.check_current_position()
            
            if not status:
                print("❌ 시스템 상태를 조회할 수 없습니다.")
                return
            
            print("\n" + "="*60)
            print("🎯 OMNI-XRP 포지션 인식 + 시장체제 분석 시스템 현재 상태")
            print("="*60)
            
            # 포지션 상태
            print(f"💰 XRP 보유 상태: {'보유 중' if position_status['has_position'] else '미보유'}")
            if position_status['has_position']:
                print(f"   보유량: {position_status['xrp_balance']:.4f} XRP")
            
            print(f"📝 계획된 거래: {status['trades']['planned']}개")
            print(f"🚀 활성 거래: {status['trades']['active']}개") 
            print(f"✅ 완료된 거래: {status['trades']['completed']}개")
            
            # 성과 정보
            if status['performance']['total_profit_krw'] != 0:
                print(f"💰 총 수익: {status['performance']['total_profit_krw']:+,.0f}원")
                print(f"📈 평균 수익률: {status['performance']['avg_profit_rate']:+.2f}%")
            
            # 현재 활성 거래 정보
            if position_status['has_active_trade']:
                active_trade = position_status['active_trade_info']
                print(f"\n🔥 현재 활성 거래:")
                print(f"   ID: {active_trade[0]}")
                print(f"   진입가: {active_trade[1]:,.0f}원")
                print(f"   목표가: {active_trade[2]:,.0f}원")
                print(f"   손절가: {active_trade[3]:,.0f}원")
            
            # 다음 행동 예상
            print(f"\n🎯 다음 행동 예상:")
            if position_status['has_position'] and position_status['has_active_trade']:
                print("   → 현재 포지션 관리 중 (추가 매수 계획 없음)")
                print("   → 목표가/손절가 도달 시 매도 실행")
            elif status['trades']['planned'] > 0:
                print("   → 계획된 진입가 도달 시 매수 실행")
            else:
                print("   → 30분 후 새로운 시장체제 분석 및 전략 수립")
            
            print("="*60)
            
        except Exception as e:
            print(f"❌ 상태 확인 중 오류: {e}")

    def start_automated_trading(self):
        """자동화된 거래 시스템 시작 - 초기화 로직 강화"""
        logger.info("🚀 OMNI-XRP 동적 분석 주기 자동화 시스템 시작")
        
        # 시스템 시작 시 포지션 검증 및 기존 계획 정리
        self._validate_and_cleanup_existing_plans()
        
        # 1. 현재 상황에 맞는 초기 분석 주기 설정
        logger.info("🔄 시스템 시작 - 초기 분석 주기 설정")
        market_data = self.observe_market_data()
        if market_data:
            position_status = market_data.get('position_status', {})
            market_regime = self._analyze_market_regime(market_data)
            
            # 초기 주기 계산 및 즉시 적용
            initial_interval, mode_desc = self.get_dynamic_analysis_interval(
                position_status, market_regime
            )
            
            # ✅ 최초 스케줄 등록
            self.current_analysis_interval = initial_interval
            schedule.every(initial_interval).minutes.do(self.run_strategy_analysis).tag('strategy_analysis')
            
            logger.info(f"✅ 초기 분석 주기 설정: {mode_desc}")
            next_run = datetime.now() + timedelta(minutes=initial_interval)
            logger.info(f"⏰ 첫 번째 정규 분석: {next_run.strftime('%H:%M:%S')}")
        else:
            # 실패 시 기본값
            self.current_analysis_interval = 30
            schedule.every(30).minutes.do(self.run_strategy_analysis).tag('strategy_analysis')
            logger.warning("⚠️ 초기 데이터 수집 실패 - 30분 기본 주기로 시작")
        
        # 2. 5분마다 주기 재평가 스케줄 등록
        schedule.every(5).minutes.do(self.check_and_update_analysis_interval).tag('interval_check')
        
        # 3. 첫 전략 분석 즉시 실행
        logger.info("🚀 첫 전략 분석 즉시 실행")
        self.run_strategy_analysis()
        
        # 메인 루프: 2초마다 가격 감시 + 스케줄 실행
        while True:
            try:
                # 1. 급변동 감지 포함 가격 감시
                self.monitor_price_with_spike_detection()
                
                # 2. 스케줄 확인 및 실행
                schedule.run_pending()
                
                # 2초 대기
                time.sleep(2)
                
            except KeyboardInterrupt:
                logger.info("🛑 사용자 중단 - 시스템 종료")
                break
            except Exception as e:
                logger.error(f"❌ 메인 루프 오류: {e}")
                time.sleep(2)

# =============================================================================
    # 7. REFLECT - 회고 및 학습
    # =============================================================================
    
    def reflect_single_trade(self, completed_trade_id):
        """강화된 단일 거래 회고 분석 - 전체 포지션 히스토리 추적"""
        try:
            logger.info(f"🔍 거래 ID {completed_trade_id} 전체 히스토리 회고 분석 중...")
            
            # 1단계: 완료된 거래 정보 조회
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT trade_id, planned_entry_price, planned_target_price, planned_stop_loss,
                        actual_entry_price, actual_exit_price, trade_result, net_profit_krw,
                        profit_rate_pct, entry_reason, target_reason, stop_loss_reason, 
                        entry_timestamp, exit_timestamp, position_size_xrp
                    FROM trades 
                    WHERE trade_id = ? AND status = 'COMPLETED'
                ''', (completed_trade_id,))
                
                completed_trade = cursor.fetchone()
            
            if not completed_trade:
                logger.warning(f"⚠️ 거래 ID {completed_trade_id}의 완료된 데이터를 찾을 수 없습니다.")
                return
            
            # 2단계: 전체 포지션 히스토리 추적
            position_history = self._trace_position_history(completed_trade_id)
            
            if not position_history:
                logger.warning(f"⚠️ 거래 ID {completed_trade_id}의 히스토리를 추적할 수 없습니다.")
                return
            
            # 3단계: 회고 분석 실행
            reflection_analysis = self._perform_comprehensive_reflection(completed_trade, position_history)
            
            if reflection_analysis:
                # 4단계: 회고 결과 저장
                self._save_reflection_to_file(completed_trade_id, reflection_analysis)
                logger.info(f"✅ 거래 ID {completed_trade_id} 종합 회고 분석 완료")
                return reflection_analysis
            else:
                logger.error(f"❌ 거래 ID {completed_trade_id} 회고 분석 실패")
                return None
                
        except Exception as e:
            logger.error(f"❌ 강화된 회고 분석 중 오류: {e}")
            return None

    def _trace_position_history(self, completed_trade_id):
        """포지션 전체 히스토리 추적"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 완료된 거래 기본 정보
                cursor.execute('''
                    SELECT position_size_xrp, entry_timestamp, exit_timestamp, actual_exit_price
                    FROM trades 
                    WHERE trade_id = ? AND status = 'COMPLETED'
                ''', (completed_trade_id,))
                
                completed_info = cursor.fetchone()
                if not completed_info:
                    return None
                    
                position_size, entry_time, exit_time, exit_price = completed_info
                
                # 같은 포지션 크기를 가진 모든 관련 거래 조회 (시간 순)
                cursor.execute('''
                    SELECT trade_id, status, planned_entry_price, planned_target_price, planned_stop_loss,
                        actual_entry_price, entry_reason, target_reason, stop_loss_reason,
                        plan_timestamp, entry_timestamp
                    FROM trades 
                    WHERE position_size_xrp = ? OR trade_id = ?
                    ORDER BY plan_timestamp ASC
                ''', (position_size, completed_trade_id))
                
                all_related_trades = cursor.fetchall()
                
                if not all_related_trades:
                    return None
                
                # 히스토리 분석
                history = {
                    'original_entry': None,
                    'management_changes': [],
                    'final_exit': {
                        'trade_id': completed_trade_id,
                        'exit_price': exit_price,
                        'exit_time': exit_time
                    }
                }
                
                for trade in all_related_trades:
                    (t_id, status, plan_entry, plan_target, plan_stop, actual_entry, 
                    entry_reason, target_reason, stop_reason, plan_time, entry_time) = trade
                    
                    # 최초 진입 거래 찾기 (actual_entry_price가 0이 아닌 첫 번째)
                    if actual_entry and actual_entry > 0 and not history['original_entry']:
                        history['original_entry'] = {
                            'trade_id': t_id,
                            'actual_entry_price': actual_entry,
                            'entry_reason': entry_reason,
                            'entry_time': entry_time,
                            'original_target': plan_target,
                            'original_stop': plan_stop
                        }
                    
                    # 관리 계획 변경 추적 (SUPERSEDED 상태)
                    if status == 'SUPERSEDED':
                        history['management_changes'].append({
                            'trade_id': t_id,
                            'plan_time': plan_time,
                            'target_price': plan_target,
                            'stop_price': plan_stop,
                            'target_reason': target_reason,
                            'stop_reason': stop_reason,
                            'change_type': 'SUPERSEDED'
                        })
                
                # 최종 유효한 관리 계획 (COMPLETED 직전)
                if all_related_trades:
                    final_trade = all_related_trades[-1]  # 마지막 거래
                    if final_trade[0] == completed_trade_id:
                        history['final_plan'] = {
                            'final_target': final_trade[3],
                            'final_stop': final_trade[4],
                            'target_reason': final_trade[7],
                            'stop_reason': final_trade[8]
                        }
                
                return history
                
        except Exception as e:
            logger.error(f"포지션 히스토리 추적 중 오류: {e}")
            return None

    def _perform_comprehensive_reflection(self, completed_trade, position_history):
        """전체 포지션 히스토리를 고려한 종합 회고 분석"""
        try:
            # 거래 기본 정보 파싱
            (t_id, plan_entry, plan_target, plan_stop, actual_entry, actual_exit, 
            result, profit, profit_rate, entry_reason, target_reason, stop_reason, 
            entry_time, exit_time, position_size) = completed_trade
            
            # 실제 진입 정보 (히스토리에서 추출)
            original_entry = position_history.get('original_entry')
            if not original_entry:
                logger.error("실제 진입 정보를 찾을 수 없습니다.")
                return None
                
            real_entry_price = original_entry['actual_entry_price']
            real_entry_reason = original_entry['entry_reason']
            real_entry_time = original_entry['entry_time']
            
            # 관리 계획 변경 히스토리
            management_changes = position_history.get('management_changes', [])
            
            # 보유 기간 계산
            holding_duration = self._calculate_holding_duration(real_entry_time, exit_time)
            
            # 실제 수익률 재계산 (실제 진입가 기준)
            real_profit_rate = ((actual_exit - real_entry_price) / real_entry_price * 100)
            
            # 매도 이후 시장 분석
            post_sell_analysis = self._analyze_post_sell_market(exit_time, actual_exit)
            
            # 관리 계획 변경 분석
            management_analysis = self._analyze_management_changes(management_changes, real_entry_price, actual_exit)
            
            # 종합 회고 프롬프트
            comprehensive_prompt = f"""
    당신은 OMNI-XRP 시스템의 전문 트레이딩 분석가입니다. 다음 XRP 거래의 **전체 포지션 히스토리**를 종합 분석해주세요.

    ## 📊 거래 기본 정보
    - **최종 거래 ID**: {t_id}
    - **거래 결과**: {result}
    - **실제 보유 기간**: {holding_duration}
    - **실제 순수익**: {profit:+,.0f}원 ({real_profit_rate:+.2f}%)

    ## 🎯 실제 진입 정보 (가장 중요!)
    - **실제 진입 ID**: {original_entry['trade_id']}
    - **실제 진입가**: {real_entry_price:,.0f}원
    - **실제 진입 시간**: {real_entry_time}
    - **실제 진입 이유**: {real_entry_reason}
    - **최초 목표가**: {original_entry['original_target']:,.0f}원
    - **최초 손절가**: {original_entry['original_stop']:,.0f}원

    ## 📈 포지션 관리 히스토리
    {management_analysis}

    ## 🎯 최종 매도 분석
    - **최종 매도가**: {actual_exit:,.0f}원
    - **최종 매도 시간**: {exit_time}
    - **목표가 달성률**: {(actual_exit / plan_target * 100):.1f}%
    - **실제 진입가 대비 수익률**: {real_profit_rate:+.2f}%

    ## 🎯 매도 타이밍 적절성 분석
    {post_sell_analysis}

    다음 **10가지 핵심 관점**에서 전체 포지션 히스토리를 심층 분석해주세요:

    1. 🎯 **실제 진입 전략 평가** (진입가 {real_entry_price:,.0f}원, 이유: {real_entry_reason[:50]}...)
    2. 📊 **포지션 관리 적절성** (목표가/손절가 {len(management_changes)}회 변경)
    3. 🔄 **관리 계획 변경의 타당성** (각 변경이 수익에 미친 영향)
    4. ⏰ **보유 기간 최적성** ({holding_duration})
    5. 💰 **실제 수익률 달성도** ({real_profit_rate:+.2f}%)
    6. 🚨 **리스크 관리 효과성** (손절가 조정 히스토리)
    7. 🎓 **관리 계획 변경에서 얻은 교훈**
    8. 🔮 **다음 거래 시 관리 개선 방향**
    9. 💡 **AI 조언 vs 실제 결과 비교**
    10. 🏆 **전체 포지션 운영 종합 평가**

    각 관점별로 구체적인 분석과 개선점을 제시해주세요.
    """

            # GPT 호출
            reflection_response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 OMNI-XRP의 전문 포지션 관리 회고 분석가입니다.
                        
    단일 거래가 아닌 **전체 포지션 운영 히스토리**를 분석하여:
    1. 실제 진입부터 최종 매도까지의 전 과정 평가
    2. 관리 계획 변경의 타당성과 효과 분석
    3. 포지션 관리 전략의 개선점 도출
    4. 다음 거래에 적용할 구체적 교훈 제시

    분석은 실제 데이터 기반이며, 전체 맥락을 고려한 종합적 평가를 제공합니다."""
                    },
                    {"role": "user", "content": comprehensive_prompt}
                ],
                max_tokens=2500,
                temperature=0.1
            )
            
            return reflection_response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"❌ 종합 회고 분석 중 오류: {e}")
            return None

    def _analyze_management_changes(self, management_changes, entry_price, exit_price):
        """관리 계획 변경 분석"""
        try:
            if not management_changes:
                return "관리 계획 변경 없음 - 최초 계획대로 진행"
            
            analysis = f"총 {len(management_changes)}회의 관리 계획 변경 발생:\n"
            
            for i, change in enumerate(management_changes, 1):
                target_from_entry = ((change['target_price'] - entry_price) / entry_price * 100)
                stop_from_entry = ((change['stop_price'] - entry_price) / entry_price * 100)
                
                analysis += f"""
    {i}. 변경 시점: {change['plan_time']}
    - 목표가: {change['target_price']:,.0f}원 (진입가 대비 {target_from_entry:+.2f}%)
    - 손절가: {change['stop_price']:,.0f}원 (진입가 대비 {stop_from_entry:+.2f}%)
    - 목표 변경 이유: {change['target_reason'][:100]}...
    - 손절 변경 이유: {change['stop_reason'][:100]}...
    """
            
            # 최종 결과와 비교
            final_result = ((exit_price - entry_price) / entry_price * 100)
            analysis += f"\n최종 결과: {exit_price:,.0f}원 ({final_result:+.2f}%)"
            
            return analysis
            
        except Exception as e:
            logger.error(f"관리 계획 변경 분석 중 오류: {e}")
            return "관리 계획 변경 분석 실패"

    def _analyze_post_sell_market(self, exit_time, exit_price):
        """매도 이후 시장 분석"""
        try:
            # 매도 이후 30분, 1시간, 2시간 가격 변화 분석
            exit_datetime = datetime.strptime(exit_time, "%Y-%m-%d %H:%M:%S")
            current_time = datetime.now()
            
            # 현재 가격 확인
            orderbook = pyupbit.get_orderbook(ticker="KRW-XRP")
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            time_diff = current_time - exit_datetime
            price_change = ((current_price - exit_price) / exit_price * 100)
            
            if time_diff.total_seconds() < 1800:  # 30분 미만
                analysis = f"매도 후 {int(time_diff.total_seconds()/60)}분 경과 - 현재 {price_change:+.2f}% 변화"
            elif time_diff.total_seconds() < 3600:  # 1시간 미만
                analysis = f"매도 후 {int(time_diff.total_seconds()/60)}분 경과 - 현재 {price_change:+.2f}% 변화"
            else:
                hours = int(time_diff.total_seconds() / 3600)
                analysis = f"매도 후 {hours}시간 경과 - 현재 {price_change:+.2f}% 변화"
            
            # 매도 타이밍 평가
            if abs(price_change) < 1:
                timing_assessment = "적절한 매도 타이밍"
            elif price_change > 3:
                timing_assessment = "조기 매도 - 추가 상승 놓침"
            elif price_change < -3:
                timing_assessment = "적시 매도 - 추가 하락 회피"
            else:
                timing_assessment = "보통 수준의 매도 타이밍"
            
            return f"{analysis}\n평가: {timing_assessment}"
            
        except Exception as e:
            logger.error(f"매도 후 시장 분석 중 오류: {e}")
            return "매도 후 시장 분석 실패"
    
    def _calculate_holding_duration(self, entry_time, exit_time):
        """보유 기간 계산"""
        try:
            entry_dt = datetime.strptime(entry_time, "%Y-%m-%d %H:%M:%S")
            exit_dt = datetime.strptime(exit_time, "%Y-%m-%d %H:%M:%S")
            duration = exit_dt - entry_dt
            
            hours = duration.total_seconds() / 3600
            if hours < 1:
                return f"{int(duration.total_seconds() / 60)}분"
            elif hours < 24:
                return f"{hours:.1f}시간"
            else:
                days = hours / 24
                return f"{days:.1f}일"
                
        except Exception as e:
            logger.error(f"보유 기간 계산 중 오류: {e}")
            return "계산 실패"
    
    def _save_reflection_to_file(self, trade_id, reflection_content):
        """회고 내용을 Reflection.md 파일에 저장"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            reflection_entry = f"""
## 🔍 거래 ID {trade_id} 회고 분석 ({timestamp})

{reflection_content}

---

"""
            
            # 파일에 추가 (최신 내용이 위에 오도록)
            if os.path.exists('Reflection.md'):
                with open('Reflection.md', 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                
                with open('Reflection.md', 'w', encoding='utf-8') as f:
                    f.write(reflection_entry + existing_content)
            else:
                with open('Reflection.md', 'w', encoding='utf-8') as f:
                    f.write(f"# OMNI-XRP 거래 회고 분석 기록\n\n{reflection_entry}")
            
            logger.info(f"📝 거래 ID {trade_id} 회고 내용이 Reflection.md에 저장되었습니다.")
            
        except Exception as e:
            logger.error(f"❌ 회고 파일 저장 중 오류: {e}")

# =============================================================================
# 8. 메인 실행부 및 전략 프롬프트 파일 생성
# =============================================================================

def create_enhanced_strategy_prompt_file():
    """최적화된 전문 프롬프트 파일들 생성"""
    
    # 1. 포지션 관리 전용 프롬프트
    position_management_content = """# OMNI-XRP 포지션 관리 전용 가이드 v6.0

## 👤 페르소나 (Persona)
당신은 수십 년간 암호화폐 시장, 특히 XRP의 극심한 변동성을 겪어온 **베테랑 퀀트 트레이더이자 리스크 관리 총책임자(CRO)**입니다. 당신의 임무는 새로운 대박을 찾는 것이 아니라, **이미 이륙한 비행기를 안전하게 착륙시키는 것**입니다. 모든 판단은 자본 보호를 최우선으로 하며, 감정적 희망 회로를 배제하고 데이터에 기반한 냉철한 조언만을 제공합니다.

## 🎯 4단계 사고 과정 (4-Step Reasoning)
최종 JSON을 생성하기 전에, 반드시 아래 4단계 사고 과정을 거쳐 결론을 도출하십시오.

1.  **상황 재평가 (Re-assessment):** 현재 포지션(수익/손실)과 OMNI 시스템이 진단한 시장 체제는 어떤 의미인가? 최초 진입 근거는 아직 유효한가?
2.  **리스크 식별 (Risk Identification):** 현시점에서 포지션을 유지할 경우 가장 큰 리스크는 무엇인가? (예: 체제 악화, BTC 급락 가능성)
3.  **전략 선택 (Strategy Selection):** 현재 최선은 '홀딩(Holding)', '부분 익절(Partial Profit-Take)', '전량 매도(Full Exit)' 중 무엇인가? 그 근거는?
4.  **가격 조정 (Price Adjustment):** 만약 '홀딩'이라면, 현재 상황에 맞게 목표가와 손절가를 어떻게 조정해야 하는가? 손절가는 절대 하향 조정하지 않는다.

---

## 🎯 핵심 철학
당신은 XRP 보유 중인 상황에서 최적의 포지션 관리 전문가입니다.

## 💡 핵심 고려사항 (최우선 적용!)
- **수익권 + 상승 추세** → 손절가 점진적 상향 조정 (트레일링 효과)
- **손실권 + 하락 추세** → 빠른 탈출 우선, 추가 하락 방지
- **목표가 달성률 80% 이상** → 일부 매도로 수익 확보
- **보유 기간 24시간+** → 시장 피로감 고려한 청산 검토
- **급변동 후** → 감정 매매 방지, 데이터 기반 냉정 판단

## 📊 수익률별 차별화 전략

### 📈 수익권 (+3% 이상)
- **+3~+10%**: 기존 계획 유지, 시장체제 변화시만 조정
- **+10~+20%**: 손절가 점진적 상향 조정 (진입가+5% 이상으로)
- **+20% 이상**: 일부 매도 필수 고려 (50% 물량)

### 📉 손실권 (-3% 이하)
- **-3~-8%**: 손절가 타이트 조정, 빠른 탈출 준비
- **-8% 이하**: 즉시 매도 또는 데드캣 바운스 대기

## 🎯 시장체제별 포지션 관리

### 상승장 지속 (체제점수 +2 이상)
```json
수익권: 손절가 = max(기존, 진입가×1.05, 현재가×0.93)
목표가: 상향 조정 고려 (ATR×2.0 범위)
전략: "상승 추세 지속으로 수익 극대화 - X% 트레일링 적용"
```

### 횡보 전환 (BB Squeeze, ATR 압축)
```json
수익권: 손절가 = max(기존, BB하단×1.02)
목표가: BB중심선 또는 현재가+3%
전략: "횡보 전환으로 보수적 수익 확보 우선"
```

### 하락장 전환 (체제점수 -1 이하)
```json
수익권: 목표가 = 현재가×1.02 (빠른 탈출)
손실권: 손절가 = 현재가×0.98 (타이트 손절)
전략: "하락장 전환 - 빠른 탈출로 자본 보호"
```

## ⚠️ 절대 원칙
**entry_price = 0** (보유 중이므로 진입 불가)
"""

    # 2. 신규 진입 전용 프롬프트
    entry_strategy_content = """# OMNI-XRP 신규 진입 전용 가이드 v6.0

## 👤 페르소나 (Persona)
당신은 수십 년간 암호화폐 시장, 특히 XRP의 극심한 변동성을 겪어온 **베테랑 퀀트 트레이더이자 리스크 관리 총책임자(CRO)**입니다. 당신의 최우선 임무는 '돈을 버는 것' 이전에 **'잃지 않는 것'**입니다. 모든 결정은 데이터에 기반하되, 항상 최악의 시나리오를 염두에 두고 자본을 보호하는 방향으로 내려져야 합니다.

## 🎯 5단계 사고 과정 (5-Step Reasoning)
최종 JSON을 생성하기 전에, 반드시 아래 5단계 사고 과정을 거쳐 결론을 도출하십시오.

1.  **진단 검증 (Verification):** OMNI 시스템의 1차 진단(예: '횡보_박스권')은 타당한가? 데이터와 상충되는 부분은 없는가? 신뢰도 점수가 낮은 이유는 무엇인가?
2.  **기회와 리스크 식별 (Opportunity & Risk Identification):** 현재 가장 매력적인 매수 시그널과, 가장 치명적인 리스크는 각각 무엇인가? 기회와 리스크 중 어느 쪽이 더 우세한가?
3.  **전략 선택 (Strategy Selection):** 시스템 권장 접근법(예: 단기매매)이 최선인가? 아니면 현재 리스크를 고려할 때 '관망'이 더 현명한 선택인가?
4.  **가격 결정 (Price Determination):** 제안된 ATR 기반 가격을 그대로 사용할 것인가, 아니면 리스크를 고려해 더 보수적으로 조정할 것인가? 예상 손익비(Reward/Risk Ratio)는 최소 1.5 이상인가?
5.  **최종 계획 수립 (Final Plan Formulation):** 위 분석을 종합하여, 최종 거래 계획을 JSON 형식으로 작성한다. 모든 필드에 대한 논리적 근거는 이 사고 과정에 명시되어 있어야 한다.

---
## 🎯 핵심 철학 (v6.0)
당신은 XRP 미보유 상황에서 최적의 진입 기회를 포착하는 전문가입니다.

## 📊 시장체제별 진입 전략

### 명백한_상승장 (체제점수 +2 이상)
```python
진입가: 현재가×1.01 (소폭 추격매수)
목표가: 현재가×1.08 (ATR×2.0 기준)
손절가: 현재가×0.95 (5% 손절)
포지션: 적극적 (잔고의 80-95%)
```

### 횡보_박스권 (BB Squeeze)
```python
진입가: min(BB하단×1.01, 현재가×0.98)
목표가: BB중심선
손절가: BB하단×0.98
포지션: 중간 (잔고의 50-70%)
```

### 혼조장 (애매한 상황)
```python
진입가: 현재가×0.97 (하락 대기)
목표가: 현재가×1.05 (보수적)
손절가: 현재가×0.93 (7% 손절)
포지션: 보수적 (잔고의 30-50%)
```

## 🚨 진입 금지 조건
- 시장체제 = "명백한_하락장"
- BTC 1시간 변동률 < -3%
- XRP ATR > 8% (극심한 변동성)
- 주요 뉴스 발표 1시간 이내

## 💡 XRP 특화 진입 기법
- **뉴스 후 안정화**: 급변동 후 30분 대기
- **BTC 동조화**: BTC 추세와 XRP 추세 일치 확인
- **거래량 확인**: 평균 대비 150% 이상 시에만
- **기술적 확인**: 최소 3개 시간대 신호 일치
"""

    # 3. 기본 전략 프롬프트 (공통 기반)
    base_strategy_content = """# OMNI-XRP 기본 전략 가이드 v6.0

## 🎯 핵심 철학
- **XRP 특화**: 극변동성(일 10%+) + 뉴스 민감성 + BTC 상관관계
- **시장체제 우선**: 강세/약세/횡보/혼조별 차별화 전략
- **포지션 인식**: 보유 vs 미보유 상황별 접근
- **A-D 지표**: 추세+모멘텀+변동성+거래량 종합 분석
- **과거 학습**: 성공 패턴 재활용 + 실패 회피

## 🚨 XRP 거래 핵심 원칙
1. **변동성 대응**: ATR > 5% 시 포지션 축소, ATR < 2% 시 확대
2. **뉴스 대응**: 급등/급락 후 즉시 분석, 감정 매매 금지
3. **BTC 추종**: BTC 강하락(-3%+) 시 XRP 매매 금지
4. **시간 관리**: 보유 기간 24시간 초과 시 재검토
5. **수익률 관리**: +20% 이상 시 일부 매도 필수 고려

## 📊 시장체제별 기본 접근법
- **명백한_하락장**: 매매금지 (체제점수 -2 이하)
- **횡보_박스권**: Mean Reversion (BB 하단→중심선)
- **명백한_상승장**: 추세추종 (체제점수 +2 이상)
- **혼조장**: 신중매매 (명확한 신호에서만)
"""

    # 파일들 생성
    with open('omni_position_management.txt', 'w', encoding='utf-8') as f:
        f.write(position_management_content)
    
    with open('omni_entry_strategy.txt', 'w', encoding='utf-8') as f:
        f.write(entry_strategy_content)

    with open('omni_base_strategy.txt', 'w', encoding='utf-8') as f:
        f.write(base_strategy_content)
    
    # 기존 통합 파일도 업데이트
    combined_content = f"""# OMNI-XRP 통합 전략 시스템 v7.0

{base_strategy_content}

## 상황별 세부 가이드
- 포지션 관리: omni_position_management.txt 참조
- 신규 진입: omni_entry_strategy.txt 참조  
"""
    
    with open('omni_xrp_strategy.txt', 'w', encoding='utf-8') as f:
        f.write(combined_content)
    
    print("✅ 전문화된 프롬프트 파일 시스템 생성 완료:")
    print("  📁 omni_position_management.txt (포지션 관리 전용)")
    print("  📁 omni_entry_strategy.txt (신규 진입 전용)")
    print("  📁 omni_base_strategy.txt (기본 전략)")
    print("  📁 omni_xrp_strategy.txt (통합 가이드)")

def main():
    """메인 실행 함수"""
    try:
        print("🎯 OMNI-XRP v5.0 포지션 인식 + 시장체제 분석 + 동적 포지션 사이징 완전 통합 시스템 시작")
        print("⚡ 실행 주기: 가격감시 2초 | 전략분석 30분")
        print("🔬 핵심 기능:")
        print("   • 시장체제별 차별화 전략 (강세/약세/횡보/혼조)")
        print("   • 동적 포지션 사이징 (체제별 투자 비중 자동 조절)")
        print("   • 3층 안전망 (하드코딩 + AI + 검증)")
        print("   • ATR 기반 동적 가격 시스템")
        print("   • EMA60 포함 완전한 지표 체계")
        print("🚨 급변동 감지: 0.7% 이상 (3분 쿨다운)")
        
        if not os.path.exists('omni_xrp_strategy.txt'):
            create_enhanced_strategy_prompt_file()
        
        # OMNI-XRP 시스템 초기화
        omni_system = OMNIXRPSystem()
        
        # 현재 상태 확인
        status = omni_system.get_trading_status()
        if status:
            logger.info(f"📊 현재 시스템 상태: {status}")
        
        # 자동화 거래 시작 (가격감시 2초, 전략분석 30분 주기)
        omni_system.start_automated_trading()
        
    except KeyboardInterrupt:
        logger.info("🛑 사용자 중단 - OMNI-XRP 시스템 종료")
    except Exception as e:
        logger.error(f"❌ 메인 실행 중 오류: {e}")

if __name__ == "__main__":
    import sys
    
    # 명령줄 인자 처리
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        system = OMNIXRPSystem()
        system.show_system_status()
    else:
        main()