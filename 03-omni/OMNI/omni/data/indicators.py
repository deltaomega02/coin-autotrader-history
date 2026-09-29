# data/indicators.py
# "순수 기술적 지표 40개+ 제공 - AI 자율 판단용 (점수 계산 없음)"

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
import warnings
import logging

warnings.filterwarnings('ignore', category=RuntimeWarning)

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

class TechnicalIndicators:

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> Dict[str, Any]:
        """
        모든 기술적 지표를 계산하여 순수 데이터만 반환
        점수 계산 없음 - AI가 직접 판단
        """
        if df is None or df.empty or len(df) < 2:
            logger.warning("DataFrame is empty or too small")
            return {}
        
        df = df.copy()
        
        # DatetimeIndex 설정
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            else:
                df.index = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq='h')
        
        df = df.sort_index()
        
        # 숫자 타입 변환
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df = df.ffill().bfill()
        
        indicators = {}
        failed_indicators = []
        
        # 기본 가격 정보
        latest = df.iloc[-1]
        indicators['close'] = float(latest['close']) if pd.notna(latest['close']) else 0
        indicators['volume'] = float(latest['volume']) if pd.notna(latest['volume']) else 0
        
        # 1. TREND INDICATORS (추세 지표)
        trend_result, trend_failures = TechnicalIndicators._calculate_trend_indicators(df)
        indicators.update(trend_result)
        failed_indicators.extend(trend_failures)
        
        # 2. MOMENTUM INDICATORS (모멘텀 지표)
        momentum_result, momentum_failures = TechnicalIndicators._calculate_momentum_indicators(df)
        indicators.update(momentum_result)
        failed_indicators.extend(momentum_failures)
        
        # 3. VOLATILITY INDICATORS (변동성 지표)
        volatility_result, volatility_failures = TechnicalIndicators._calculate_volatility_indicators(df)
        indicators.update(volatility_result)
        failed_indicators.extend(volatility_failures)
        
        # 4. VOLUME INDICATORS (거래량 지표)
        volume_result, volume_failures = TechnicalIndicators._calculate_volume_indicators(df)
        indicators.update(volume_result)
        failed_indicators.extend(volume_failures)
        
        # 5. DIVERGENCE DETECTION (다이버전스 감지)
        indicators['divergences'] = TechnicalIndicators._detect_divergences(df, indicators)
        
        # 6. KEY LEVELS (주요 가격 레벨) - 새로 추가!
        indicators['key_levels'] = TechnicalIndicators.calculate_key_levels(df)
        
        # 7. 추가 파생 지표들 (AI 판단용 원시 데이터)
        indicators['price_momentum'] = {
            'change_1h': ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100) if len(df) >= 2 else 0,
            'change_4h': ((df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100) if len(df) >= 5 else 0,
            'change_24h': ((df['close'].iloc[-1] - df['close'].iloc[-25]) / df['close'].iloc[-25] * 100) if len(df) >= 25 else 0,
        }
        
        # 실패한 지표 로깅
        if failed_indicators:
            logger.warning(f"Failed indicators: {', '.join(failed_indicators)}")
            indicators['_failed_indicators'] = failed_indicators
        
        return TechnicalIndicators._clean_indicators(indicators)
    
    @staticmethod
    def calculate_key_levels(df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
        """
        주요 가격 레벨 계산 (고점, 저점, 피봇 등)
        """
        if df.empty or len(df) < window:
            return {
                'recent_high': 0,
                'recent_low': 0,
                'price_position': 50.0,
                'pivot': 0,
                'resistance1': 0,
                'support1': 0
            }
        
        try:
            # 최근 N개 봉에서 실제 고점/저점
            recent_high = float(df['high'].tail(window).max())
            recent_low = float(df['low'].tail(window).min())
            
            # 현재가
            current_price = float(df['close'].iloc[-1])
            
            # 현재가 위치 (0-100%)
            if recent_high > recent_low:
                price_position = ((current_price - recent_low) / (recent_high - recent_low)) * 100
            else:
                price_position = 50.0
            
            # 피봇 포인트 계산 (전일 기준)
            last = df.iloc[-1]
            pivot = float((last['high'] + last['low'] + last['close']) / 3)
            
            # 저항선/지지선
            resistance1 = float(2 * pivot - last['low'])
            support1 = float(2 * pivot - last['high'])
            resistance2 = float(pivot + (last['high'] - last['low']))
            support2 = float(pivot - (last['high'] - last['low']))
            
            # VWAP (볼륨 가중 평균가)
            vwap = float((df['close'] * df['volume']).tail(window).sum() / df['volume'].tail(window).sum())
            
            return {
                'recent_high': recent_high,
                'recent_low': recent_low,
                'current_price': current_price,
                'price_position': price_position,
                'pivot': pivot,
                'resistance1': resistance1,
                'resistance2': resistance2,
                'support1': support1,
                'support2': support2,
                'vwap': vwap,
                'range': recent_high - recent_low,
                'range_pct': ((recent_high - recent_low) / current_price * 100) if current_price > 0 else 0
            }
            
        except Exception as e:
            logger.warning(f"Key levels calculation error: {e}")
            return {
                'recent_high': float(df['high'].iloc[-1]) if not df.empty else 0,
                'recent_low': float(df['low'].iloc[-1]) if not df.empty else 0,
                'price_position': 50.0,
                'pivot': float(df['close'].iloc[-1]) if not df.empty else 0
            }
    
    @staticmethod
    def _calculate_trend_indicators(df: pd.DataFrame) -> Tuple[Dict[str, Any], List[str]]:
        result = {}
        failed = []
        data_len = len(df)
        
        # ADX/DMI
        if data_len >= 14:
            try:
                adx = ta.adx(df['high'], df['low'], df['close'], length=14)
                if adx is not None and not adx.empty:
                    result['adx'] = float(adx['ADX_14'].iloc[-1]) if 'ADX_14' in adx.columns else 0
                    result['dmp'] = float(adx['DMP_14'].iloc[-1]) if 'DMP_14' in adx.columns else 0
                    result['dmn'] = float(adx['DMN_14'].iloc[-1]) if 'DMN_14' in adx.columns else 0
            except Exception as e:
                logger.debug(f"ADX failed: {e}")
                failed.append('ADX')
        
        # SMA
        for period in [5, 10, 20, 50, 100, 200]:
            if data_len >= period:
                try:
                    sma = ta.sma(df['close'], length=period)
                    if sma is not None and not sma.empty:
                        result[f'sma_{period}'] = float(sma.iloc[-1]) if pd.notna(sma.iloc[-1]) else 0
                except:
                    failed.append(f'SMA_{period}')
        
        # EMA
        for period in [9, 21, 50, 100, 200]:
            if data_len >= period:
                try:
                    ema = ta.ema(df['close'], length=period)
                    if ema is not None and not ema.empty:
                        result[f'ema_{period}'] = float(ema.iloc[-1]) if pd.notna(ema.iloc[-1]) else 0
                except:
                    failed.append(f'EMA_{period}')
        
        # HMA, WMA
        if data_len >= 20:
            try:
                hma = ta.hma(df['close'], length=20)
                if hma is not None and not hma.empty:
                    result['hma_20'] = float(hma.iloc[-1]) if pd.notna(hma.iloc[-1]) else 0
            except:
                failed.append('HMA')
            
            try:
                wma = ta.wma(df['close'], length=20)
                if wma is not None and not wma.empty:
                    result['wma_20'] = float(wma.iloc[-1]) if pd.notna(wma.iloc[-1]) else 0
            except:
                failed.append('WMA')
        
        # Supertrend
        if data_len >= 14:
            try:
                supertrend = ta.supertrend(df['high'], df['low'], df['close'])
                if supertrend is not None and not supertrend.empty:
                    for col in supertrend.columns:
                        if 'SUPERT' in col:
                            value = supertrend[col].iloc[-1]
                            result['supertrend'] = float(value) if pd.notna(value) else 0
                            break
            except:
                failed.append('Supertrend')
        
        # PSAR
        if data_len >= 2:
            try:
                psar = ta.psar(df['high'], df['low'])
                if psar is not None and not psar.empty:
                    for col in psar.columns:
                        if 'PSARl' in col or 'PSARs' in col:
                            value = psar[col].iloc[-1]
                            if pd.notna(value):
                                result['psar'] = float(value)
                                result['psar_trend'] = 'BULL' if result['psar'] < df['close'].iloc[-1] else 'BEAR'
                                break
            except:
                failed.append('PSAR')
        
        return result, failed
    
    @staticmethod
    def _calculate_momentum_indicators(df: pd.DataFrame) -> Tuple[Dict[str, Any], List[str]]:
        result = {}
        failed = []
        data_len = len(df)
        
        # RSI
        for period in [9, 14, 21]:
            if data_len >= period:
                try:
                    rsi = ta.rsi(df['close'], length=period)
                    if rsi is not None and not rsi.empty:
                        value = rsi.iloc[-1]
                        result[f'rsi_{period}'] = float(value) if pd.notna(value) else 50.0
                except:
                    result[f'rsi_{period}'] = 50.0
                    failed.append(f'RSI_{period}')
        
        # Stochastic RSI
        if data_len >= 14:
            try:
                stochrsi = ta.stochrsi(df['close'])
                if stochrsi is not None and not stochrsi.empty:
                    for col in stochrsi.columns:
                        if 'STOCHRSIk' in col:
                            value = stochrsi[col].iloc[-1]
                            result['stochrsi_k'] = float(value) if pd.notna(value) else 50.0
                        elif 'STOCHRSId' in col:
                            value = stochrsi[col].iloc[-1]
                            result['stochrsi_d'] = float(value) if pd.notna(value) else 50.0
            except:
                failed.append('StochRSI')
        
        # MACD
        if data_len >= 26:
            try:
                macd = ta.macd(df['close'])
                if macd is not None and not macd.empty:
                    for col in macd.columns:
                        if 'MACD_' in col and 'h' not in col and 's' not in col:
                            value = macd[col].iloc[-1]
                            result['macd'] = float(value) if pd.notna(value) else 0
                        elif 'MACDs_' in col:
                            value = macd[col].iloc[-1]
                            result['macd_signal'] = float(value) if pd.notna(value) else 0
                        elif 'MACDh_' in col:
                            value = macd[col].iloc[-1]
                            result['macd_histogram'] = float(value) if pd.notna(value) else 0
            except:
                failed.append('MACD')
        
        # Stochastic
        if data_len >= 14:
            try:
                stoch = ta.stoch(df['high'], df['low'], df['close'])
                if stoch is not None and not stoch.empty:
                    for col in stoch.columns:
                        if 'STOCHk' in col:
                            value = stoch[col].iloc[-1]
                            result['stoch_k'] = float(value) if pd.notna(value) else 50.0
                        elif 'STOCHd' in col:
                            value = stoch[col].iloc[-1]
                            result['stoch_d'] = float(value) if pd.notna(value) else 50.0
            except:
                failed.append('Stochastic')
        
        # CCI
        if data_len >= 20:
            try:
                cci = ta.cci(df['high'], df['low'], df['close'], length=20)
                if cci is not None and not cci.empty:
                    value = cci.iloc[-1]
                    result['cci'] = float(value) if pd.notna(value) else 0
            except:
                failed.append('CCI')
        
        # Williams %R
        if data_len >= 14:
            try:
                willr = ta.willr(df['high'], df['low'], df['close'])
                if willr is not None and not willr.empty:
                    value = willr.iloc[-1]
                    result['williams_r'] = float(value) if pd.notna(value) else -50.0
            except:
                failed.append('Williams_%R')
        
        # ROC
        if data_len >= 10:
            try:
                roc = ta.roc(df['close'], length=10)
                if roc is not None and not roc.empty:
                    value = roc.iloc[-1]
                    result['roc'] = float(value) if pd.notna(value) else 0
            except:
                failed.append('ROC')
        
        return result, failed
    
    @staticmethod
    def _calculate_volatility_indicators(df: pd.DataFrame) -> Tuple[Dict[str, Any], List[str]]:
        result = {}
        failed = []
        data_len = len(df)
        
        # Bollinger Bands
        if data_len >= 20:
            for std in [1.5, 2.0, 2.5, 3.0]:
                try:
                    bb = ta.bbands(df['close'], length=20, std=std)
                    if bb is not None and not bb.empty:
                        for col in bb.columns:
                            if 'BBU' in col or 'UPPER' in col:
                                value = bb[col].iloc[-1]
                                result[f'bb_upper_{std}'] = float(value) if pd.notna(value) else 0
                            elif 'BBM' in col or 'MID' in col:
                                value = bb[col].iloc[-1]
                                result[f'bb_middle_{std}'] = float(value) if pd.notna(value) else 0
                            elif 'BBL' in col or 'LOWER' in col:
                                value = bb[col].iloc[-1]
                                result[f'bb_lower_{std}'] = float(value) if pd.notna(value) else 0
                except:
                    failed.append(f'BB_{std}')
            
            # BB Position
            if 'bb_upper_2.0' in result and 'bb_lower_2.0' in result:
                try:
                    current = df['close'].iloc[-1]
                    upper = result['bb_upper_2.0']
                    lower = result['bb_lower_2.0']
                    if upper > lower:
                        result['bb_position'] = (current - lower) / (upper - lower) * 100
                    result['bb_width'] = (upper - lower) / current * 100 if current > 0 else 0
                except:
                    pass
        
        # ATR
        for period in [7, 14, 21]:
            if data_len >= period:
                try:
                    atr = ta.atr(df['high'], df['low'], df['close'], length=period)
                    if atr is not None and not atr.empty:
                        value = atr.iloc[-1]
                        if pd.notna(value):
                            result[f'atr_{period}'] = float(value)
                            close_price = df['close'].iloc[-1]
                            result[f'atr_{period}_pct'] = float(value / close_price * 100) if close_price > 0 else 0
                except:
                    failed.append(f'ATR_{period}')
        
        # Keltner Channels
        if data_len >= 20:
            try:
                kc = ta.kc(df['high'], df['low'], df['close'])
                if kc is not None and not kc.empty:
                    for col in kc.columns:
                        if 'KCU' in col:
                            value = kc[col].iloc[-1]
                            result['kc_upper'] = float(value) if pd.notna(value) else 0
                        elif 'KCB' in col:
                            value = kc[col].iloc[-1]
                            result['kc_middle'] = float(value) if pd.notna(value) else 0
                        elif 'KCL' in col:
                            value = kc[col].iloc[-1]
                            result['kc_lower'] = float(value) if pd.notna(value) else 0
            except:
                failed.append('KC')
        
        # Donchian Channels
        if data_len >= 20:
            try:
                dc = ta.donchian(df['high'], df['low'])
                if dc is not None and not dc.empty:
                    for col in dc.columns:
                        if 'DCU' in col:
                            value = dc[col].iloc[-1]
                            result['dc_upper'] = float(value) if pd.notna(value) else 0
                        elif 'DCM' in col:
                            value = dc[col].iloc[-1]
                            result['dc_middle'] = float(value) if pd.notna(value) else 0
                        elif 'DCL' in col:
                            value = dc[col].iloc[-1]
                            result['dc_lower'] = float(value) if pd.notna(value) else 0
            except:
                failed.append('DC')
        
        return result, failed
    
    @staticmethod
    def _calculate_volume_indicators(df: pd.DataFrame) -> Tuple[Dict[str, Any], List[str]]:
        result = {}
        failed = []
        data_len = len(df)
        
        # OBV
        if data_len >= 2:
            try:
                obv = ta.obv(df['close'], df['volume'])
                if obv is not None and not obv.empty:
                    value = obv.iloc[-1]
                    result['obv'] = float(value) if pd.notna(value) else 0
                    
                    if len(obv) >= 20:
                        obv_slope = (obv.iloc[-1] - obv.iloc[-20]) / 20
                        result['obv_slope'] = float(obv_slope) if pd.notna(obv_slope) else 0
                        result['obv_trend'] = 'UP' if obv_slope > 0 else 'DOWN'
            except:
                failed.append('OBV')
        
        # VWAP
        if data_len >= 1 and isinstance(df.index, pd.DatetimeIndex):
            try:
                vwap = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
                if vwap is not None and not vwap.empty:
                    value = vwap.iloc[-1]
                    if pd.notna(value):
                        result['vwap'] = float(value)
                        close_price = df['close'].iloc[-1]
                        result['price_to_vwap'] = close_price / result['vwap'] if result['vwap'] > 0 else 1.0
                    else:
                        result['vwap'] = float(df['close'].iloc[-1])
                        result['price_to_vwap'] = 1.0
            except:
                result['vwap'] = float(df['close'].iloc[-1])
                result['price_to_vwap'] = 1.0
        
        # MFI
        if data_len >= 14:
            try:
                mfi = ta.mfi(df['high'], df['low'], df['close'], df['volume'])
                if mfi is not None and not mfi.empty:
                    value = mfi.iloc[-1]
                    result['mfi'] = float(value) if pd.notna(value) else 50.0
            except:
                result['mfi'] = 50.0
        
        # CMF
        if data_len >= 20:
            try:
                cmf = ta.cmf(df['high'], df['low'], df['close'], df['volume'])
                if cmf is not None and not cmf.empty:
                    value = cmf.iloc[-1]
                    result['cmf'] = float(value) if pd.notna(value) else 0
            except:
                failed.append('CMF')
        
        # A/D Line
        if data_len >= 2:
            try:
                ad = ta.ad(df['high'], df['low'], df['close'], df['volume'])
                if ad is not None and not ad.empty:
                    value = ad.iloc[-1]
                    result['ad_line'] = float(value) if pd.notna(value) else 0
                    
                    if len(ad) >= 20:
                        ad_slope = (ad.iloc[-1] - ad.iloc[-20]) / 20
                        result['ad_slope'] = float(ad_slope) if pd.notna(ad_slope) else 0
            except:
                failed.append('AD_Line')
        
        # Volume Profile
        if data_len >= 20:
            try:
                vol_mean_20 = df['volume'].rolling(20).mean().iloc[-1]
                if pd.notna(vol_mean_20) and vol_mean_20 > 0:
                    result['volume_ratio'] = df['volume'].iloc[-1] / vol_mean_20
                else:
                    result['volume_ratio'] = 1.0
                result['volume_mean_20'] = float(vol_mean_20) if pd.notna(vol_mean_20) else 0
            except:
                failed.append('Volume_Profile')
        
        return result, failed
    
    @staticmethod
    def _detect_divergences(df: pd.DataFrame, indicators: Dict) -> Dict[str, Any]:
        """다이버전스 감지 - 순수 데이터만"""
        divergences = {
            'rsi_divergence': None,
            'macd_divergence': None,
            'obv_divergence': None,
            'divergence_data': {}  # AI 판단용 원시 데이터
        }
        
        if len(df) < 50:
            return divergences
        
        try:
            # 최근 고점/저점 찾기
            recent_high_idx = df['high'].rolling(20).max() == df['high']
            recent_low_idx = df['low'].rolling(20).min() == df['low']
            
            # RSI Divergence
            if 'rsi_14' in indicators:
                rsi = ta.rsi(df['close'], length=14)
                if rsi is not None and len(rsi) >= 50:
                    price_lows = df.loc[recent_low_idx, 'low'].tail(2)
                    if len(price_lows) == 2:
                        rsi_at_lows = rsi[price_lows.index]
                        if len(rsi_at_lows) == 2:
                            if price_lows.iloc[1] < price_lows.iloc[0] and rsi_at_lows.iloc[1] > rsi_at_lows.iloc[0]:
                                divergences['rsi_divergence'] = 'BULLISH'
                            
                            # 원시 데이터 저장
                            divergences['divergence_data']['rsi_price_lows'] = [float(price_lows.iloc[0]), float(price_lows.iloc[1])]
                            divergences['divergence_data']['rsi_at_lows'] = [float(rsi_at_lows.iloc[0]), float(rsi_at_lows.iloc[1])]
                    
                    price_highs = df.loc[recent_high_idx, 'high'].tail(2)
                    if len(price_highs) == 2:
                        rsi_at_highs = rsi[price_highs.index]
                        if len(rsi_at_highs) == 2:
                            if price_highs.iloc[1] > price_highs.iloc[0] and rsi_at_highs.iloc[1] < rsi_at_highs.iloc[0]:
                                divergences['rsi_divergence'] = 'BEARISH'
                            
                            divergences['divergence_data']['rsi_price_highs'] = [float(price_highs.iloc[0]), float(price_highs.iloc[1])]
                            divergences['divergence_data']['rsi_at_highs'] = [float(rsi_at_highs.iloc[0]), float(rsi_at_highs.iloc[1])]
            
            # OBV Divergence
            if 'obv' in indicators and 'obv_slope' in indicators:
                obv_trend = indicators.get('obv_trend', 'NEUTRAL')
                if len(df) >= 20:
                    price_change = df['close'].iloc[-1] - df['close'].iloc[-20]
                    divergences['divergence_data']['obv_price_change'] = float(price_change)
                    divergences['divergence_data']['obv_trend'] = obv_trend
                    
                    if obv_trend == 'UP' and price_change < 0:
                        divergences['obv_divergence'] = 'BULLISH'
                    elif obv_trend == 'DOWN' and price_change > 0:
                        divergences['obv_divergence'] = 'BEARISH'
                    
        except Exception as e:
            logger.debug(f"Divergence detection error: {e}")
        
        return divergences
    
    @staticmethod
    def _clean_indicators(indicators: Dict[str, Any]) -> Dict[str, Any]:
        """NaN과 Inf 제거"""
        cleaned = {}
        
        for key, value in indicators.items():
            if isinstance(value, dict):
                cleaned[key] = TechnicalIndicators._clean_indicators(value)
            elif isinstance(value, (int, float)):
                if pd.isna(value) or np.isinf(value):
                    if 'rsi' in key:
                        cleaned[key] = 50.0
                    elif 'ratio' in key:
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
    
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> Dict[str, Any]:
        """호환성 래퍼"""
        return TechnicalIndicators.calculate_all_indicators(df)