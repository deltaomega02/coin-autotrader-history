# core/market_analyzer.py
# "Phase 1: 시장 상황을 진단하고 거래 후보 TOP 3를 선정하는 시장 분석 파일"

import pandas as pd
import numpy as np
import json
from typing import Dict, Any, Optional, List
from datetime import datetime  
from data.upbit_client import UpbitClient
from data.indicators import TechnicalIndicators
from core.reflector import Reflector
from config.settings import settings  
from ai.gpt_client import get_gpt_client

class MarketAnalyzer:
    
    # "MarketAnalyzer 클래스를 초기화하고 필요한 클라이언트들을 생성하는 메서드" (인자: self)
    def __init__(self):
        self.upbit = UpbitClient()
        self.indicators = TechnicalIndicators()
        self.gpt = get_gpt_client()
        self.reflector = Reflector()
    
    # "시장 상황을 종합 분석하고 거래 진행 여부를 결정하는 메서드" (인자: self)
    def analyze_market_condition(self) -> Dict[str, Any]:
        print("📊 Phase 1: 시장 데이터 수집 시작...")
        
        # ========== memory 관련 부분 주석처리 시작 ==========
        # # 1. 과거 학습 경험 로드
        # memory = self.reflector.get_recent_memory(limit=5)
        # has_memory = bool(memory.get('long_term', '').strip() or memory.get('short_term', '').strip())
        # 
        # if has_memory:
        #     print("🧠 과거 거래 경험을 참고합니다")
        # else:
        #     print("순수 데이터 기반 분석 모드")
        # ========== memory 관련 부분 주석처리 끝 ==========
        
        # memory 사용하지 않도록 설정
        memory = None
        has_memory = False
        print("순수 데이터 기반 분석 모드")
        
        # 2. BTC 원시 데이터 수집
        btc_data = self._get_btc_raw_data()
        
        # 3. 알트코인 원시 데이터 수집 (상위 10개로 축소)
        altcoin_data = self._get_altcoin_raw_data()
        
        if not altcoin_data:
            return {
                "action": "wait", 
                "reason": "알트코인 데이터 수집 실패", 
                "duration_hours": 1,
                "confidence_level": 0
            }
        
        # 4. 시장 데이터 구성
        market_data = {
            "btc_data": btc_data,
            "altcoin_count": len(altcoin_data),
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"   📈 BTC: {btc_data.get('current_price', 0):,.0f}원")
        print(f"   🎯 수집된 알트코인: {len(altcoin_data)}개")
        
        # 5. GPT에 원시 데이터 전달
        print("🤖 GPT 시장 분석 중...")
        
        # ========== memory 파라미터 제거 ==========
        # 기존: memory if has_memory else None
        # 변경: None으로 고정
        gpt_result = self.gpt.analyze_market_phase1(
            market_data, 
            altcoin_data, 
            None  # memory 파라미터를 항상 None으로 전달
        )
        
        if gpt_result.get('error'):
            print(f"❌ GPT 분석 실패: {gpt_result['error']}")
            return {
                "action": "wait",
                "reason": f"AI 분석 실패: {gpt_result['error']}",
                "duration_hours": 2,
                "confidence_level": 0
            }
        
        # 6. 결과 해석
        self._interpret_altcoin_result(gpt_result, has_memory)
        
        return gpt_result

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
            
            # 4. 프랙탈 차원 분석 (간단한 버전)
            fractal_info = self._analyze_fractal_dimension(df)
            
            # 5. 거래량 구조 분석
            volume_structure = self._analyze_volume_structure(df)
            
            summary = {
                "support_resistance": support_resistance,
                "recent_trend": recent_trend,
                "dominant_pattern": dominant_pattern,
                "fractal_info": fractal_info,
                "volume_structure": volume_structure,
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
            
            # 주요 저항선 (상위 3개)
            resistance_levels = []
            high_peaks = df['high'].nlargest(10)
            for price in high_peaks:
                if not any(abs(price - r) < price * 0.005 for r in resistance_levels):
                    resistance_levels.append(float(price))
                if len(resistance_levels) >= 3:
                    break
            
            # 주요 지지선 (하위 3개)
            support_levels = []
            low_troughs = df['low'].nsmallest(10)
            for price in low_troughs:
                if not any(abs(price - s) < price * 0.005 for s in support_levels):
                    support_levels.append(float(price))
                if len(support_levels) >= 3:
                    break
            
            return {
                "major_resistances": sorted(resistance_levels, reverse=True)[:3],
                "major_supports": sorted(support_levels)[:3],
                "pivot_level": float(pivot),
                "vwap": vwap
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
            
            return {
                "direction": trend_direction,
                "slope_percentage": float(slope_pct),
                "strength_r2": float(r_squared),
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
                    bb_desc = "with Bollinger squeeze"
                elif recent_bb_std > avg_bb_std * 1.3:
                    bb_desc = "with Bollinger expansion"
                else:
                    bb_desc = ""
            else:
                bb_desc = ""
            
            pattern = f"{vol_desc}, {trend_desc} {bb_desc}".strip()
            return pattern
            
        except Exception as e:
            return "Pattern analysis unavailable"
    
    # "프랙탈 차원 분석 메서드" (인자: self, df)
    def _analyze_fractal_dimension(self, df: pd.DataFrame) -> Dict[str, Any]:
        """간단한 프랙탈 차원 분석으로 자기유사성 측정"""
        try:
            prices = df['close'].values
            
            # Hurst Exponent 계산 (간단한 버전)
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
            
            # 해석
            if hurst > 0.6:
                interpretation = "Trending (momentum)"
            elif hurst < 0.4:
                interpretation = "Mean-reverting"
            else:
                interpretation = "Random walk"
            
            return {
                "hurst_exponent": float(hurst),
                "interpretation": interpretation,
                "self_similarity": "High" if abs(hurst - 0.5) > 0.2 else "Low"
            }
        except Exception as e:
            return {"hurst_exponent": 0.5, "interpretation": "Unknown", "self_similarity": "Unknown"}
    
    # "거래량 구조 분석 메서드" (인자: self, df)
    def _analyze_volume_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """거래량 패턴과 구조 분석"""
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
            
            return {
                "recent_vs_historical_ratio": float(recent_volume / historical_volume) if historical_volume > 0 else 1.0,
                "trend": volume_trend,
                "recent_spikes_count": int(recent_spikes),
                "average_volume": historical_volume
            }
        except Exception as e:
            return {"recent_vs_historical_ratio": 1.0, "trend": "unknown", "recent_spikes_count": 0, "average_volume": 0}

    # "BTC의 원시 OHLCV 데이터와 기술 지표를 수집하는 메서드" (인자: self)
    def _get_btc_raw_data(self) -> Dict[str, Any]:
        try:
            print("   🔍 BTC 데이터 수집...")
            
            btc_ticker = "KRW-BTC"

            current_price = self.upbit.get_current_price(btc_ticker)
            
            market_data = self.upbit.get_market_data(
                btc_ticker, 
                ["minute15", "minute60", "minute240", "day"]  # 15분, 1시간, 4시간, 일봉
            )
            
            btc_data = {
                "ticker": btc_ticker,
                "current_price": current_price,
                "timestamp": datetime.now().isoformat()
            }
            
            # 각 시간대별 원시 데이터와 지표
            for interval, data in market_data.items():
                if interval == "ticker":
                    continue
                    
                if data and isinstance(data, list) and len(data) > 0:
                    try:
                        df = pd.DataFrame(data)
                        indicators = self.indicators.calculate_indicators(df)
                        
                        # 프랙탈 분석을 위한 과거 구조 요약 추가
                        historical_summary = self._generate_historical_structure_summary(df, interval)

                        candle_count = {
                            "minute15": 50,  # 50 (12.5시간)
                            "minute60": 30,  # 30 (30시간)
                            "minute240": 15, # 15 (2.5일)
                            "day": 10        # 10 (10일)
                        }
                        
                        recent_count = candle_count.get(interval, 10)
                        
                        btc_data[f"{interval}_data"] = {
                            "ohlcv": data[-recent_count:],
                            "indicators": indicators,
                            "historical_structure_summary": historical_summary,  # 추가된 부분
                            "volume_stats": {
                                "mean": float(df['volume'].mean()),
                                "std": float(df['volume'].std()),
                                "recent": float(df['volume'].iloc[-1])
                            }
                        }
                    except Exception as e:
                        print(f"   ⚠️ {interval} 데이터 처리 오류: {e}")
                        continue
                else:
                    print(f"   ⚠️ {interval} 데이터가 비어있음")
            
            return btc_data
            
        except Exception as e:
            print(f"❌ BTC 데이터 수집 오류: {e}")
            import traceback
            traceback.print_exc()
            return {}

    # "상위 알트코인들의 원시 데이터를 수집하는 메서드" (인자: self)
    def _get_altcoin_raw_data(self) -> Dict[str, Any]:
        try:
            print("   📊 알트코인 데이터 수집 중...")
            
            # 상위 20개 코인
            top_coins = self.upbit.get_top_20_coins()  # 메서드명 변경 필요
            
            if not top_coins:
                print("❌ 상위 20개 코인 조회 실패")
                return {}
            
            # 원시 데이터 수집
            raw_altcoin_data = {}
            collected_count = 0
            
            max_coins = 20  # 20
            
            for ticker in top_coins[:max_coins]:
                if ticker == "KRW-BTC":
                    continue
                    
                try:
                    # 현재가
                    current_price = self.upbit.get_current_price(ticker)
                    if not current_price:
                        continue
                    
                    market_data = self.upbit.get_market_data(
                        ticker, 
                        ["minute5", "minute15", "minute60", "minute240", "day"]  # 5분봉, 15분, 1시간, 4시간, 일봉
                    )
                    
                    # day 데이터가 없으면 건너뛰기
                    if not market_data.get("day"):
                        continue
                    
                    # 원시 데이터 구성
                    coin_raw_data = {
                        "ticker": ticker,
                        "current_price": current_price,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # 각 시간대별 데이터와 지표
                    for interval, data in market_data.items():
                        if interval == "ticker":
                            continue
                            
                        if data and isinstance(data, list) and len(data) > 0:
                            try:
                                df = pd.DataFrame(data)
                                indicators = self.indicators.calculate_indicators(df)
                                
                                # 프랙탈 분석을 위한 과거 구조 요약 추가
                                historical_summary = self._generate_historical_structure_summary(df, interval)
                                
                                # 단기 분석용 최근 캔들 수
                                candle_count = {
                                    "minute5": 50,   # 5분봉 50개 (250분)
                                    "minute15": 40,  # 15분봉 40개 (10시간)
                                    "minute60": 30,  # 1시간봉 30개 (30시간)
                                    "minute240": 15,  # 4시간봉 15개 (60시간)
                                    "day": 10         # 일봉 10개 (5일)
                                }
                                
                                recent_count = candle_count.get(interval, 5)
                                
                                coin_raw_data[f"{interval}_data"] = {
                                    "ohlcv": data[-recent_count:],
                                    "indicators": indicators,
                                    "historical_structure_summary": historical_summary,
                                    "volume_stats": {
                                        "mean": float(df['volume'].mean()),
                                        "std": float(df['volume'].std()),
                                        "recent": float(df['volume'].iloc[-1]),
                                        "ratio": float(df['volume'].iloc[-1] / df['volume'].mean()) if df['volume'].mean() > 0 else 1.0
                                    }
                                }
                            except Exception as e:
                                continue
                    
                    raw_altcoin_data[ticker] = coin_raw_data
                    collected_count += 1
                    
                    # 진행 상황 표시
                    if collected_count % 5 == 0:
                        print(f"      수집 완료: {collected_count}개")
                        
                except Exception as e:
                    continue
            
            print(f"   ✅ 총 {collected_count}개 알트코인 데이터 수집 완료")
            return raw_altcoin_data
            
        except Exception as e:
            print(f"❌ 알트코인 데이터 수집 오류: {e}")
            import traceback
            traceback.print_exc()
            return {}

    # "GPT 분석 결과를 해석하고 포맷팅하여 출력하는 메서드" (인자: self, gpt_result, has_memory)
    def _interpret_altcoin_result(self, gpt_result: Dict[str, Any], has_memory: bool):
        action = gpt_result.get('action', 'wait')
        final_decision = gpt_result.get('final_decision', {})
        confidence = final_decision.get('confidence_level', 0)

        if action == 'proceed':
            top_3 = final_decision.get('top_3_tickers', [])
            profit_range = final_decision.get('expected_profit_range', 'N/A')
            
            print(f"\n✅ 거래 진행 (신뢰도: {confidence:.0f}%)")
            print(f"   🎯 선정 후보: {', '.join(top_3)}")
            print(f"   💰 예상 수익률: {profit_range}")

            memory_influence = final_decision.get('memory_influence', '')
            if memory_influence and has_memory:
                print(f"   🧠 교훈 활용: {memory_influence[:100]}")
                
        else:
            duration = final_decision.get('duration_hours', 1)
            reason = final_decision.get('reasoning', '')
            
            print(f"\n⏸️ 거래 대기 ({duration}시간)")
            print(f"   📝 사유: {reason[:100]}")
            
            if has_memory:
                memory_influence = final_decision.get('memory_influence', '')
                if memory_influence:
                    print(f"   🧠 교훈 반영: {memory_influence[:100]}")

    # "GPT-5를 활용하여 현재 시장 추세를 판단하는 메서드" (인자: self)
    def get_market_regime(self) -> str:

        try:
            import openai
            from config.settings import settings

            btc_data = self._get_btc_raw_data()
            
            if not btc_data:
                print("⚠️ BTC 데이터 수집 실패 - SIDEWAYS 기본값 사용")
                return "SIDEWAYS"

            prompt = f"""Analyze BTC market regime from raw data.
    BTC Data: {json.dumps(btc_data, ensure_ascii=False)}

# ROLE
You are an expert quantitative analyst specializing in BTC technical analysis for short-term automated trading systems. Your analysis must be objective and data-driven.

# CONTEXT
The goal is to determine the current market regime for the next 6-12 hours based on the provided raw data, which includes 1-hour OHLCV candles and key indicators.

# TASK
Analyze the provided BTC data and classify the market regime into one of three categories. Your reasoning should be summarized in the 'key_indicators' field.

# DATA
BTC Data: {json.dumps(btc_data, ensure_ascii=False)}

# REGIME DEFINITIONS
- BULL_TREND: Price is consistently trading above key moving averages (e.g., 20, 50-period). RSI is holding above 55. Recent price action shows higher highs and higher lows.
- BEAR_TREND: Price is consistently trading below key moving averages. RSI is holding below 45. Recent price action shows lower highs and lower lows.
- SIDEWAYS: Price is trading between clear support and resistance levels without a clear direction. Key moving averages are flattening and intertwining. RSI is hovering around 50.

# REQUIRED OUTPUT FORMAT
Classify the regime and provide confidence and key indicators in the specified JSON format."""

            openai.api_key = settings.OPENAI_API_KEY
            
            response = openai.responses.create(
                model="gpt-5",
                input=prompt,
                reasoning={"effort": "minimal"},
                text={
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "market_regime",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "regime": {
                                    "type": "string",
                                    "enum": ["BULL_TREND", "SIDEWAYS", "BEAR_TREND"]
                                },
                                "confidence": {
                                    "type": "number", 
                                    "minimum": 0, 
                                    "maximum": 100
                                },
                                "key_indicators": {
                                    "type": "string"
                                }
                            },
                            "required": ["regime", "confidence", "key_indicators"],
                            "additionalProperties": False
                        }
                    }
                },
                max_output_tokens=2048
            )

            if hasattr(response, 'output_text') and response.output_text:
                result = json.loads(response.output_text)
                
                regime = result.get('regime', 'SIDEWAYS')
                confidence = result.get('confidence', 0)
                indicators = result.get('key_indicators', '')
                
                print(f"📊 시장 추세: {regime} (신뢰도: {confidence}%)")
                if indicators:
                    print(f"   근거: {indicators[:100]}")
                
                return regime
            else:
                print("⚠️ GPT-5 추세 판단 실패 - SIDEWAYS 기본값 사용")
                return "SIDEWAYS"
                
        except Exception as e:
            print(f"❌ 시장 추세 판단 오류: {e}")
            return "SIDEWAYS"