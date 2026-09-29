# ai/gpt_client.py
# AI Client for Trading System - Gemini 2.5 Pro (Phase 1) and GPT-5 (Phase 3)
# FIXED: JSON format requirement for GPT-5 API

import openai
import google.generativeai as genai
import json
import asyncio
import time
from typing import Dict, Any, Optional, List
from config.settings import settings
from datetime import datetime

_gpt_client_instance = None

def get_gpt_client():
    global _gpt_client_instance
    if _gpt_client_instance is None:
        _gpt_client_instance = GPTClient()
    return _gpt_client_instance

class GPTClient:
    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.gpt_model = "gpt-5"
        
        # Gemini 2.5 Pro 설정
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel('gemini-2.5-pro')
        
        # 캐시 관리
        self.response_cache = {}
        self.last_analysis_time = None
    
    def create_strategy_phase3(self, 
                                coin_data: Dict[str, Any], 
                                selected_coin: str,
                                analysis: Dict[str, Any] = None) -> Dict[str, Any]:
            
            print(f"\n🤖 GPT-5 자율 전략 수립 (V14: 2-Target): {selected_coin}")
            
            current_price = coin_data.get('current_price', 0)
            
            # indicators.py에서 계산된 정확한 레벨 사용
            key_levels = coin_data.get('key_levels', {})
            if not key_levels:
                h1_data = coin_data.get('minute60_analysis', {})
                key_levels = h1_data.get('key_levels', {})
            
            recent_high = key_levels.get('recent_high', current_price)
            recent_low = key_levels.get('recent_low', current_price)
            price_position = key_levels.get('price_position', 50.0)
            atr = coin_data.get('minute60_analysis', {}).get('indicators', {}).get('atr_14', 0)
            
            print(f"   📊 가격 분석:")
            print(f"      현재가: {current_price:,.0f} KRW")
            print(f"      최근 고점: {recent_high:,.0f} KRW")
            print(f"      최근 저점: {recent_low:,.0f} KRW")
            print(f"      위치: {price_position:.1f}%")
            
            # 오더북 데이터 추출 및 분석
            orderbook_analysis = coin_data.get('orderbook_analysis', {})
            orderbook_context = ""
            
            if orderbook_analysis:
                print(f"\n   📊 오더북 상태:")
                print(f"      스프레드: {orderbook_analysis.get('spread', 0):.3f}%")
                print(f"      매수/매도 비율: {orderbook_analysis.get('bid_ask_ratio', 1):.2f}")
                print(f"      주문 불균형: {orderbook_analysis.get('order_imbalance', 0):+.1f}%")
                print(f"      시장 압력: {orderbook_analysis.get('pressure', 'NEUTRAL')}")
                
                bid_walls = orderbook_analysis.get('bid_walls', [])
                ask_walls = orderbook_analysis.get('ask_walls', [])
                
                if bid_walls:
                    print(f"      🧱 매수벽 감지: {len(bid_walls)}개")
                    for wall in bid_walls[:2]:
                        print(f"         - {wall['price']:,.0f}원 (평균의 {wall['ratio']:.1f}배)")
                
                if ask_walls:
                    print(f"      🧱 매도벽 감지: {len(ask_walls)}개")
                    for wall in ask_walls[:2]:
                        print(f"         - {wall['price']:,.0f}원 (평균의 {wall['ratio']:.1f}배)")
                
                pressure = orderbook_analysis.get('pressure', 'NEUTRAL')
                spread = orderbook_analysis.get('spread', 0)
                
                if pressure == 'STRONG_BUY':
                    execution_urgency = "HIGH"
                    urgency_reason = "강한 매수 압력 감지"
                elif pressure == 'STRONG_SELL':
                    execution_urgency = "LOW"
                    urgency_reason = "강한 매도 압력 - 대기 권장"
                elif spread > 0.3:
                    execution_urgency = "LOW"
                    urgency_reason = "넓은 스프레드 - 지정가 권장"
                else:
                    execution_urgency = "MEDIUM"
                    urgency_reason = "정상 시장 상태"
            else:
                execution_urgency = "MEDIUM"
                urgency_reason = "오더북 데이터 없음"
            
            # Phase 1에서 전달받은 시장 체제 및 분석
            market_regime = analysis.get('market_regime', 'SIDEWAYS') if analysis else 'SIDEWAYS'
            expected_move = analysis.get('expected_move', '2-3%') if analysis else '2-3%'
            confidence = analysis.get('confidence_level', 70) if analysis else 70

            pressure = orderbook_analysis.get('pressure', 'NEUTRAL') if orderbook_analysis else 'NEUTRAL'
            spread = orderbook_analysis.get('spread', 0) if orderbook_analysis else 0

            # Phase 1 분석 결과 활용
            gemini_context = ""
            if analysis:
                gemini_context = f"""
            <phase1_analysis>
            Market Regime: {market_regime}
            Selected Coin: {selected_coin}
            Confidence: {confidence}%
            Expected Move: {expected_move}
            Reasoning: {analysis.get('reasoning', 'N/A') if analysis else 'N/A'}
            </phase1_analysis>"""

            # 오더북 컨텍스트 준비
            if orderbook_analysis:
                orderbook_context = f"""
            # ORDERBOOK ANALYSIS (Real-time)
            - Spread: {orderbook_analysis.get('spread', 0):.3f}% ({orderbook_analysis.get('spread_krw', 0):,.0f} KRW)
            - Buy/Sell Volume Ratio: {orderbook_analysis.get('bid_ask_ratio', 1):.2f}
            - Order Imbalance: {orderbook_analysis.get('order_imbalance', 0):+.1f}%
            - Market Pressure: {orderbook_analysis.get('pressure', 'NEUTRAL')}
            - Best Bid: {orderbook_analysis.get('best_bid', 0):,.0f} KRW
            - Best Ask: {orderbook_analysis.get('best_ask', 0):,.0f} KRW
            - Weighted Mid Price: {orderbook_analysis.get('weighted_mid_price', 0):,.0f} KRW"""
                
                bid_walls = orderbook_analysis.get('bid_walls', [])
                ask_walls = orderbook_analysis.get('ask_walls', [])
                
                if bid_walls:
                    orderbook_context += f"\n- Bid Walls Detected: {len(bid_walls)} levels"
                    for i, wall in enumerate(bid_walls[:2], 1):
                        orderbook_context += f"\n  Wall {i}: {wall['price']:,.0f} KRW ({wall['ratio']:.1f}x average)"
                
                if ask_walls:
                    orderbook_context += f"\n- Ask Walls Detected: {len(ask_walls)} levels"
                    for i, wall in enumerate(ask_walls[:2], 1):
                        orderbook_context += f"\n  Wall {i}: {wall['price']:,.0f} KRW ({wall['ratio']:.1f}x average)"
    
            prompt = f"""
# AI Execution Strategist: Generate 2-Target Plan (V15 Ultimate)

# Goal: Calculate HIGH-PROBABILITY entry, VERY conservative T1 (70%), realistic T2 (30%), TIGHT initial stop, position size. Output ONLY required JSON.
# Priority: Hit T1 to enable risk-free runner (SL->Breakeven). Maximize breakeven opportunities.

# Inputs:
<phase1_analysis>
{gemini_context}
</phase1_analysis>
<market_data>
Coin:{selected_coin}|Price:{current_price:,.0f}|ATR:{atr:,.0f}({(atr/current_price*100):.2f}%)|Range:{recent_low:,.0f}-{recent_high:,.0f}|Pos:{price_position:.1f}%
</market_data>
<orderbook_data>
{orderbook_context}
</orderbook_data>

# Process:

### 1. Asset Profile:
- **MAJOR (BTC, ETH):** Conservative Entry (No Chase)
- **ALTCOIN (Others):** Balanced Entry

### 2. Base Strategy (From Phase 1 `Market Regime`):

| Regime      | Base Entry Rule         | Base Target Concept          | Base Stop Concept              | Base Pos Size | R:R Min |
|-------------|-------------------------|------------------------------|--------------------------------|---------------|---------|
| BULL_TREND  | Wait -0.3% pullback     | Moderate Gain (+3.5%/1.5ATR) | Tight (-2.5% max/1.0ATR)       | 65%           | 1.3     |
| SIDEWAYS    | Wait -0.5% pullback     | Small Gain (+2.5%/1.0ATR)    | Moderate (-3.0% max/1.2ATR)    | 45%           | 1.2     |
| BEAR_TRAP   | Wait -0.7% pullback     | Minimal Gain (+1.8%/0.7ATR)  | Very Tight (-2.0% max/0.7ATR)  | 25%           | 1.0     |
| KOREAN_PUMP | Immediate market entry  | Large Gain (+5.0%/2.0ATR)    | Wider (-3.5% max/1.5ATR)       | 55%           | 1.5     |

### 3. Calculate Entry Price (`entry_price`):
- **STRONG_BUY Pressure:**
    - ALTCOIN: `Entry = Current Price`
    - MAJOR: **NO CHASE.** `Entry = Current Price * (1 - 0.003 to 0.005)`
- **BUY Pressure:**
    - ALTCOIN: Reduce pullback: `Entry = Current Price * (1 - 0.001 to 0.002)`
    - MAJOR: Stick to baseline pullback (e.g., -0.3%)
- **NEUTRAL/SELL/STRONG_SELL:** Apply baseline or increase pullback (up to -1.0%).
- **WIDE Spread (>0.3%):** Add extra -0.1% pullback buffer.

### 4. Calculate Exits & Stop (`target_price_1`, `target_price_2`, `stop_loss_price`):
**NOTE: Target split ratio is FIXED at 0.7 (70% T1 / 30% T2).**

**Target 1 (T1) - 70% Exit (VERY Conservative - Maximize Hit Rate):**
- Find nearest significant Ask Wall within +2% of Entry.
- `IF` wall: `T1 = Wall_Price * 0.998`
- `ELSE`: `T1 = Entry * (1 + min(0.012, 0.7 * ATR / Entry))` **(Aim for ~+0.8% to +1.2% gain, easy target)**

**Target 2 (T2) - 30% Runner (Realistic Ambition):**
- Determine Regime Multiplier: BULL/PUMP=2.0, SIDEWAYS=1.5, BEAR=1.0
- `Potential_T2_ATR = Entry * (1 + Multiplier * ATR / Entry)`
- Find nearest significant `Next_Resistance` (Recent High or next Ask Wall).
- `Potential_T2_Res = Next_Resistance * 0.998`
- `T2 = min(Potential_T2_ATR, Potential_T2_Res)` **(Use the lower target for realism)**
- Ensure minimum gap: `T2 = max(T2, T1 * 1.02)` (Must be >= T1 + 2%)
- **Realism Cap:** `T2 = min(T2, Entry * 1.10)` **(Hard cap T2 gain at +10% max from entry)**

**Initial Stop Loss (SL) - TIGHTER:**
- `SL = Entry * (1 - max(0.007, 0.8 * ATR / Entry))` **(Aim for ~-0.7% to -0.9% risk, tighter than before)**
- Adjust SL below nearby Bid Wall if applicable.
- *(System moves SL to Entry after T1 hit)*

### 5. Calculate Position Size (`position_size_percent`):
- `Final % = Base_Size * Confidence_Mult * Orderbook_Mult`
- Apply Caps: BULL 85%, SIDEWAYS 60%, BEAR 35%, PUMP 70% (Min 20%).

### 6. Generate JSON Output ONLY:
- Validate: T2 > T1 > Entry > SL. Check R:R (blended, ensuring it meets regime min).
- **Output ONLY the JSON.**

# REQUIRED JSON OUTPUT (V14.1 Schema - DO NOT CHANGE)
{{
  "entry_price": "[Calc Price Step 3]",
  "target_price_1": "[Calc T1 Step 4 - VERY Conservative]",
  "target_price_2": "[Calc T2 Step 4 - Realistic Runner]",
  "target_split_ratio": 0.7,
  "stop_loss_price": "[Calc SL Step 4 - TIGHTER]",
  "position_size_percent": "[Final % Step 5]",
  "reasoning": "[Profile: MAJOR/ALTCOIN]. Regime:{market_regime}. Pressure:{pressure}. Conf:{confidence}%. Strategy:[Entry logic]. T1(70%):[Conservative T1 logic, aiming for high hit rate ~+1%]. T2(30%):[Realistic T2 logic using {Multiplier}x ATR capped by resistance/max gain]. SL:[Tight initial SL logic ~-0.8%]. Note:After T1, SL->Breakeven."
}}
"""

            try:
                print("   📡 GPT-5 API 호출 (V14: 2-Target 전략)")
                start_time = time.time()
                
                # GPT-5 Responses API 사용
                response = openai.responses.create(
                    model=self.gpt_model,  # "gpt-5"
                    input=prompt,
                    reasoning={
                        "effort": "medium"
                    },
                    text={
                        "verbosity": "low",
                        "format": {
                            "type": "json_schema",
                            "name": "trading_strategy_v14",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "entry_price": {"type": "number"},
                                    "target_price_1": {"type": "number"},  # V14
                                    "target_price_2": {"type": "number"},  # V14
                                    "target_split_ratio": {"type": "number", "default": 0.7},  # V14
                                    "stop_loss_price": {"type": "number"},
                                    "position_size_percent": {
                                        "type": "integer", 
                                        "minimum": 35, 
                                        "maximum": 90
                                    },
                                    "reasoning": {"type": "string"}
                                },
                                "required": [
                                    "entry_price", 
                                    "target_price_1",   # V14
                                    "target_price_2",   # V14
                                    "target_split_ratio",
                                    "stop_loss_price", 
                                    "position_size_percent", 
                                    "reasoning"
                                ],
                                "additionalProperties": False
                            }
                        }
                    },
                    max_output_tokens=70000
                )
                
                elapsed = time.time() - start_time
                print(f"   ✅ GPT-5 응답 완료 ({elapsed:.1f}초)")
                
                # 응답 파싱
                if not hasattr(response, 'output_text') or not response.output_text:
                    print("   ❌ GPT-5 응답에 output_text 없음")
                    return {"error": "GPT-5 응답 실패 - output_text 없음"}
                
                try:
                    strategy = json.loads(response.output_text)
                    print("   ✅ JSON 파싱 성공 (V14)")
                except json.JSONDecodeError as e:
                    print(f"   ❌ JSON 파싱 실패: {e}")
                    return {"error": f"GPT-5 JSON 파싱 실패: {str(e)}"}
                
                # V14: 2개 목표가 추출
                entry_price = float(strategy.get('entry_price', 0))
                target_price_1 = float(strategy.get('target_price_1', 0))  # V14
                target_price_2 = float(strategy.get('target_price_2', 0))  # V14
                target_split_ratio = float(strategy.get('target_split_ratio', 0.7))  # V14
                stop_loss_price = float(strategy.get('stop_loss_price', 0))
                position_size = int(strategy.get('position_size_percent', 0))
                reasoning = strategy.get('reasoning', '')
                
                # 오더북 기반 가격 미세 조정
                if orderbook_analysis and entry_price > 0:
                    if pressure == 'STRONG_BUY':
                        entry_price = min(entry_price, current_price * 1.001)
                    elif pressure == 'STRONG_SELL':
                        entry_price = min(entry_price, current_price * 0.995)
                    
                    # 매도벽 회피 (T1만 조정, T2는 유지)
                    if ask_walls:
                        nearest_wall = ask_walls[0]['price']
                        if abs(target_price_1 - nearest_wall) / nearest_wall < 0.005:
                            target_price_1 = nearest_wall * 0.998
                            print(f"   🎯 T1 조정: {target_price_1:,.0f}원 (매도벽 회피)")
                
                # V14: 가격 유효성 검사 (2개 목표가)
                if not (entry_price > 10 and 
                        target_price_1 > entry_price and 
                        target_price_2 > target_price_1 and  # V14: T2 > T1
                        stop_loss_price < entry_price and
                        abs(entry_price - current_price) / current_price < 0.1):
                    print(f"   ❌ 가격 검증 실패!")
                    print(f"      진입: {entry_price}, T1: {target_price_1}, T2: {target_price_2}, 손절: {stop_loss_price}")
                    return {"error": "GPT-5 전략 가격 검증 실패 (V14)"}
                
                # 포지션 크기 검증
                position_size = max(20, min(97, position_size))
                
                # 오더북 압력에 따른 포지션 조정
                if orderbook_analysis:
                    if pressure == 'STRONG_BUY' and confidence >= 80:
                        position_size = min(position_size * 1.1, 90)
                        print(f"   💼 포지션 상향: {position_size}% (강한 매수압력)")
                    elif pressure == 'STRONG_SELL':
                        position_size = max(position_size * 0.9, 20)
                        print(f"   💼 포지션 하향: {position_size}% (강한 매도압력)")
                
                position_size = int(position_size)
                
                # V14: 혼합 수익률 계산
                expected_return_1 = ((target_price_1 - entry_price) / entry_price) * 100
                expected_return_2 = ((target_price_2 - entry_price) / entry_price) * 100
                blended_return = (expected_return_1 * target_split_ratio) + (expected_return_2 * (1 - target_split_ratio))
                risk_return = ((stop_loss_price - entry_price) / entry_price) * 100
                rr_ratio = abs(blended_return / risk_return) if risk_return != 0 else 0
                
                # V14: 전략 파라미터 (2개 목표가)
                trading_params = {
                    "coin_ticker": selected_coin,
                    "current_price": current_price,
                    "entry_price": entry_price,
                    "target_price_1": target_price_1,      # V14
                    "target_price_2": target_price_2,      # V14
                    "target_split_ratio": target_split_ratio,  # V14
                    "stop_loss_price": stop_loss_price,
                    "entry_reason": reasoning,
                    "target_reason": f"T1: {expected_return_1:.1f}% (70%) / T2: {expected_return_2:.1f}% (30%)",  # V14
                    "stop_loss_reason": f"손실 제한 {risk_return:.1f}%",
                    "position_size_percent": position_size,
                    "execution_urgency": execution_urgency,
                    "urgency_reason": urgency_reason
                }
                
                print(f"\n   ✅ GPT-5 자율 전략 완성 (V14)")
                print(f"   💰 진입가: {entry_price:,.0f} KRW")
                print(f"   🎯 목표가 1: {target_price_1:,.0f} KRW (+{expected_return_1:.2f}%) [70% 청산]")  # V14
                print(f"   🚀 목표가 2: {target_price_2:,.0f} KRW (+{expected_return_2:.2f}%) [30% 추격]")  # V14
                print(f"   🛑 손절가: {stop_loss_price:,.0f} KRW")
                print(f"   💼 포지션: {position_size}%")
                print(f"   📈 혼합 수익: +{blended_return:.2f}% (가중평균)")  # V14
                print(f"   📉 리스크: {risk_return:.2f}%")
                print(f"   ⚖️ R:R 비율: 1:{rr_ratio:.1f}")
                print(f"   ⚡ 실행 긴급도: {execution_urgency} ({urgency_reason})")
                
                return {
                    "trading_parameters": trading_params,
                    "risk_assessment": {
                        "risk_reward_ratio": rr_ratio,
                        "position_size_suggestion": f"{position_size}%",
                        "execution_urgency": execution_urgency,
                        "urgency_reason": urgency_reason,
                        "expected_duration": "hours",
                        "orderbook_quality": "GOOD" if spread < 0.2 else "FAIR" if spread < 0.5 else "POOR"
                    }
                }
                
            except openai.APIError as e:
                print(f"   ❌ GPT-5 API 오류: {e}")
                return {"error": f"GPT-5 API 오류: {str(e)}"}
                
            except Exception as e:
                print(f"   ❌ GPT-5 전략 수립 실패: {e}")
                import traceback
                traceback.print_exc()
                return {"error": f"GPT-5 전략 수립 실패: {str(e)}"}

    # Phase 1 Gemini 분석 함수는 그대로 유지
    async def analyze_market_phase1_gemini(self, 
                                          market_data: Dict[str, Any], 
                                          coins_data: Dict[str, Any]) -> Dict[str, Any]:
        
        print("🤖 Gemini 2.5 Pro 자율 분석 시작...")
        start_time = time.time()
        
        # 상위 20개 코인 선택
        top_20_coins = self._select_top_20_coins(coins_data)
        print(f"   📊 분석 대상: {len(top_20_coins)}개 코인")
        
        # 모든 코인 데이터를 하나의 구조화된 JSON으로 구성
        batch_prompt = self._build_unified_analysis_prompt(top_20_coins, market_data)
        
        try:
            print("   🚀 Gemini 2.5 Pro 호출 (자율 판단)")
            
            # Gemini 단일 요청 - 모든 코인 동시 분석
            response = self.gemini_model.generate_content(
                batch_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=150000,
                    response_mime_type="application/json"
                )
            )
            
            # 응답 파싱
            result = json.loads(response.text)
            elapsed = time.time() - start_time
            
            print(f"✅ Gemini 분석 완료 ({elapsed:.1f}초)")
            
            # 시장 체제 출력
            market_regime = result.get('market_regime', 'SIDEWAYS')
            print(f"\n   🌍 시장 체제: {market_regime}")
            print(f"   📝 시장 개요: {result.get('market_overview', '')}")

            # 분석 결과 처리
            best_coin = result.get('final_selection', {})
            
            if best_coin.get('ticker'):
                print(f"\n   🎯 최종 선정: {best_coin['ticker']}")
                print(f"   💡 판단 근거: {best_coin.get('key_reason', 'AI 자율 판단')}")
                print(f"   🔮 신뢰도: {best_coin.get('confidence', 0)}%")
                print(f"   📈 예상 움직임: {best_coin.get('expected_move', 'N/A')}")
                
                return {
                    "action": "proceed",
                    "selected_coin": best_coin['ticker'],
                    "analysis": best_coin.get('detailed_analysis', {}),
                    "confidence_level": best_coin.get('confidence', 0),
                    "reasoning": best_coin.get('selection_reason', ''),
                    "market_context": result.get('market_overview', ''),
                    "market_regime": market_regime,  # Phase 3로 전달
                    "expected_move": best_coin.get('expected_move', '2-3%'),  # Phase 3로 전달
                    "comparison_matrix": result.get('comparison_matrix', {})
                }
            else:
                # 거래하지 않기로 결정
                wait_reason = result.get('wait_reason', 'No suitable opportunities')
                wait_minutes = self._determine_wait_time_by_regime(market_regime)
                
                print(f"\n   ⏳ 거래 대기 결정 - {wait_minutes}분")
                print(f"   🔍 이유: {wait_reason}")
                
                return {
                    "action": "wait",
                    "reason": wait_reason,
                    "wait_minutes": wait_minutes,
                    "market_overview": result.get('market_overview', ''),
                    "market_regime": market_regime
                }
                
        except Exception as e:
            print(f"   ❌ Gemini 분석 오류: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "action": "wait",
                "reason": f"분석 오류: {str(e)}",
                "wait_minutes": 30
            }
    
    def _determine_wait_time_by_regime(self, market_regime: str) -> int:
        """시장 체제별 대기 시간 결정"""
        wait_times = {
            'BULL_TREND': 30,     # 활발한 시장, 자주 체크
            'SIDEWAYS': 45,       # 중간 빈도
            'BEAR_TRAP': 90,     # 위험한 시장, 긴 대기
            'KOREAN_PUMP': 20    # 빠른 시장, 자주 체크
        }
        return wait_times.get(market_regime, 30)

    def _build_unified_analysis_prompt(self, coins_data: Dict, market_data: Dict) -> str:
        # 코인 데이터 구조화
        coins_analysis_data = []
        for ticker, data in coins_data.items():
            h1_indicators = data.get('minute60_data', {}).get('indicators', {})
            
            coin_summary = {
                "ticker": ticker,
                "current_price": data.get('current_price', 0),
                "volume_24h_krw": data.get('volume_24h_krw', 0),
                "change_24h": data.get('change_24h', 0),
                "volume_ratio": h1_indicators.get('volume_ratio', 1.0),
                
                "technical_indicators": {
                    "rsi_14": h1_indicators.get('rsi_14', 50),
                    "macd": h1_indicators.get('macd', 0),
                    "macd_signal": h1_indicators.get('macd_signal', 0),
                    "macd_histogram": h1_indicators.get('macd_histogram', 0),
                    "bb_position": h1_indicators.get('bb_position', 50),
                    "adx": h1_indicators.get('adx', 0),
                    "obv_trend": h1_indicators.get('obv_trend', 'NEUTRAL'),
                    "mfi": h1_indicators.get('mfi', 50),
                    "atr_14_pct": h1_indicators.get('atr_14_pct', 0)
                },
                
                "moving_averages": {
                    "sma_50": h1_indicators.get('sma_50', 0),
                    "sma_200": h1_indicators.get('sma_200', 0),
                    "ema_21": h1_indicators.get('ema_21', 0),
                },
                
                "divergences": h1_indicators.get('divergences', {}),
            }
            coins_analysis_data.append(coin_summary)
        
        # BTC 데이터 추출
        btc_data = market_data.get('btc_data', {})
        btc_price = btc_data.get('current_price', 0)
        btc_h1 = btc_data.get('minute60_data', {}).get('indicators', {})
        btc_rsi = btc_h1.get('rsi_14', 50)
        btc_adx = btc_h1.get('adx', 0)
        
        # 현재 시간 체크 (한국 시장 특성)
        current_hour = datetime.now().hour
        time_context = "Korean Peak Hours" if (9 <= current_hour <= 11) or (20 <= current_hour <= 23) else "Normal Hours"
         
        prompt = f"""
# MISSION: KOREAN CRYPTO MARKET ANALYSIS & SELECTION
You are a senior quantitative analyst for a Korean crypto trading desk. Your primary goal is to identify the single most promising, short-term (hours) trading opportunity from a list of high-volume assets on Upbit. You must be highly selective and prioritize capital preservation. It is better to wait for a high-probability setup than to force a trade.

Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST ({time_context})

# YOUR CHAIN OF THOUGHT (Follow these steps precisely):

### Step 1: Define the Overall Market Regime (Most Critical Step)
Based on the provided BTC status and the current time, classify the market into ONE of the following four regimes. This classification will dictate your entire strategy.
- **BTC Status:** Price={btc_price:,.0f} KRW, RSI(1H)={btc_rsi:.1f}, ADX(1H)={btc_adx:.1f}
- **Regimes:**
  1. **BULL_TREND:** BTC is strong and rising (RSI > 55, ADX > 20). Altcoins are likely to follow. Strategy: Find coins with momentum.
  2. **SIDEWAYS:** BTC is range-bound (RSI 45-55, ADX < 25). Altcoins may rotate. Strategy: Look for mean-reversion plays (buy support, sell resistance).
  3. **BEAR_TRAP:** BTC is weak or falling (RSI < 45). High risk. Strategy: AVOID trading. Only consider a trade if a perfect, high-conviction (85%+) oversold bounce setup with divergence appears.
  4. **KOREAN_PUMP:** Market is driven by specific, high-volume pumps in Korean-favored altcoins, often decoupling from BTC. (Common during peak hours 9-11am, 8-11pm KST). Strategy: Identify and ride early momentum.

### Step 2: Screen Candidates Based on the Active Regime
Filter the provided list of coins based on your chosen regime's strategy.
- If BULL_TREND: Screen for coins with RSI > 50, positive MACD, and increasing volume.
- If SIDEWAYS: Screen for coins near support/resistance or with RSI < 35 for a bounce.
- If BEAR_TRAP: Immediately discard 95% of coins. Only look for extreme oversold conditions (RSI < 30) with clear bullish divergence.
- If KOREAN_PUMP: Screen for coins with volume ratio > 5 and change_24h > 5% but < 15% (to catch them early).

### Step 3: Apply Conceptual Risk Filters (CRITICAL)
From your screened list, **you MUST discard** any coin that meets these 'Toxic Asset' criteria, regardless of its technical setup. Use your internal knowledge to assess the context.
1.  **AVOID POST-LISTING / AIRDROP DUMPS:**
    - Ask yourself: Is this coin's high volume combined with **sharp negative price action (e.g., `change_24h < -5%`)** explainable by a recent major exchange listing, token unlock, or large-scale airdrop distribution?
    - If YES: This is a **'falling knife' (dumping)**, not an 'oversold bounce' (opportunity). **DISCARD IT.**
2.  **AVOID UNSTABLE VOLATILITY:**
    - Ask yourself: Is this coin's high volatility (`atr_14_pct` is unusually high) combined with an erratic chart (e.g., long upper and lower wicks, "shakeouts")?
    - If YES: This implies **unpredictable manipulation**, not a clean technical setup. The stop-loss is unreliable. **DISCARD IT.**
3.  **AVOID FOMO TRAPS (Over-Pumped):**
    - Ask yourself: Is this coin already up significantly **(e.g., `change_24h > +20.0%`)**?
    - If YES: The move is likely exhausted. Risk of reversal is too high. **DISCARD IT.**

### Step 4: Analyze Top 2-3 Candidates & Make Final Selection
From your screened list, perform a deep-dive analysis on the top 2-3 candidates. Compare them against each other. Select the ONE with the highest probability of success. If no coin presents a clear A+ setup, you MUST choose to wait.

### Step 5: Generate Final JSON Output
Compile your findings into the required JSON format. Be concise but thorough in your reasoning.

# PROVIDED COIN DATA
<all_coins_data>
{json.dumps(coins_analysis_data, ensure_ascii=False, indent=2)}
</all_coins_data>

# REQUIRED JSON OUTPUT (Strictly adhere to this format)
{{
  "market_overview": "A concise summary of the current market state and what to expect in the next few hours.",
  "market_regime": "BULL_TREND|SIDEWAYS|BEAR_TRAP|KOREAN_PUMP",
  "top_candidates": [
    {{"ticker": "KRW-XXX", "reason": "Specific pattern and indicators"}},
    {{"ticker": "KRW-YYY", "reason": "Specific pattern and indicators"}}
  ],
  "final_selection": {{
    "ticker": "KRW-XXX",  // The ticker of the chosen coin, or null if you decide to wait.
    "confidence": 75,  // Your confidence in this trade's success (scale 60-95).
    "key_reason": "One-line summary of why this coin was selected over others.",
    "expected_move": "2-3%",  // Realistic profit potential for this trade.
    "selection_reason": "Detailed explanation of why this trade will work, comparing it to other candidates if necessary.",
    "detailed_analysis": {{
      "technical_setup": "e.g., 'Clear bullish divergence on the 1H chart at a major support level.'",
      "key_indicators": "e.g., 'RSI is oversold at 28, Volume Ratio is 3.5x, MFI is bottoming.'",      "volume_analysis": "Volume context",
      "risk_factors": [
            "e.g., 'BTC is still in a slight downtrend, which could cap the bounce.'",
            "e.g., 'There is a known resistance level at 1,250 KRW.'"
        ],
      "entry_timing": "IMMEDIATE|WAIT_DIP|WAIT_BREAKOUT"
    }}
  }},
  "wait_reason": null  // If ticker is null, provide a clear reason, e.g., "Market is in a BEAR_TRAP regime with no high-probability setups available. Waiting for BTC to stabilize."
}}

"""
        return prompt
    
    def _select_top_20_coins(self, coins_data: Dict) -> Dict:
        # 거래량 기준으로 상위 20개 선택
        sorted_coins = sorted(
            coins_data.items(),
            key=lambda x: x[1].get('volume_24h_krw', 0),
            reverse=True
        )
        
        selected = dict(sorted_coins[:20])
        
        # 선택된 코인 목록 출력
        print("\n   📋 분석 대상 20개 코인:")
        coin_names = [ticker.replace('KRW-', '') for ticker in selected.keys()]
        for i in range(0, len(coin_names), 5):
            print(f"      {', '.join(coin_names[i:i+5])}")
        
        return selected
    
    def _determine_wait_time(self) -> int:
        current_hour = datetime.now().hour
        
        # 새벽 시간대 (1-9시): 긴 대기
        if 1 <= current_hour < 9:
            return 120  # 2시간
        # 활발한 시간대: 짧은 대기  
        else:
            return 30  # 30분
    
    def analyze_market_phase1(self, 
                            market_data: Dict[str, Any], 
                            coins_data: Dict[str, Any],
                            memory: Dict[str, str] = None) -> Dict[str, Any]:
        # 동기 래퍼
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                self.analyze_market_phase1_gemini(market_data, coins_data)
            )
            return result
        finally:
            loop.close()
    
    def cleanup(self):
        self.response_cache.clear()
        self.last_analysis_time = None
        print("🧹 AI 클라이언트 정리 완료")