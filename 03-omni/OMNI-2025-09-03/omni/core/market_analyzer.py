# core/market_analyzer.py
# "Phase 1: 시장 상황을 진단하고 거래 후보 TOP 3를 선정하는 시장 분석 파일"

import pandas as pd
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
        
        # 1. 과거 학습 경험 로드
        memory = self.reflector.get_recent_memory(limit=5)
        has_memory = bool(memory.get('long_term', '').strip() or memory.get('short_term', '').strip())
        
        if has_memory:
            print("🧠 과거 거래 경험을 참고합니다")
        else:
            print("순수 데이터 기반 분석 모드")
        
        # 2. BTC 원시 데이터 수집
        btc_data = self._get_btc_raw_data()
        
        # 3. 알트코인 원시 데이터 수집
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
        gpt_result = self.gpt.analyze_market_phase1(
            market_data, 
            altcoin_data, 
            memory if has_memory else None
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

                        candle_count = {
                            "minute15": 20,  # 15분봉 > 20개 (5시간)
                            "minute60": 15,  # 1시간봉 > 15개 (15시간)
                            "minute240": 10, # 4시간봉 > 10개 (40시간)
                            "day": 5         # 일봉 > 5개 (5일)
                        }
                        
                        recent_count = candle_count.get(interval, 10)
                        
                        btc_data[f"{interval}_data"] = {
                            "ohlcv": data[-recent_count:],
                            "indicators": indicators,
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
            
            # 상위 30개 코인 가져오기
            top_30_coins = self.upbit.get_top_30_coins()
            
            if not top_30_coins:
                print("❌ 상위 30개 코인 조회 실패")
                return {}
            
            # 원시 데이터 수집
            raw_altcoin_data = {}
            collected_count = 0
            
            max_coins = 30
            
            for ticker in top_30_coins[:max_coins]:
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
                                
                                # 단기 분석용 최근 캔들 수
                                candle_count = {
                                    "minute5": 10,   # 5분봉 10개 (50분)
                                    "minute15": 8,  # 15분봉 8개 (2시간)
                                    "minute60": 6,  # 1시간봉 6개 (6시간)
                                    "minute240": 3,  # 4시간봉 3개 (12시간)
                                    "day": 2         # 일봉 2개 (2일)
                                }
                                
                                recent_count = candle_count.get(interval, 5)
                                
                                coin_raw_data[f"{interval}_data"] = {
                                    "ohlcv": data[-recent_count:],
                                    "indicators": indicators,
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
                    if collected_count % 10 == 0:
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
