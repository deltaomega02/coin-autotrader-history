# core/strategy_maker.py
# "Phase 3: 선정된 코인에 대한 구체적인 거래 전략(진입가, 목표가, 손절가)을 수립하는 파일"

import pandas as pd
from typing import Dict, Any, Optional
from data.upbit_client import UpbitClient
from data.indicators import TechnicalIndicators
from data.database import TradeDatabase
from ai.gpt_client import get_gpt_client
from core.reflector import Reflector
from datetime import datetime  

class StrategyMaker:
    
    # "StrategyMaker 클래스를 초기화하고 필요한 클라이언트들을 생성하는 메서드" (인자: self)
    def __init__(self):
        self.upbit = UpbitClient()
        self.indicators = TechnicalIndicators()
        self.gpt = get_gpt_client()
        self.db = TradeDatabase()
        self.reflector = Reflector()
    
    # "선정된 코인에 대한 거래 전략을 수립하고 DB에 저장하는 메서드" (인자: self, selected_coin, deep_analysis)
    def create_trading_strategy(self, selected_coin: str, deep_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        print(f"📋 Phase 3: {selected_coin} 거래 전략 수립 시작...")
        
        # ========== memory 관련 부분 주석처리 시작 ==========
        # # 1. 과거 학습 경험 로드
        # memory = self.reflector.get_recent_memory(limit=5)
        # has_memory = bool(memory.get('long_term', '').strip() or memory.get('short_term', '').strip())
        # 
        # if has_memory:
        #     print("🧠 과거 거래 경험을 전략 수립에 반영합니다")
        # else:
        #     print("순수 데이터 기반 전략 수립")
        # ========== memory 관련 부분 주석처리 끝 ==========
        
        # memory 사용하지 않도록 설정
        memory = None
        has_memory = False
        print("순수 데이터 기반 전략 수립")
        
        # 2. 선정된 코인의 원시 데이터 수집
        coin_data = self._get_raw_strategy_data(selected_coin)
        if not coin_data:
            return {"error": f"{selected_coin} 데이터 수집 실패"}
        
        print(f"   📊 {selected_coin} 원시 데이터 수집 완료")
        
        # 3. GPT-5 전략 수립 호출
        # ========== memory 파라미터 제거 ==========
        # 기존: memory if has_memory else None
        # 변경: None으로 고정
        strategy = self.gpt.create_strategy_phase3(
            coin_data, 
            selected_coin, 
            deep_analysis,
            None  # memory 파라미터를 항상 None으로 전달
        )
        
        if strategy.get('error'):
            print(f"❌ 전략 수립 실패: {strategy['error']}")
            return strategy
        
        # 3-1. GPT 컨텍스트 수집
        gpt_context = self._collect_gpt_context(selected_coin, deep_analysis, strategy)
        
        # 4. DB 저장용 데이터 준비
        db_strategy = self._prepare_db_strategy(strategy, coin_data)
        
        # 5. 거래 계획을 DB에 저장 (컨텍스트 포함)
        trade_id = self.db.insert_trade_plan(db_strategy, gpt_context)  
        strategy['trade_id'] = trade_id
        strategy['gpt_context'] = gpt_context 
        
        # 6. 결과 출력
        self._display_strategy_result(strategy, has_memory)
        
        return strategy
    
    # "전략 수립용 원시 데이터를 수집하는 메서드" (인자: self, ticker)
    def _get_raw_strategy_data(self, ticker: str) -> Optional[Dict[str, Any]]:

        try:
            # 모든 타임프레임 원시 데이터 수집
            market_data = self.upbit.get_market_data(
                ticker, 
                ["minute5", "minute60", "minute240", "day"]
            )
            
            strategy_data = {
                "ticker": ticker, 
                "timestamp": pd.Timestamp.now().isoformat()
            }
            
            # 각 타임프레임별 원시 데이터와 순수 지표
            for interval, data in market_data.items():
                if interval == "ticker" or not data:
                    continue
                
                df = pd.DataFrame(data)
                if df.empty:
                    continue
                
                # 순수 기술 지표만 (점수 없음)
                indicators = self.indicators.calculate_indicators(df)
                
                # 최근 캔들 데이터
                recent_candles = data[-10:] if len(data) >= 10 else data
                
                strategy_data[f"{interval}_analysis"] = {
                    "candles": recent_candles,  # 원시 OHLCV
                    "indicators": indicators,    # 순수 지표
                    "data_points": len(data)     # 데이터 개수
                }
            
            # 현재가 정보
            current_price = self.upbit.get_current_price(ticker)
            strategy_data['current_price'] = current_price
            
            # ATR 분석
            atr_analysis = self._calculate_atr_based_targets(strategy_data, current_price)
            if atr_analysis:
                strategy_data['atr_analysis'] = atr_analysis
                
                # ATR 정보 로그 출력
                daily_atr = atr_analysis.get('daily_atr_krw', 0)
                daily_atr_pct = atr_analysis.get('daily_atr_percentage', 0)
                recommended_targets = atr_analysis.get('recommended_target_range', {})
                
                print(f"🎯 {ticker} ATR 분석:")
                print(f"   일봉 ATR: {daily_atr:.6f}원 ({daily_atr_pct:.2f}%)")
                if recommended_targets:
                    conservative = recommended_targets.get('conservative_target', 0)
                    aggressive = recommended_targets.get('aggressive_target', 0)
                    print(f"   추천 목표 범위: {conservative:.6f}원 ~ {aggressive:.6f}원")
            
            # 간단한 지지/저항선 (원시 데이터)
            strategy_data['price_levels'] = self._get_simple_price_levels(
                pd.DataFrame(market_data.get('day', []))
            )
            
            return strategy_data
            
        except Exception as e:
            print(f"Error getting raw strategy data for {ticker}: {e}")
            return None

    # "ATR 기반 동적 목표가를 계산하는 메서드" (인자: self, strategy_data, current_price)
    def _calculate_atr_based_targets(self, strategy_data: Dict[str, Any], current_price: float) -> Optional[Dict[str, Any]]:
        try:
            # 일봉 ATR 데이터 추출
            day_analysis = strategy_data.get('day_analysis', {})
            daily_atr_krw = day_analysis.get('indicators', {}).get('atr', 0)
            daily_atr_percentage = day_analysis.get('indicators', {}).get('atr_percentage', 0)
            
            # ATR 데이터가 없거나 유효하지 않으면 None 반환
            if daily_atr_krw <= 0 or current_price <= 0:
                print(f"⚠️ ATR 데이터 없음 또는 무효: ATR={daily_atr_krw}, Price={current_price}")
                return None
            
            # ATR 기반 목표가 계산
            atr_analysis = {
                'daily_atr_krw': daily_atr_krw,
                'daily_atr_percentage': daily_atr_percentage,
                'atr_multipliers': {
                    'conservative': 1.0,    # ATR × 1.0 (보수적)
                    'balanced': 1.3,        # ATR × 1.3 (균형)
                    'aggressive': 1.6,      # ATR × 1.6 (적극적)
                    'maximum': 2.0          # ATR × 2.0 (최대)
                }
            }
            
            # 목표가 범위 계산
            multipliers = atr_analysis['atr_multipliers']
            recommended_targets = {}
            
            for target_type, multiplier in multipliers.items():
                target_price = current_price + (daily_atr_krw * multiplier)
                target_percentage = ((target_price - current_price) / current_price) * 100
                
                recommended_targets[f'{target_type}_target'] = target_price
                recommended_targets[f'{target_type}_percentage'] = target_percentage
            
            atr_analysis['recommended_target_range'] = recommended_targets
            
            # 변동성 분류
            if daily_atr_percentage < 2.0:
                volatility_class = "LOW"
                recommended_multiplier = 1.0
            elif daily_atr_percentage < 5.0:
                volatility_class = "MEDIUM"
                recommended_multiplier = 1.3
            elif daily_atr_percentage < 10.0:
                volatility_class = "HIGH"
                recommended_multiplier = 1.6
            else:
                volatility_class = "EXTREME"
                recommended_multiplier = 1.2 
            
            atr_analysis.update({
                'volatility_classification': volatility_class,
                'recommended_multiplier': recommended_multiplier,
                'recommended_target_price': current_price + (daily_atr_krw * recommended_multiplier),
                'recommended_target_percentage': (daily_atr_krw * recommended_multiplier / current_price) * 100
            })
            
            # 4시간봉 ATR과 비교
            h4_analysis = strategy_data.get('minute240_analysis', {})
            h4_atr = h4_analysis.get('indicators', {}).get('atr', 0)
            
            if h4_atr > 0:
                atr_ratio = daily_atr_krw / h4_atr if h4_atr > 0 else 1.0
                atr_analysis['atr_consistency'] = {
                    'h4_atr_krw': h4_atr,
                    'daily_to_h4_ratio': atr_ratio,
                    'consistency_level': "STABLE" if 3.0 <= atr_ratio <= 7.0 else "VOLATILE"
                }
            
            return atr_analysis
            
        except Exception as e:
            print(f"❌ ATR 기반 목표가 계산 오류: {e}")
            return None

    # "간단한 가격 레벨(지지/저항선)을 계산하는 메서드" (인자: self, df)
    def _get_simple_price_levels(self, df: pd.DataFrame) -> Dict[str, float]:
        try:
            if df.empty or len(df) < 5:
                return {}
            
            # 최근 30일 데이터
            recent_data = df.tail(min(30, len(df)))

            levels = {
                "high_30d": float(recent_data['high'].max()),
                "low_30d": float(recent_data['low'].min()),
                "avg_30d": float(recent_data['close'].mean()),
                "current": float(df['close'].iloc[-1])
            }

            if len(df) >= 10:
                recent_10d = df.tail(10)
                levels.update({
                    "high_10d": float(recent_10d['high'].max()),
                    "low_10d": float(recent_10d['low'].min()),
                    "avg_10d": float(recent_10d['close'].mean())
                })
            
            return levels
            
        except Exception as e:
            print(f"Error calculating price levels: {e}")
            return {}
    
    # "GPT 응답을 DB 저장 형식으로 변환하는 메서드" (인자: self, strategy, coin_data)
    def _prepare_db_strategy(self, strategy: Dict[str, Any], coin_data: Dict[str, Any]) -> Dict[str, Any]:

        try:
            # GPT 응답에서 필요한 데이터 추출
            trading_params = strategy.get('trading_parameters', {})
            
            # 가격 정밀도 처리 함수
            def format_price_precision(price: float, ticker: str) -> float:
                try:
                    price = float(price)
                    
                    # 업비트 공식 호가 단위 규칙
                    if price >= 2000000:
                        return float(int(price / 1000) * 1000)
                    elif price >= 1000000:
                        return float(int(price / 1000) * 1000)
                    elif price >= 500000:
                        return float(int(price / 500) * 500)
                    elif price >= 100000:
                        return float(int(price / 100) * 100)
                    elif price >= 50000:
                        return float(int(price / 50) * 50)
                    elif price >= 10000:
                        return float(int(price / 10) * 10)
                    elif price >= 5000:
                        return float(int(price / 5) * 5)
                    elif price >= 1000:
                        return float(int(price))
                    elif price >= 100:
                        return float(int(price))
                    elif price >= 10:
                        return round(price * 10) / 10
                    elif price >= 1:
                        return round(price * 100) / 100
                    elif price >= 0.1:
                        return round(price * 1000) / 1000
                    elif price >= 0.01:
                        return round(price * 10000) / 10000
                    elif price >= 0.001:
                        return round(price * 100000) / 100000
                    elif price >= 0.0001:
                        return round(price * 1000000) / 1000000
                    elif price >= 0.00001:
                        return round(price * 10000000) / 10000000
                    else:
                        return round(price * 100000000) / 100000000

                except (ValueError, TypeError):
                    print(f"⚠️ 가격 변환 오류: {price}")
                    return float(price) if price else 0.0
            
            ticker = trading_params.get('coin_ticker', '')
            
            # 가격 정밀도 적용
            entry_price = format_price_precision(trading_params.get('entry_price', 0), ticker)
            target_price = format_price_precision(trading_params.get('target_price', 0), ticker)
            stop_loss_price = format_price_precision(trading_params.get('stop_loss_price', 0), ticker)
            
            # 가격 검증
            if entry_price <= 0 or target_price <= 0 or stop_loss_price <= 0:
                print(f"⚠️ 유효하지 않은 가격: 진입({entry_price}), 목표({target_price}), 손절({stop_loss_price})")
            
            if target_price <= entry_price:
                print(f"⚠️ 목표가가 진입가보다 낮음: 목표({target_price}) <= 진입({entry_price})")
            
            if stop_loss_price >= entry_price:
                print(f"⚠️ 손절가가 진입가보다 높음: 손절({stop_loss_price}) >= 진입({entry_price})")
            
            db_strategy = {
                'coin_ticker': ticker,
                'entry_price': entry_price,
                'target_price': target_price,
                'stop_loss_price': stop_loss_price,
                'entry_reason': trading_params.get('entry_reason', ''),
                'target_reason': trading_params.get('target_reason', ''),
                'stop_loss_reason': trading_params.get('stop_loss_reason', ''),
                'market_data': coin_data
            }
            
            print(f"📊 가격 정밀도 적용 완료:")
            print(f"   진입가: {entry_price}")
            print(f"   목표가: {target_price}")
            print(f"   손절가: {stop_loss_price}")
            
            return db_strategy
            
        except Exception as e:
            print(f"Error preparing DB strategy: {e}")
            return {}

    # "거래 복구용 GPT 분석 컨텍스트를 수집하는 메서드" (인자: self, selected_coin, deep_analysis, strategy)
    def _collect_gpt_context(self, selected_coin: str, deep_analysis: Dict[str, Any], strategy: Dict[str, Any]) -> Dict[str, Any]:
        try:
            context = {
                'timestamp': datetime.now().isoformat(),
                'selected_coin': selected_coin,
                'phase_contexts': {}
            }

            cache_status = self.gpt.get_cache_status()

            if hasattr(self.gpt, 'response_cache'):
                contexts = self.gpt.response_cache.get('contexts', {})
                
                # Phase 1 컨텍스트
                if 'phase1' in contexts:
                    context['phase_contexts']['phase1'] = contexts['phase1']
                
                # Phase 2 컨텍스트 및 심층 분석 결과
                if 'phase2' in contexts:
                    context['phase_contexts']['phase2'] = contexts['phase2']
                
                if deep_analysis:
                    context['deep_analysis_summary'] = {
                        'selected_coin': deep_analysis.get('final_selection', {}).get('selected_coin'),
                        'confidence_score': deep_analysis.get('final_selection', {}).get('confidence_score'),
                        'selection_rationale': deep_analysis.get('final_selection', {}).get('selection_rationale', '')[:200]
                    }
                
                # Phase 3 컨텍스트
                if 'phase3' in contexts:
                    context['phase_contexts']['phase3'] = contexts['phase3']
            
            # 전략 핵심 정보
            if strategy and 'trading_parameters' in strategy:
                params = strategy['trading_parameters']
                context['strategy_summary'] = {
                    'coin_ticker': params.get('coin_ticker'),
                    'entry_price': params.get('entry_price'),
                    'target_price': params.get('target_price'),
                    'stop_loss_price': params.get('stop_loss_price'),
                    'expected_duration_hours': params.get('expected_duration_hours')
                }
            
            print(f"📝 GPT 컨텍스트 수집 완료 (Phase 수: {len(context['phase_contexts'])})")
            
            return context
            
        except Exception as e:
            print(f"⚠️ GPT 컨텍스트 수집 오류: {e}")
            return {}

    # "수립된 전략 결과를 포맷팅하여 출력하는 메서드" (인자: self, strategy, has_memory)
    def _display_strategy_result(self, strategy: Dict[str, Any], has_memory: bool):

        try:
            trading_params = strategy.get('trading_parameters', {})
            execution_plan = strategy.get('altcoin_execution_plan', {})
            altcoin_risk = strategy.get('altcoin_risk_matrix', {})

            def format_price_display(price):
                try:
                    price = float(price)
                    if price >= 1000:
                        return f"{price:,.2f}원"
                    elif price >= 1:
                        return f"{price:.4f}원"
                    else:
                        return f"{price:.6f}원"
                except:
                    return f"{price}원"
            
            entry_price = trading_params.get('entry_price', 0)
            target_price = trading_params.get('target_price', 0)
            stop_loss_price = trading_params.get('stop_loss_price', 0)
            
            print(f"\n📋 거래 전략 수립 완료 (ID: {strategy.get('trade_id')})")
            print(f"   💰 코인: {trading_params.get('coin_ticker')}")
            print(f"   📈 진입가: {format_price_display(entry_price)}")
            print(f"   🎯 목표가: {format_price_display(target_price)}")
            print(f"   🛑 손절가: {format_price_display(stop_loss_price)}")
            print(f"   ⏰ 예상시간: {trading_params.get('expected_duration_hours', 0):.1f}시간")
            
            # 수익률 계산
            if entry_price > 0:
                target_profit_rate = (target_price - entry_price) / entry_price * 100
                stop_loss_rate = (stop_loss_price - entry_price) / entry_price * 100
                print(f"   📊 예상 수익률: +{target_profit_rate:.2f}% / {stop_loss_rate:.2f}%")
            
            # 실행 계획 정보
            btc_dependency = execution_plan.get('btc_dependency_level', 'UNKNOWN')
            success_prob = execution_plan.get('success_probability', 0)
            catalyst = execution_plan.get('individual_catalyst', 'N/A')
            
            print(f"\n🎯 실행 계획:")
            print(f"   🔗 BTC 의존도: {btc_dependency}")
            print(f"   📊 성공 확률: {success_prob:.0f}%")
            print(f"   💡 핵심 동력: {catalyst[:50]}...")
            
            # 리스크 매트릭스
            independence_score = altcoin_risk.get('btc_independence_score', 50)
            print(f"   🏆 독립성 점수: {independence_score:.0f}/100")
            
            # 교훈 활용 여부
            memory_applied = execution_plan.get('memory_applied', '')
            if memory_applied and has_memory:
                print(f"   🧠 교훈 반영: {memory_applied[:100]}...")
            elif has_memory:
                print(f"   순수 데이터 기반 전략")
            
            print(f"\n" + "="*50)
            
        except Exception as e:
            print(f"Error displaying strategy result: {e}")