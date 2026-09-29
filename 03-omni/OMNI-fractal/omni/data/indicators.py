# data/indicators.py
# "다양한 기술적 지표를 계산하여 순수 데이터로 제공하는 지표 계산 파일"

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

class TechnicalIndicators:

    @staticmethod
    # "DataFrame에서 모든 기술 지표를 계산하여 딕셔너리로 반환하는 정적 메서드" (인자: df)
    def calculate_indicators(df: pd.DataFrame) -> Dict[str, Any]:

        if df is None or df.empty:
            return {}
        
        data_len = len(df)
        if data_len < 2:
            return {}

        indicators = {}
        
        # 1. 기본 가격 정보
        try:
            latest = df.iloc[-1]
            indicators['open'] = float(latest.get('open', 0))
            indicators['high'] = float(latest.get('high', 0))
            indicators['low'] = float(latest.get('low', 0))
            indicators['close'] = float(latest.get('close', 0))
            indicators['volume'] = float(latest.get('volume', 0))

            if indicators['close'] <= 0:
                return {}
                
        except Exception:
            return {}
        
        # 2. 가격 변화율
        try:
            if data_len >= 2:
                prev_close = float(df.iloc[-2].get('close', 0))
                if prev_close > 0:
                    indicators['price_change'] = float(indicators['close'] - prev_close)
                    indicators['price_change_rate'] = float(
                        (indicators['close'] - prev_close) / prev_close * 100
                    )
                else:
                    indicators['price_change'] = 0.0
                    indicators['price_change_rate'] = 0.0
        except:
            indicators['price_change'] = 0.0
            indicators['price_change_rate'] = 0.0
        
        # 3. 거래량 통계
        try:
            if data_len >= 20:
                indicators['volume_mean_20'] = float(df['volume'].rolling(20).mean().iloc[-1])
                indicators['volume_std_20'] = float(df['volume'].rolling(20).std().iloc[-1])
            elif data_len >= 5:
                indicators['volume_mean_5'] = float(df['volume'].rolling(5).mean().iloc[-1])
                indicators['volume_std_5'] = float(df['volume'].rolling(5).std().iloc[-1])
            
            # 거래량 비율 (현재/평균)
            if data_len >= 20:
                vol_mean = df['volume'].rolling(20).mean().iloc[-1]
            elif data_len >= 5:
                vol_mean = df['volume'].rolling(5).mean().iloc[-1]
            else:
                vol_mean = df['volume'].mean()
                
            if pd.notna(vol_mean) and vol_mean > 0:
                indicators['volume_ratio'] = float(indicators['volume'] / vol_mean)
            else:
                indicators['volume_ratio'] = 1.0
                
        except:
            indicators['volume_ratio'] = 1.0
        
        # 4. RSI (14)
        if data_len >= 14:
            indicators['rsi'] = TechnicalIndicators._calculate_rsi(df)
        
        # 5. 볼린저 밴드 (20, 2)
        if data_len >= 20:
            bb_result = TechnicalIndicators._calculate_bollinger_bands(df)
            indicators.update(bb_result)
        
        # 6. 이동평균선 (5, 20, 60, 120)
        ma_result = TechnicalIndicators._calculate_moving_averages(df, data_len)
        indicators.update(ma_result)
        
        # 7. MACD (12, 26, 9)
        if data_len >= 26:
            macd_result = TechnicalIndicators._calculate_macd(df)
            indicators.update(macd_result)
        
        # 8. 스토캐스틱 (14, 3, 3)
        if data_len >= 14:
            stoch_result = TechnicalIndicators._calculate_stochastic(df)
            indicators.update(stoch_result)
        
        # 9. ATR (14)
        if data_len >= 14:
            atr_result = TechnicalIndicators._calculate_atr(df)
            indicators.update(atr_result)
        
        # 10. OBV (On Balance Volume)
        if data_len >= 2:
            obv_result = TechnicalIndicators._calculate_obv(df)
            indicators.update(obv_result)
        
        # 11. 최고/최저가 통계
        if data_len >= 20:
            indicators['high_20'] = float(df['high'].rolling(20).max().iloc[-1])
            indicators['low_20'] = float(df['low'].rolling(20).min().iloc[-1])
        if data_len >= 60:
            indicators['high_60'] = float(df['high'].rolling(60).max().iloc[-1])
            indicators['low_60'] = float(df['low'].rolling(60).min().iloc[-1])
        
        # 12. 변동성 지표
        if data_len >= 20:
            indicators['volatility_20'] = float(df['close'].pct_change().rolling(20).std().iloc[-1])
        if data_len >= 5:
            indicators['volatility_5'] = float(df['close'].pct_change().rolling(5).std().iloc[-1])
        
        # 13. 프랙탈 분석용 지지/저항 레벨 (추가)
        if data_len >= 50:
            sr_levels = TechnicalIndicators.calculate_support_resistance(df)
            indicators.update(sr_levels)
        
        # 14. 패턴 강도 지표 (추가)
        if data_len >= 20:
            pattern_strength = TechnicalIndicators._calculate_pattern_strength(df)
            indicators.update(pattern_strength)
        
        # 최종 검증 (NaN, Inf 제거)
        return TechnicalIndicators._clean_indicators(indicators)

    @staticmethod
    # "프랙탈 분석을 위한 지지/저항 레벨을 계산하는 정적 메서드" (인자: df, lookback)
    def calculate_support_resistance(df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        """프랙탈 분석을 위한 주요 지지/저항 레벨 계산"""
        result = {}
        
        try:
            # 최근 N개 캔들 데이터
            recent_df = df.tail(lookback)
            
            # 1. 피봇 포인트 계산
            pivot_result = TechnicalIndicators._calculate_pivot_points(recent_df)
            result.update(pivot_result)
            
            # 2. 프랙탈 기반 지지/저항
            fractal_levels = TechnicalIndicators._find_fractal_levels(recent_df)
            result['fractal_resistance'] = fractal_levels['resistance']
            result['fractal_support'] = fractal_levels['support']
            
            # 3. 거래량 가중 지지/저항
            volume_levels = TechnicalIndicators._find_volume_weighted_levels(recent_df)
            result['volume_resistance'] = volume_levels['resistance']
            result['volume_support'] = volume_levels['support']
            
            # 4. 심리적 가격대 (라운드 넘버)
            current_price = float(df['close'].iloc[-1])
            psychological_levels = TechnicalIndicators._find_psychological_levels(current_price)
            result['psychological_resistance'] = psychological_levels['resistance']
            result['psychological_support'] = psychological_levels['support']
            
            # 5. 동적 지지/저항 (이동평균선 기반)
            dynamic_levels = TechnicalIndicators._calculate_dynamic_levels(df)
            result.update(dynamic_levels)
            
        except Exception as e:
            pass
        
        return result
    
    @staticmethod
    # "피봇 포인트와 관련 레벨을 계산하는 정적 메서드" (인자: df)
    def _calculate_pivot_points(df: pd.DataFrame) -> Dict[str, float]:
        """전통적인 피봇 포인트 계산"""
        result = {}
        
        try:
            # 전일 고/저/종가
            prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
            high = float(prev['high'])
            low = float(prev['low'])
            close = float(prev['close'])
            
            # 피봇 포인트
            pivot = (high + low + close) / 3
            result['pivot_point'] = pivot
            
            # 저항선
            result['r1'] = 2 * pivot - low
            result['r2'] = pivot + (high - low)
            result['r3'] = high + 2 * (pivot - low)
            
            # 지지선
            result['s1'] = 2 * pivot - high
            result['s2'] = pivot - (high - low)
            result['s3'] = low - 2 * (high - pivot)
            
            # 카마릴라 피봇
            range_hl = high - low
            result['camarilla_r1'] = close + range_hl * 1.0833
            result['camarilla_r2'] = close + range_hl * 1.1666
            result['camarilla_s1'] = close - range_hl * 1.0833
            result['camarilla_s2'] = close - range_hl * 1.1666
            
        except:
            pass
        
        return result
    
    @staticmethod
    # "프랙탈 패턴을 찾아 지지/저항 레벨을 식별하는 정적 메서드" (인자: df)
    def _find_fractal_levels(df: pd.DataFrame) -> Dict[str, List[float]]:
        """Williams Fractal 패턴으로 지지/저항 찾기"""
        result = {'resistance': [], 'support': []}
        
        try:
            highs = df['high'].values
            lows = df['low'].values
            
            # 프랙탈 고점 (저항) 찾기
            for i in range(2, len(highs) - 2):
                if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                    result['resistance'].append(float(highs[i]))
            
            # 프랙탈 저점 (지지) 찾기
            for i in range(2, len(lows) - 2):
                if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                    result['support'].append(float(lows[i]))
            
            # 중복 제거 및 정렬
            result['resistance'] = sorted(list(set(result['resistance'])), reverse=True)[:3]
            result['support'] = sorted(list(set(result['support'])))[:3]
            
        except:
            pass
        
        return result
    
    @staticmethod
    # "거래량 가중 가격 레벨을 찾는 정적 메서드" (인자: df)
    def _find_volume_weighted_levels(df: pd.DataFrame) -> Dict[str, List[float]]:
        """거래량이 집중된 가격대 찾기"""
        result = {'resistance': [], 'support': []}
        
        try:
            # VWAP 계산
            vwap = (df['close'] * df['volume']).sum() / df['volume'].sum()
            current_price = float(df['close'].iloc[-1])
            
            # 거래량 프로파일 생성
            price_levels = np.linspace(df['low'].min(), df['high'].max(), 20)
            volume_profile = []
            
            for i in range(len(price_levels) - 1):
                mask = (df['close'] >= price_levels[i]) & (df['close'] < price_levels[i+1])
                vol = df.loc[mask, 'volume'].sum()
                volume_profile.append((price_levels[i], vol))
            
            # 거래량이 많은 상위 가격대 선택
            volume_profile.sort(key=lambda x: x[1], reverse=True)
            
            for price, _ in volume_profile[:5]:
                if price > current_price:
                    result['resistance'].append(float(price))
                else:
                    result['support'].append(float(price))
            
            # VWAP 추가
            if vwap > current_price:
                result['resistance'].append(float(vwap))
            else:
                result['support'].append(float(vwap))
            
            result['resistance'] = sorted(result['resistance'][:3])
            result['support'] = sorted(result['support'], reverse=True)[:3]
            
        except:
            pass
        
        return result
    
    @staticmethod
    # "심리적 가격대를 찾는 정적 메서드" (인자: price)
    def _find_psychological_levels(price: float) -> Dict[str, List[float]]:
        """라운드 넘버 등 심리적 가격대 찾기"""
        result = {'resistance': [], 'support': []}
        
        try:
            # 자릿수에 따른 라운드 넘버 간격 결정
            if price >= 10000:
                interval = 1000
            elif price >= 1000:
                interval = 100
            elif price >= 100:
                interval = 10
            elif price >= 10:
                interval = 1
            else:
                interval = 0.1
            
            # 현재 가격 기준 라운드 넘버
            base = int(price / interval) * interval
            
            # 저항선 (위쪽 라운드 넘버)
            for i in range(1, 4):
                result['resistance'].append(float(base + interval * i))
            
            # 지지선 (아래쪽 라운드 넘버)
            for i in range(0, 3):
                result['support'].append(float(base - interval * i))
            
        except:
            pass
        
        return result
    
    @staticmethod
    # "동적 지지/저항 레벨을 계산하는 정적 메서드" (인자: df)
    def _calculate_dynamic_levels(df: pd.DataFrame) -> Dict[str, float]:
        """이동평균선 기반 동적 지지/저항"""
        result = {}
        
        try:
            current_price = float(df['close'].iloc[-1])
            
            # 주요 이동평균선
            for period in [20, 50, 100, 200]:
                if len(df) >= period:
                    ma = df['close'].rolling(period).mean().iloc[-1]
                    if pd.notna(ma):
                        key = f'ma{period}_level'
                        result[key] = float(ma)
                        
                        # 현재 가격과의 관계
                        if ma > current_price:
                            result[f'ma{period}_type'] = 'resistance'
                        else:
                            result[f'ma{period}_type'] = 'support'
            
            # EMA도 추가
            for period in [12, 26]:
                if len(df) >= period:
                    ema = df['close'].ewm(span=period).mean().iloc[-1]
                    if pd.notna(ema):
                        result[f'ema{period}_level'] = float(ema)
            
        except:
            pass
        
        return result
    
    @staticmethod
    # "패턴 강도 지표를 계산하는 정적 메서드" (인자: df)
    def _calculate_pattern_strength(df: pd.DataFrame) -> Dict[str, float]:
        """패턴의 강도와 신뢰도 측정"""
        result = {}
        
        try:
            # 1. 추세 강도 (ADX)
            if len(df) >= 14:
                adx = ta.adx(df['high'], df['low'], df['close'], length=14)
                if adx is not None and 'ADX_14' in adx.columns:
                    result['adx'] = float(adx['ADX_14'].iloc[-1])
            
            # 2. 모멘텀 강도
            if len(df) >= 10:
                roc = ta.roc(df['close'], length=10)
                if roc is not None and not roc.empty:
                    result['momentum_10'] = float(roc.iloc[-1])
            
            # 3. 볼륨 강도
            if len(df) >= 20:
                volume_ma = df['volume'].rolling(20).mean()
                recent_vol = df['volume'].tail(5).mean()
                result['volume_strength'] = float(recent_vol / volume_ma.iloc[-1]) if volume_ma.iloc[-1] > 0 else 1.0
            
            # 4. 변동성 수축/확장
            if len(df) >= 20:
                bb_width = ta.bbands(df['close'], length=20)
                if bb_width is not None and not bb_width.empty:
                    upper_col = [col for col in bb_width.columns if 'BBU' in col or 'UPPER' in col][0]
                    lower_col = [col for col in bb_width.columns if 'BBL' in col or 'LOWER' in col][0]
                    
                    current_width = bb_width[upper_col].iloc[-1] - bb_width[lower_col].iloc[-1]
                    avg_width = (bb_width[upper_col] - bb_width[lower_col]).mean()
                    
                    result['bb_squeeze'] = float(current_width / avg_width) if avg_width > 0 else 1.0
            
        except:
            pass
        
        return result

    @staticmethod
    # "RSI (상대강도지수)를 계산하는 정적 메서드" (인자: df)
    def _calculate_rsi(df: pd.DataFrame) -> float:
        try:
            rsi = ta.rsi(df['close'], length=14)
            if rsi is not None and not rsi.empty:
                rsi_value = float(rsi.iloc[-1])
                if pd.notna(rsi_value) and 0 <= rsi_value <= 100:
                    return rsi_value
        except:
            pass
        return 50.0
    
    @staticmethod
    # "볼린저 밴드를 계산하는 정적 메서드" (인자: df)
    def _calculate_bollinger_bands(df: pd.DataFrame) -> Dict[str, float]:
        result = {}
        
        try:
            bb = ta.bbands(df['close'], length=20, std=2)
            
            if bb is not None and isinstance(bb, pd.DataFrame) and not bb.empty:
                for col in bb.columns:
                    col_upper = col.upper()
                    if 'BBU' in col_upper or 'UPPER' in col_upper:
                        result['bb_upper'] = float(bb[col].iloc[-1])
                    elif 'BBM' in col_upper or 'MIDDLE' in col_upper or 'MID' in col_upper:
                        result['bb_middle'] = float(bb[col].iloc[-1])
                    elif 'BBL' in col_upper or 'LOWER' in col_upper:
                        result['bb_lower'] = float(bb[col].iloc[-1])
                
                # BB Position 계산 (0-100)
                if all(k in result for k in ['bb_upper', 'bb_middle', 'bb_lower']):
                    current_price = float(df['close'].iloc[-1])
                    upper = result['bb_upper']
                    lower = result['bb_lower']
                    
                    if upper > lower:
                        position = (current_price - lower) / (upper - lower) * 100
                        result['bb_position'] = max(0, min(100, position))
                    else:
                        result['bb_position'] = 50.0
        except:
            pass
        
        return result
    
    @staticmethod
    # "이동평균선 (SMA, EMA)을 계산하는 정적 메서드" (인자: df, data_len)
    def _calculate_moving_averages(df: pd.DataFrame, data_len: int) -> Dict[str, Any]:
        result = {}
        
        try:
            # SMA 계산
            periods = [5, 20, 60, 120]
            for period in periods:
                if data_len >= period:
                    sma = ta.sma(df['close'], length=period)
                    if sma is not None and not sma.empty:
                        sma_value = float(sma.iloc[-1])
                        if pd.notna(sma_value):
                            result[f'sma_{period}'] = sma_value
            
            # EMA 계산
            ema_periods = [12, 26]
            for period in ema_periods:
                if data_len >= period:
                    ema = ta.ema(df['close'], length=period)
                    if ema is not None and not ema.empty:
                        ema_value = float(ema.iloc[-1])
                        if pd.notna(ema_value):
                            result[f'ema_{period}'] = ema_value
                            
        except:
            pass
        
        return result
    
    @staticmethod
    # "MACD 지표를 계산하는 정적 메서드" (인자: df)
    def _calculate_macd(df: pd.DataFrame) -> Dict[str, float]:
        result = {}
        
        try:
            macd = ta.macd(df['close'])
            if macd is not None and isinstance(macd, pd.DataFrame) and not macd.empty:
                mapping = {
                    'MACD_12_26_9': 'macd',
                    'MACDs_12_26_9': 'macd_signal',
                    'MACDh_12_26_9': 'macd_histogram'
                }
                
                for col, key in mapping.items():
                    if col in macd.columns:
                        value = float(macd[col].iloc[-1])
                        if pd.notna(value):
                            result[key] = value
        except:
            pass
        
        return result
    
    @staticmethod
    # "스토캐스틱 지표를 계산하는 정적 메서드" (인자: df)
    def _calculate_stochastic(df: pd.DataFrame) -> Dict[str, float]:
        result = {}
        
        try:
            stoch = ta.stoch(df['high'], df['low'], df['close'])
            if stoch is not None and isinstance(stoch, pd.DataFrame) and not stoch.empty:
                if 'STOCHk_14_3_3' in stoch.columns:
                    k_value = float(stoch['STOCHk_14_3_3'].iloc[-1])
                    if pd.notna(k_value):
                        result['stoch_k'] = max(0, min(100, k_value))
                
                if 'STOCHd_14_3_3' in stoch.columns:
                    d_value = float(stoch['STOCHd_14_3_3'].iloc[-1])
                    if pd.notna(d_value):
                        result['stoch_d'] = max(0, min(100, d_value))
        except:
            pass
        
        return result

    @staticmethod
    # "ATR (평균진폭)을 계산하는 정적 메서드" (인자: df, period)
    def _calculate_atr(df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
        result = {}
        
        try:
            atr = ta.atr(df['high'], df['low'], df['close'], length=period)
            
            if atr is not None and not atr.empty and len(atr) > 0:
                atr_value = float(atr.iloc[-1])
                current_price = float(df['close'].iloc[-1])
                
                if pd.notna(atr_value) and atr_value > 0 and current_price > 0:
                    result["atr"] = atr_value
                    result["atr_percentage"] = (atr_value / current_price) * 100
                    
        except:
            pass
        
        return result
    
    @staticmethod
    # "OBV (누적거래량)를 계산하는 정적 메서드" (인자: df)
    def _calculate_obv(df: pd.DataFrame) -> Dict[str, float]:
        result = {}
        
        try:
            obv = ta.obv(df['close'], df['volume'])
            if obv is not None and not obv.empty:
                current_obv = float(obv.iloc[-1])
                if pd.notna(current_obv):
                    result['obv'] = current_obv
                    
                    # OBV 변화율
                    if len(obv) >= 20:
                        obv_20_ago = float(obv.iloc[-20])
                        if pd.notna(obv_20_ago) and obv_20_ago != 0:
                            result['obv_change_20'] = (current_obv - obv_20_ago) / abs(obv_20_ago) * 100
        except:
            pass
        
        return result
    
    @staticmethod
    # "NaN과 Inf 값을 정리하여 깨끗한 데이터를 반환하는 정적 메서드" (인자: indicators)
    def _clean_indicators(indicators: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        
        for key, value in indicators.items():
            if isinstance(value, (int, float)):
                if pd.isna(value) or np.isinf(value):
                    if 'rsi' in key:
                        cleaned[key] = 50.0
                    elif 'volume_ratio' in key:
                        cleaned[key] = 1.0
                    elif 'position' in key:
                        cleaned[key] = 50.0
                    else:
                        cleaned[key] = 0.0
                else:
                    cleaned[key] = float(value)
            elif isinstance(value, list):
                # 리스트 값들도 정리
                cleaned[key] = [float(v) if pd.notna(v) and not np.isinf(v) else 0.0 for v in value]
            else:
                cleaned[key] = value
        
        return cleaned