# data/indicators.py
# "다양한 기술적 지표를 계산하여 순수 데이터로 제공하는 지표 계산 파일"

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Optional
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
        
        # 최종 검증 (NaN, Inf 제거)
        return TechnicalIndicators._clean_indicators(indicators)

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
            else:
                cleaned[key] = value
        
        return cleaned