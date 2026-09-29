# core/deep_analyzer.py 
# "Phase 2: 선정된 TOP 3 코인에 대한 심층 분석을 수행하여 최종 1개 코인을 선정하는 파일"

from typing import Dict, Any, List, Optional
from datetime import datetime
from data.upbit_client import UpbitClient
from data.indicators import TechnicalIndicators
from ai.gpt_client import get_gpt_client
from core.reflector import Reflector
import pandas as pd
import numpy as np
import json

class DeepAnalyzer:

    # "DeepAnalyzer 클래스를 초기화하고 필요한 클라이언트들을 생성하는 메서드" (인자: self)
    def __init__(self):
        self.upbit = UpbitClient()
        self.indicators = TechnicalIndicators()
        self.gpt = get_gpt_client()
        self.reflector = Reflector()
    
    # "TOP 3 후보 코인을 GPT-5 단일 추론으로 심층 분석하는 메서드" (인자: self, top_3_tickers)
    def analyze_candidates(self, top_3_tickers: List[str]) -> Dict[str, Any]:
        print(f"🔍 Phase 2: GPT-5 심층 분석 - {top_3_tickers}")

        # ========== memory 관련 부분 주석처리 시작 ==========
        # memory = self.reflector.get_recent_memory(limit=5)
        # has_memory = bool(memory.get('long_term', '').strip() or memory.get('short_term', '').strip())
        # 
        # if has_memory:
        #     print("🧠 과거 알트코인 거래 경험을 참고합니다")
        # else:
        #     print("순수 데이터 기반 심층 분석 모드")
        # ========== memory 관련 부분 주석처리 끝 ==========
        
        # memory 사용하지 않도록 설정
        memory = None
        has_memory = False
        print("순수 데이터 기반 심층 분석 모드")

        candidates_raw_data = {}
        
        for ticker in top_3_tickers:
            print(f"   📊 {ticker} 상세 데이터 수집 중...")
            raw_data = self._get_detailed_raw_data(ticker)
            
            if raw_data:
                candidates_raw_data[ticker] = raw_data
                print(f"   ✅ {ticker} 데이터 수집 완료")
            else:
                print(f"   ❌ {ticker} 데이터 수집 실패")
        
        if len(candidates_raw_data) < 2:
            return {
                "error": f"분석 가능한 후보가 {len(candidates_raw_data)}개뿐 (최소 2개 필요)",
                "available_candidates": list(candidates_raw_data.keys())
            }

        print("🤖 GPT-5 통합 다중 관점 분석 시작...")
        
        # ========== memory 파라미터 제거 ==========
        # 기존: memory if has_memory else None
        # 변경: None으로 고정
        final_decision = self.gpt.analyze_deep_phase2_unified(
            candidates_raw_data,
            None  # memory 파라미터를 항상 None으로 전달
        )
        
        if not final_decision or final_decision.get('error'):
            return {"error": f"GPT-5 분석 실패: {final_decision.get('error', '알 수 없는 오류')}"}

        self._display_analysis_result(final_decision, has_memory)
        
        return final_decision
    
    # "프랙탈 분석을 위한 과거 데이터 구조 요약 생성 메서드" (인자: self, df, interval)
    def _generate_historical_structure_summary(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        """과거 데이터에서 핵심 구조적 정보를 추출하여 토큰 효율적인 요약 생성"""
        try:
            if df is None or df.empty or len(df) < 20:
                return {}
            
            # 1. 주요 지지/저항 레벨 계산
            support_resistance = self._calculate_support_resistance_levels(df)
            
            # 2. 최근 N개 캔들의 추세 판단
            recent_trend = self._analyze_recent_trend(df, n=20)
            
            # 3. 지배적인 패턴 설명
            dominant_pattern = self._describe_dominant_pattern(df, interval)
            
            # 4. 프랙탈 차원 분석
            fractal_info = self._analyze_fractal_dimension(df)
            
            # 5. 거래량 구조 분석
            volume_structure = self._analyze_volume_structure(df)
            
            # 6. 패턴 유사성 분석 (과거 패턴과 현재 패턴 비교)
            pattern_similarity = self._analyze_pattern_similarity(df)
            
            summary = {
                "support_resistance": support_resistance,
                "recent_trend": recent_trend,
                "dominant_pattern": dominant_pattern,
                "fractal_info": fractal_info,
                "volume_structure": volume_structure,
                "pattern_similarity": pattern_similarity,
                "data_points": len(df),
                "interval": interval
            }
            
            return summary
            
        except Exception as e:
            print(f"   ⚠️ 과거 구조 요약 생성 오류 ({interval}): {e}")
            return {}
    
    # "지지/저항 레벨 계산 메서드" (인자: self, df)
    def _calculate_support_resistance_levels(self, df: pd.DataFrame) -> Dict[str, List[float]]:
        """피봇 포인트와 거래량 가중 방식으로 주요 지지/저항 레벨 식별"""
        try:
            # 최근 가격 범위
            recent_high = float(df['high'].tail(50).max())
            recent_low = float(df['low'].tail(50).min())
            
            # 거래량 가중 평균 가격 (VWAP)
            vwap = float((df['close'] * df['volume']).sum() / df['volume'].sum())
            
            # 피봇 레벨 계산
            pivot = (recent_high + recent_low + float(df['close'].iloc[-1])) / 3
            
            # 피봇 기반 저항선
            r1 = 2 * pivot - recent_low
            r2 = pivot + (recent_high - recent_low)
            r3 = r1 + (recent_high - recent_low)
            
            # 피봇 기반 지지선
            s1 = 2 * pivot - recent_high
            s2 = pivot - (recent_high - recent_low)
            s3 = s1 - (recent_high - recent_low)
            
            # 주요 저항선 (실제 가격 기반 + 피봇 기반 혼합)
            resistance_levels = []
            high_peaks = df['high'].nlargest(10)
            for price in high_peaks:
                if not any(abs(price - r) < price * 0.005 for r in resistance_levels):
                    resistance_levels.append(float(price))
                if len(resistance_levels) >= 3:
                    break
            
            # 피봇 저항선 추가 (중복 제거)
            for r in [r1, r2, r3]:
                if not any(abs(r - rl) < r * 0.005 for rl in resistance_levels):
                    resistance_levels.append(float(r))
            
            # 주요 지지선 (실제 가격 기반 + 피봇 기반 혼합)
            support_levels = []
            low_troughs = df['low'].nsmallest(10)
            for price in low_troughs:
                if not any(abs(price - s) < price * 0.005 for s in support_levels):
                    support_levels.append(float(price))
                if len(support_levels) >= 3:
                    break
            
            # 피봇 지지선 추가 (중복 제거)
            for s in [s1, s2, s3]:
                if not any(abs(s - sl) < s * 0.005 for sl in support_levels):
                    support_levels.append(float(s))
            
            return {
                "major_resistances": sorted(resistance_levels, reverse=True)[:3],
                "major_supports": sorted(support_levels)[:3],
                "pivot_level": float(pivot),
                "vwap": vwap,
                "current_position": "above_pivot" if float(df['close'].iloc[-1]) > pivot else "below_pivot"
            }
        except Exception as e:
            return {"major_resistances": [], "major_supports": [], "pivot_level": 0, "vwap": 0}
    
    # "최근 추세 분석 메서드" (인자: self, df, n)
    def _analyze_recent_trend(self, df: pd.DataFrame, n: int = 20) -> Dict[str, Any]:
        """최근 N개 캔들의 추세 방향과 강도 분석"""
        try:
            recent_df = df.tail(n)
            
            # 선형 회귀로 추세 방향 계산
            x = np.arange(len(recent_df))
            y = recent_df['close'].values
            z = np.polyfit(x, y, 1)
            slope = z[0]
            
            # 추세 강도 (R-squared)
            p = np.poly1d(z)
            yhat = p(x)
            ybar = np.sum(y) / len(y)
            ssreg = np.sum((yhat - ybar) ** 2)
            sstot = np.sum((y - ybar) ** 2)
            r_squared = ssreg / sstot if sstot != 0 else 0
            
            # 추세 판단
            avg_price = float(recent_df['close'].mean())
            slope_pct = (slope / avg_price) * 100
            
            # 추세 각도 계산
            trend_angle = np.degrees(np.arctan(slope_pct / 100))
            
            if slope_pct > 0.5:
                trend_direction = "STRONG_UP"
            elif slope_pct > 0.1:
                trend_direction = "UP"
            elif slope_pct < -0.5:
                trend_direction = "STRONG_DOWN"
            elif slope_pct < -0.1:
                trend_direction = "DOWN"
            else:
                trend_direction = "SIDEWAYS"
            
            # 변동성
            volatility = float(recent_df['close'].pct_change().std())
            
            return {
                "direction": trend_direction,
                "slope_percentage": float(slope_pct),
                "strength_r2": float(r_squared),
                "trend_angle_degrees": float(trend_angle),
                "volatility": volatility,
                "candles_analyzed": n
            }
        except Exception as e:
            return {"direction": "UNKNOWN", "slope_percentage": 0, "strength_r2": 0, "candles_analyzed": n}
    
    # "지배적 패턴 설명 생성 메서드" (인자: self, df, interval)
    def _describe_dominant_pattern(self, df: pd.DataFrame, interval: str) -> str:
        """과거 데이터의 지배적인 패턴을 간단한 텍스트로 설명"""
        try:
            # 변동성 분석
            volatility = float(df['close'].pct_change().std())
            
            # 추세 지속성
            up_days = len(df[df['close'] > df['open']])
            down_days = len(df[df['close'] < df['open']])
            trend_ratio = up_days / (up_days + down_days) if (up_days + down_days) > 0 else 0.5
            
            # 패턴 설명 생성
            if volatility > 0.05:
                vol_desc = "High volatility"
            elif volatility > 0.02:
                vol_desc = "Moderate volatility"
            else:
                vol_desc = "Low volatility"
            
            if trend_ratio > 0.6:
                trend_desc = "bullish bias"
            elif trend_ratio < 0.4:
                trend_desc = "bearish bias"
            else:
                trend_desc = "balanced"
            
            # 볼린저 밴드 수축/확장
            if len(df) >= 20:
                bb_std = df['close'].rolling(20).std()
                recent_bb_std = float(bb_std.iloc[-1])
                avg_bb_std = float(bb_std.mean())
                
                if recent_bb_std < avg_bb_std * 0.7:
                    bb_desc = "with Bollinger squeeze (condensation)"
                elif recent_bb_std > avg_bb_std * 1.3:
                    bb_desc = "with Bollinger expansion (breakout)"
                else:
                    bb_desc = "with normal bandwidth"
            else:
                bb_desc = ""
            
            # 채널 패턴 감지
            channel_pattern = self._detect_channel_pattern(df)
            
            pattern = f"{vol_desc}, {trend_desc} {bb_desc} {channel_pattern}".strip()
            return pattern
            
        except Exception as e:
            return "Pattern analysis unavailable"
    
    # "채널 패턴 감지 메서드" (인자: self, df)
    def _detect_channel_pattern(self, df: pd.DataFrame) -> str:
        """상승/하락 채널 또는 삼각형 패턴 감지"""
        try:
            if len(df) < 20:
                return ""
            
            highs = df['high'].tail(20)
            lows = df['low'].tail(20)
            
            # 고점과 저점의 추세선 계산
            x = np.arange(len(highs))
            high_slope = np.polyfit(x, highs.values, 1)[0]
            low_slope = np.polyfit(x, lows.values, 1)[0]
            
            avg_price = float(df['close'].mean())
            high_slope_pct = (high_slope / avg_price) * 100
            low_slope_pct = (low_slope / avg_price) * 100
            
            # 패턴 판단
            if abs(high_slope_pct - low_slope_pct) < 0.1:
                if high_slope_pct > 0.2:
                    return "in ascending channel"
                elif high_slope_pct < -0.2:
                    return "in descending channel"
                else:
                    return "in horizontal channel"
            elif high_slope_pct < 0 and low_slope_pct > 0:
                return "forming triangle convergence"
            elif high_slope_pct > 0 and low_slope_pct < 0:
                return "forming expanding triangle"
            
            return ""
            
        except Exception as e:
            return ""
    
    # "프랙탈 차원 분석 메서드" (인자: self, df)
    def _analyze_fractal_dimension(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Hurst Exponent와 프랙탈 차원으로 시장 특성 분석"""
        try:
            prices = df['close'].values
            
            # Hurst Exponent 계산 (R/S 분석)
            lags = range(2, min(20, len(prices) // 2))
            tau = []
            
            for lag in lags:
                price_diff = prices[lag:] - prices[:-lag]
                tau.append(np.sqrt(np.mean(price_diff ** 2)))
            
            if len(tau) > 0 and len(lags) > 0:
                # 로그-로그 회귀
                log_lags = np.log(list(lags))
                log_tau = np.log(tau)
                hurst = np.polyfit(log_lags, log_tau, 1)[0]
            else:
                hurst = 0.5
            
            # 프랙탈 차원 계산
            fractal_dimension = 2 - hurst
            
            # 해석
            if hurst > 0.6:
                market_type = "Trending (momentum)"
                trading_edge = "Follow trend"
            elif hurst < 0.4:
                market_type = "Mean-reverting"
                trading_edge = "Counter-trend"
            else:
                market_type = "Random walk"
                trading_edge = "No clear edge"
            
            return {
                "hurst_exponent": float(hurst),
                "fractal_dimension": float(fractal_dimension),
                "market_type": market_type,
                "trading_edge": trading_edge,
                "self_similarity": "High" if abs(hurst - 0.5) > 0.2 else "Low"
            }
        except Exception as e:
            return {
                "hurst_exponent": 0.5,
                "fractal_dimension": 1.5,
                "market_type": "Unknown",
                "trading_edge": "Unknown",
                "self_similarity": "Unknown"
            }
    
    # "거래량 구조 분석 메서드" (인자: self, df)
    def _analyze_volume_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """거래량 패턴과 구조 심층 분석"""
        try:
            recent_volume = float(df['volume'].tail(10).mean())
            historical_volume = float(df['volume'].mean())
            
            # 거래량 추세
            volume_trend = "increasing" if recent_volume > historical_volume * 1.2 else \
                          "decreasing" if recent_volume < historical_volume * 0.8 else "stable"
            
            # 거래량 스파이크 감지
            volume_std = float(df['volume'].std())
            volume_mean = float(df['volume'].mean())
            spike_threshold = volume_mean + (2 * volume_std)
            recent_spikes = len(df.tail(20)[df.tail(20)['volume'] > spike_threshold])
            
            # OBV (On-Balance Volume) 추세
            obv = (df['volume'] * ((df['close'] - df['close'].shift(1)) > 0).astype(int)).cumsum()
            obv_slope = np.polyfit(np.arange(len(obv.tail(20))), obv.tail(20).values, 1)[0]
            
            # 가격-거래량 상관관계
            price_volume_corr = float(df['close'].tail(20).corr(df['volume'].tail(20)))
            
            return {
                "recent_vs_historical_ratio": float(recent_volume / historical_volume) if historical_volume > 0 else 1.0,
                "trend": volume_trend,
                "recent_spikes_count": int(recent_spikes),
                "average_volume": historical_volume,
                "obv_trend": "accumulation" if obv_slope > 0 else "distribution",
                "price_volume_correlation": price_volume_corr
            }
        except Exception as e:
            return {
                "recent_vs_historical_ratio": 1.0,
                "trend": "unknown",
                "recent_spikes_count": 0,
                "average_volume": 0
            }
    
    # "패턴 유사성 분석 메서드" (인자: self, df)
    def _analyze_pattern_similarity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """과거 패턴과 현재 패턴의 유사성 비교 (프랙탈 분석의 핵심)"""
        try:
            if len(df) < 50:
                return {}
            
            # 현재 패턴 (최근 20개 캔들)
            current_pattern = df['close'].tail(20).values
            current_normalized = (current_pattern - current_pattern.mean()) / current_pattern.std()
            
            # 과거에서 유사한 패턴 찾기
            best_similarity = 0
            best_pattern_info = {}
            
            # 슬라이딩 윈도우로 과거 패턴 검색
            for i in range(20, len(df) - 20):
                past_pattern = df['close'].iloc[i:i+20].values
                past_normalized = (past_pattern - past_pattern.mean()) / past_pattern.std()
                
                # 코사인 유사도 계산
                similarity = np.dot(current_normalized, past_normalized) / (
                    np.linalg.norm(current_normalized) * np.linalg.norm(past_normalized)
                )
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    
                    # 해당 패턴 이후 가격 변화
                    future_return = (df['close'].iloc[i+20] - df['close'].iloc[i+19]) / df['close'].iloc[i+19]
                    
                    best_pattern_info = {
                        "similarity_score": float(similarity),
                        "pattern_date_index": i,
                        "future_return_after_pattern": float(future_return),
                        "pattern_outcome": "bullish" if future_return > 0.01 else "bearish" if future_return < -0.01 else "neutral"
                    }
            
            return best_pattern_info if best_similarity > 0.7 else {"similarity_score": 0, "pattern_outcome": "no_similar_pattern"}
            
        except Exception as e:
            return {"similarity_score": 0, "pattern_outcome": "analysis_failed"}
    
    # "개별 코인의 상세 원시 데이터를 수집하는 메서드" (인자: self, ticker)
    def _get_detailed_raw_data(self, ticker: str) -> Optional[Dict[str, Any]]:

        try:
            market_data = self.upbit.get_market_data(
                ticker, 
                ["minute5", "minute15", "minute60", "minute240", "day"]
            )

            current_price = self.upbit.get_current_price(ticker)
            if not current_price:
                return None

            raw_data = {
                "ticker": ticker,
                "current_price": float(current_price),
                "timestamp": datetime.now().isoformat()
            }

            for interval, data in market_data.items():
                if interval == "ticker" or not data:
                    continue
                
                df = pd.DataFrame(data)
                if df.empty:
                    continue
                
                # 순수 기술 지표
                indicators = self.indicators.calculate_indicators(df)
                
                # 프랙탈 분석을 위한 과거 구조 요약 추가
                historical_summary = self._generate_historical_structure_summary(df, interval)
                
                # 최근 캔들 데이터
                recent_candles = data[-20:] if len(data) >= 20 else data
                
                # 캔들 패턴 감지
                candle_patterns = self._detect_candle_patterns(df)
                
                # 거래량 프로파일
                volume_profile = self._calculate_volume_profile(df)
                
                raw_data[f"{interval}_analysis"] = {
                    "candles": recent_candles,
                    "indicators": indicators,
                    "historical_structure_summary": historical_summary,  # 추가된 부분
                    "patterns": candle_patterns,
                    "volume_profile": volume_profile
                }
            
            # 호가창 데이터
            try:
                orderbook = self._get_orderbook_data(ticker)
                if orderbook:
                    raw_data["orderbook"] = orderbook
            except:
                pass
            
            # 최근 체결 데이터
            try:
                recent_trades = self._get_recent_trades(ticker)
                if recent_trades:
                    raw_data["recent_trades"] = recent_trades
            except:
                pass

            return self._convert_numpy_types(raw_data)
            
        except Exception as e:
            print(f"Error getting raw data for {ticker}: {e}")
            return None
    
    # "캔들스틱 패턴을 감지하여 패턴 정보를 반환하는 메서드" (인자: self, df)
    def _detect_candle_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:

        patterns = []
        
        if len(df) < 3:
            return patterns
        
        try:
            # 최근 5개 캔들로 패턴 감지
            recent = df.tail(5)
            
            for i in range(len(recent) - 1, -1, -1):
                candle = recent.iloc[i]
                pattern_info = {
                    "index": i - len(recent),  # -5, -4, -3, -2, -1
                    "patterns": []
                }
                
                open_price = candle['open']
                close = candle['close']
                high = candle['high']
                low = candle['low']
                
                body = abs(close - open_price)
                full_range = high - low
                
                if full_range == 0:
                    continue
                
                # Doji
                if body / full_range < 0.1:
                    pattern_info["patterns"].append("doji")
                
                # Hammer / Hanging Man
                upper_shadow = high - max(open_price, close)
                lower_shadow = min(open_price, close) - low
                
                if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                    if close > open_price:
                        pattern_info["patterns"].append("hammer")
                    else:
                        pattern_info["patterns"].append("hanging_man")
                
                # Shooting Star / Inverted Hammer
                if upper_shadow > body * 2 and lower_shadow < body * 0.5:
                    if close < open_price:
                        pattern_info["patterns"].append("shooting_star")
                    else:
                        pattern_info["patterns"].append("inverted_hammer")
                
                # Engulfing patterns (2개 캔들 필요)
                if i > 0:
                    prev_candle = recent.iloc[i-1]
                    prev_body = abs(prev_candle['close'] - prev_candle['open'])
                    
                    # Bullish Engulfing
                    if (prev_candle['close'] < prev_candle['open'] and 
                        close > open_price and
                        open_price <= prev_candle['close'] and 
                        close >= prev_candle['open']):
                        pattern_info["patterns"].append("bullish_engulfing")
                    
                    # Bearish Engulfing
                    if (prev_candle['close'] > prev_candle['open'] and 
                        close < open_price and
                        open_price >= prev_candle['close'] and 
                        close <= prev_candle['open']):
                        pattern_info["patterns"].append("bearish_engulfing")
                
                if pattern_info["patterns"]:
                    patterns.append(pattern_info)
            
        except Exception as e:
            print(f"Pattern detection error: {e}")
        
        return patterns
    
    # "거래량 프로파일을 계산하여 원시 데이터로 반환하는 메서드" (인자: self, df)
    def _calculate_volume_profile(self, df: pd.DataFrame) -> Dict[str, Any]:

        profile = {}
        
        try:
            if len(df) < 5:
                return profile
            
            volumes = df['volume'].values
            prices = df['close'].values
            
            # 최근 거래량 vs 평균
            recent_vol = volumes[-3:].mean() if len(volumes) >= 3 else volumes[-1]
            avg_vol = volumes.mean()
            
            profile["recent_volume"] = float(recent_vol)
            profile["average_volume"] = float(avg_vol)
            profile["volume_ratio"] = float(recent_vol / avg_vol) if avg_vol > 0 else 1.0
            
            # 가격별 거래량 분포
            if len(df) >= 20:
                price_levels = np.percentile(prices, [20, 40, 60, 80])
                volume_distribution = []
                
                for i in range(len(price_levels) + 1):
                    if i == 0:
                        mask = prices <= price_levels[0]
                    elif i == len(price_levels):
                        mask = prices > price_levels[-1]
                    else:
                        mask = (prices > price_levels[i-1]) & (prices <= price_levels[i])
                    
                    level_volume = volumes[mask].sum() if mask.any() else 0
                    volume_distribution.append({
                        "level": i,
                        "volume": float(level_volume),
                        "percentage": float(level_volume / volumes.sum() * 100) if volumes.sum() > 0 else 0
                    })
                
                profile["distribution"] = volume_distribution
            
            # 거래량 추세
            if len(volumes) >= 10:
                recent_trend = volumes[-5:].mean()
                older_trend = volumes[-10:-5].mean()
                
                if older_trend > 0:
                    trend_ratio = (recent_trend - older_trend) / older_trend
                    profile["volume_trend"] = "increasing" if trend_ratio > 0.1 else "decreasing" if trend_ratio < -0.1 else "stable"
                    profile["trend_strength"] = float(abs(trend_ratio))
            
        except Exception as e:
            print(f"Volume profile error: {e}")
        
        return profile
    
    # "호가창 데이터를 수집하는 선택적 메서드" (인자: self, ticker)
    def _get_orderbook_data(self, ticker: str) -> Optional[Dict[str, Any]]:

        try:

            if hasattr(self.upbit, 'get_orderbook'):
                orderbook = self.upbit.get_orderbook(ticker)
                
                if orderbook:
                    return {
                        "bid_ask_spread": float(orderbook.get('ask_price', 0) - orderbook.get('bid_price', 0)),
                        "bid_volume": float(orderbook.get('total_bid_volume', 0)),
                        "ask_volume": float(orderbook.get('total_ask_volume', 0)),
                        "bid_ask_ratio": float(orderbook.get('bid_volume', 0) / max(orderbook.get('ask_volume', 1), 1)),
                        "timestamp": orderbook.get('timestamp', datetime.now().isoformat())
                    }
        except:
            pass
        
        return None
    
    # "최근 체결 데이터를 수집하는 선택적 메서드" (인자: self, ticker, limit)
    def _get_recent_trades(self, ticker: str, limit: int = 20) -> Optional[List[Dict]]:

        try:
            if hasattr(self.upbit, 'get_recent_trades'):
                trades = self.upbit.get_recent_trades(ticker, limit)
                
                if trades:
                    buy_volume = sum(t['volume'] for t in trades if t.get('ask_bid') == 'BID')
                    sell_volume = sum(t['volume'] for t in trades if t.get('ask_bid') == 'ASK')
                    
                    return {
                        "trade_count": len(trades),
                        "buy_volume": float(buy_volume),
                        "sell_volume": float(sell_volume),
                        "buy_sell_ratio": float(buy_volume / max(sell_volume, 1)),
                        "avg_trade_size": float(sum(t['volume'] for t in trades) / len(trades))
                    }
        except:
            pass
        
        return None
    
    # "numpy 타입을 Python 기본 타입으로 재귀적으로 변환하는 메서드" (인자: self, obj)
    def _convert_numpy_types(self, obj):
        if isinstance(obj, dict):
            return {key: self._convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
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
    
    # "GPT-5 분석 결과를 포맷팅하여 출력하는 메서드" (인자: self, result, has_memory)
    def _display_analysis_result(self, result: Dict[str, Any], has_memory: bool):

        action = result.get('action', 'wait')
        final_selection = result.get('final_selection', {})
        
        selected_coin = final_selection.get('selected_coin', '')
        confidence = final_selection.get('confidence_score', 0)
        reasoning = final_selection.get('selection_rationale', '')
        
        print(f"\n🎯 GPT-5 통합 분석 결과:")
        print(f"   💰 선정 코인: {selected_coin if selected_coin else 'None'}")
        print(f"   📊 신뢰도: {confidence:.0f}/100")
        print(f"   🎬 결정: {action.upper()}")
        
        if action == 'wait':
            wait_reason = final_selection.get('wait_reason', '더 좋은 기회 대기')
            print(f"   ⏸️  대기 사유: {wait_reason}")
            print(f"   🔄 30분 후 Phase 1부터 재시작 권장")
        else:
            # 주요 분석 포인트
            perspectives = result.get('multi_perspective_analysis', {})
            if perspectives:
                print(f"\n📊 다중 관점 분석 요약:")
                
                # 각 관점별 점수
                for perspective, analysis in perspectives.items():
                    if isinstance(analysis, dict):
                        score = analysis.get('score', 0)
                        insight = analysis.get('key_insight', '')
                        print(f"   • {perspective}: {score}/100")
                        if insight:
                            print(f"     → {insight[:80]}...")
            
            # 프랙탈 분석 결과 표시 (추가)
            fractal_analysis = final_selection.get('fractal_analysis', {})
            if fractal_analysis:
                print(f"\n🔬 프랙탈 분석:")
                similarity = fractal_analysis.get('pattern_similarity', 0)
                if similarity > 0.7:
                    print(f"   • 과거 유사 패턴 발견 (유사도: {similarity:.1%})")
                    outcome = fractal_analysis.get('historical_outcome', '')
                    if outcome:
                        print(f"   • 과거 패턴 결과: {outcome}")
            
            # 선정 근거
            if reasoning:
                print(f"\n💡 선정 근거:")
                print(f"   {reasoning[:200]}...")
            
            # 메모리 활용 여부
            if has_memory:
                memory_influence = final_selection.get('memory_influence', '')
                if memory_influence:
                    print(f"\n🧠 경험 활용:")
                    print(f"   {memory_influence[:150]}...")
        
        # 리스크 정보
        risk_factors = final_selection.get('risk_factors', [])
        if risk_factors:
            print(f"\n⚠️  주요 리스크:")
            for risk in risk_factors[:3]:
                print(f"   • {risk}")
        
        print(f"\n" + "="*70)