# core/strategy_maker.py
# "Phase 3: GPT-5 자율 전략 수립 - V14: 2-Target Scaling Out"

import pandas as pd
from typing import Dict, Any, Optional
from data.upbit_client import UpbitClient
from data.indicators import TechnicalIndicators
from data.database import TradeDatabase
from ai.gpt_client import get_gpt_client
from datetime import datetime  

class StrategyMaker:
    
    def __init__(self):
        self.upbit = UpbitClient()
        self.indicators = TechnicalIndicators()
        self.gpt = get_gpt_client()
        self.db = TradeDatabase()
    
    def create_trading_strategy(self, selected_coin: str, phase1_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        print(f"📋 Phase 3: {selected_coin} GPT-5 자율 전략 수립...")
        
        # 1. 선정된 코인의 최신 데이터 수집
        coin_data = self._get_enhanced_strategy_data(selected_coin)
        if not coin_data:
            return {"error": f"{selected_coin} 데이터 수집 실패"}
        
        print(f"   📊 {selected_coin} 강화된 데이터 수집 완료")
        
        # 2. GPT-5 자율 전략 수립
        strategy = self.gpt.create_strategy_phase3(
            coin_data, 
            selected_coin,
            phase1_analysis
        )
        
        if strategy.get('error'):
            print(f"❌ 전략 수립 실패: {strategy['error']}")
            return strategy
        
        # 3. DB 저장용 데이터 준비
        db_strategy = self._prepare_db_strategy(strategy, coin_data)
        
        # 4. 거래 계획 DB 저장
        trade_id = self.db.insert_trade_plan(db_strategy)
        strategy['trade_id'] = trade_id
        
        # 5. 결과 출력
        self._display_strategy_result(strategy)
        
        return strategy
    
    def _get_enhanced_strategy_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        try:
            # 다중 타임프레임 데이터 수집
            market_data = self.upbit.get_market_data(
                ticker, 
                ["minute5", "minute15", "minute60", "minute240", "day"]
            )
            
            current_price = self.upbit.get_current_price(ticker)
            
            strategy_data = {
                "ticker": ticker,
                "current_price": current_price,
                "timestamp": datetime.now().isoformat()
            }
            
            # 각 타임프레임별 지표 계산
            for interval, data in market_data.items():
                if interval == "ticker" or not data:
                    continue
                
                df = pd.DataFrame(data)
                if df.empty:
                    continue
                
                # 강화된 지표 계산 (key_levels 포함)
                indicators = self.indicators.calculate_all_indicators(df)
                
                strategy_data[f"{interval}_analysis"] = {
                    "candles": data[-20:],  # 최근 20개 캔들
                    "indicators": indicators,
                    "key_levels": indicators.get('key_levels', {}),  # 주요 레벨
                    "divergences": indicators.get('divergences', {}),
                    "volume_ratio": indicators.get('volume_ratio', 1.0)
                }
                
                # 1시간봉 기준 핵심 지표 출력
                if interval == "minute60":
                    self._log_key_indicators(ticker, indicators)
                    # 1시간봉 key_levels를 최상위로도 저장
                    strategy_data['key_levels'] = indicators.get('key_levels', {})
            
            # ATR 기반 변동성 분석
            atr_analysis = self._analyze_volatility_for_strategy(strategy_data)
            if atr_analysis:
                strategy_data['volatility_analysis'] = atr_analysis
            
            # 오더북 데이터 추가 (Phase 3에서만)
            print(f"\n📊 오더북 데이터 수집...")
            orderbook = self.upbit.get_orderbook(ticker)
            if orderbook:
                orderbook_analysis = self._analyze_orderbook(orderbook, current_price)
                strategy_data['orderbook_analysis'] = orderbook_analysis
                
                # 오더북 핵심 지표 출력
                if orderbook_analysis:
                    print(f"   💹 오더북 분석 완료:")
                    print(f"      스프레드: {orderbook_analysis.get('spread', 0):.3f}%")
                    print(f"      매수/매도: {orderbook_analysis.get('bid_ask_ratio', 1):.2f}")
                    print(f"      불균형: {orderbook_analysis.get('order_imbalance', 0):.1f}%")
                    print(f"      압력: {orderbook_analysis.get('pressure', 'NEUTRAL')}")
                    
                    # 호가벽 정보
                    bid_walls = orderbook_analysis.get('bid_walls', [])
                    ask_walls = orderbook_analysis.get('ask_walls', [])
                    if bid_walls:
                        wall = bid_walls[0]
                        print(f"      🧱 매수벽: {wall['price']:,.0f}원 ({wall['ratio']:.1f}배)")
                    if ask_walls:
                        wall = ask_walls[0]
                        print(f"      🧱 매도벽: {wall['price']:,.0f}원 ({wall['ratio']:.1f}배)")
            else:
                print(f"   ⚠️ 오더북 데이터 수집 실패")
            
            return strategy_data
            
        except Exception as e:
            print(f"❌ 데이터 수집 오류: {e}")
            return None

    def _log_key_indicators(self, ticker: str, indicators: Dict):
        print(f"\n🎯 {ticker} 핵심 지표:")
        
        # 추세
        adx = indicators.get('adx', 0)
        print(f"   ADX: {adx:.1f} (추세 강도)")
        
        # 모멘텀
        rsi = indicators.get('rsi_14', 50)
        print(f"   RSI: {rsi:.1f}")
        
        # 다이버전스
        divergences = indicators.get('divergences', {})
        if divergences.get('rsi_divergence'):
            print(f"   🔄 RSI 다이버전스: {divergences['rsi_divergence']}")
        
        # 거래량
        volume_ratio = indicators.get('volume_ratio', 1)
        print(f"   거래량 비율: {volume_ratio:.2f}x")
        
        # 주요 레벨 (indicators.py에서 계산된 값)
        key_levels = indicators.get('key_levels', {})
        if key_levels:
            print(f"   📍 고점: {key_levels.get('recent_high', 0):,.0f}")
            print(f"   📍 저점: {key_levels.get('recent_low', 0):,.0f}")
            print(f"   📍 위치: {key_levels.get('price_position', 50):.1f}%")
    
    def _analyze_volatility_for_strategy(self, data: Dict) -> Dict:
        try:
            # 여러 타임프레임 ATR 수집
            atr_values = {}
            
            for timeframe in ['minute60', 'minute240', 'day']:
                analysis = data.get(f'{timeframe}_analysis', {})
                indicators = analysis.get('indicators', {})
                
                atr = indicators.get('atr_14', 0)
                atr_pct = indicators.get('atr_14_pct', 0)
                
                if atr > 0:
                    atr_values[timeframe] = {
                        'atr': atr,
                        'atr_pct': atr_pct
                    }
            
            if not atr_values:
                return None
            
            # 변동성 분류
            daily_atr_pct = atr_values.get('day', {}).get('atr_pct', 0)
            
            if daily_atr_pct < 2:
                volatility_level = "LOW"
                recommended_position = 70  # 70% 포지션
            elif daily_atr_pct < 5:
                volatility_level = "MEDIUM"
                recommended_position = 50  # 50% 포지션
            elif daily_atr_pct < 10:
                volatility_level = "HIGH"
                recommended_position = 30  # 30% 포지션
            else:
                volatility_level = "EXTREME"
                recommended_position = 20  # 20% 포지션
            
            return {
                'volatility_level': volatility_level,
                'daily_atr_pct': daily_atr_pct,
                'recommended_position_pct': recommended_position,
                'atr_by_timeframe': atr_values
            }
            
        except Exception as e:
            print(f"⚠️ 변동성 분석 오류: {e}")
            return None
    
    def _analyze_orderbook(self, orderbook: Dict, current_price: float) -> Dict:
        """오더북 분석 - Phase 3 전용"""
        try:
            units = orderbook.get('orderbook_units', [])
            
            if not units:
                return {}
            
            # 상위 5호가만 분석 (깊이 있는 분석)
            top5 = units[:5]
            
            # 1. 스프레드 계산
            best_ask = float(top5[0]['ask_price'])
            best_bid = float(top5[0]['bid_price'])
            spread = (best_ask - best_bid) / current_price * 100
            
            # 2. 호가별 누적 이량
            bid_volume = sum(float(u['bid_size']) for u in top5)
            ask_volume = sum(float(u['ask_size']) for u in top5)
            
            # 상위 1호가만
            bid_volume_1 = float(top5[0]['bid_size'])
            ask_volume_1 = float(top5[0]['ask_size'])
            
            # 3. 매수/매도 비율
            ratio = bid_volume / ask_volume if ask_volume > 0 else 1.0
            ratio_1 = bid_volume_1 / ask_volume_1 if ask_volume_1 > 0 else 1.0
            
            # 4. 불균형 점수 (-100 ~ +100)
            imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume) * 100 if (bid_volume + ask_volume) > 0 else 0
            
            # 5. 압력 판단
            if imbalance > 30:
                pressure = 'STRONG_BUY'
            elif imbalance > 10:
                pressure = 'BUY'
            elif imbalance < -30:
                pressure = 'STRONG_SELL'
            elif imbalance < -10:
                pressure = 'SELL'
            else:
                pressure = 'NEUTRAL'
            
            # 6. 호가벽 감지 (평균의 3배 이상)
            avg_bid = bid_volume / 5 if len(top5) == 5 else bid_volume / len(top5)
            avg_ask = ask_volume / 5 if len(top5) == 5 else ask_volume / len(top5)
            
            bid_walls = []
            ask_walls = []
            
            for i, u in enumerate(top5):
                bid_size = float(u['bid_size'])
                ask_size = float(u['ask_size'])
                
                # 매수벽 감지
                if bid_size > avg_bid * 3:
                    bid_walls.append({
                        'price': float(u['bid_price']),
                        'volume': bid_size,
                        'ratio': bid_size / avg_bid,
                        'level': i + 1  # 몇 번째 호가인지
                    })
                
                # 매도벽 감지
                if ask_size > avg_ask * 3:
                    ask_walls.append({
                        'price': float(u['ask_price']),
                        'volume': ask_size,
                        'ratio': ask_size / avg_ask,
                        'level': i + 1
                    })
            
            # 7. 가중 중간가 (거래량 가중)
            weighted_bid = sum(float(u['bid_price']) * float(u['bid_size']) for u in top5) / bid_volume if bid_volume > 0 else best_bid
            weighted_ask = sum(float(u['ask_price']) * float(u['ask_size']) for u in top5) / ask_volume if ask_volume > 0 else best_ask
            weighted_mid = (weighted_bid + weighted_ask) / 2
            
            return {
                'spread': spread,
                'spread_krw': best_ask - best_bid,
                'bid_ask_ratio': ratio,
                'bid_ask_ratio_1': ratio_1,  # 1호가만
                'order_imbalance': imbalance,
                'pressure': pressure,
                'bid_walls': bid_walls,
                'ask_walls': ask_walls,
                'bid_volume_total': bid_volume,
                'ask_volume_total': ask_volume,
                'weighted_mid_price': weighted_mid,
                'best_bid': best_bid,
                'best_ask': best_ask
            }
            
        except Exception as e:
            print(f"⚠️ 오더북 분석 오류: {e}")
            return {}

    def _prepare_db_strategy(self, strategy: Dict, coin_data: Dict) -> Dict:
        try:
            trading_params = strategy.get('trading_parameters', {})
            
            # 업비트 호가 단위 적용
            def apply_price_unit(price: float) -> float:
                if price <= 0:
                    return 0
                    
                if price >= 2000000:
                    return float(int(price / 1000) * 1000)
                elif price >= 1000000:
                    return float(int(price / 500) * 500)
                elif price >= 500000:
                    return float(int(price / 100) * 100)
                elif price >= 100000:
                    return float(int(price / 50) * 50)
                elif price >= 10000:
                    return float(int(price / 10) * 10)
                elif price >= 1000:
                    return float(int(price / 5) * 5)
                elif price >= 100:
                    return float(int(price))
                elif price >= 10:
                    return round(price, 1)
                elif price >= 1:
                    return round(price, 2)
                else:
                    return round(price, 4)
            
            ticker = trading_params.get('coin_ticker', '')
            
            # V14: 2개 목표가 처리
            entry_price = apply_price_unit(trading_params.get('entry_price', 0))
            target_price_1 = apply_price_unit(trading_params.get('target_price_1', 0))
            target_price_2 = apply_price_unit(trading_params.get('target_price_2', 0))
            stop_loss_price = apply_price_unit(trading_params.get('stop_loss_price', 0))
            
            # 가격 검증 (1원 버그 방지)
            current_price = coin_data.get('current_price', 0)
            if entry_price < 10 and current_price > 100:
                print(f"⚠️ 가격 오류 감지! 재계산...")
                entry_price = apply_price_unit(current_price * 1.001)
                target_price_1 = apply_price_unit(current_price * 1.025)  # 1차: +2.5%
                target_price_2 = apply_price_unit(current_price * 1.05)   # 2차: +5%
                stop_loss_price = apply_price_unit(current_price * 0.98)
            
            db_strategy = {
                'coin_ticker': ticker,
                'entry_price': entry_price,
                'target_price_1': target_price_1,      # V14: 1차 목표
                'target_price_2': target_price_2,      # V14: 2차 목표
                'stop_loss_price': stop_loss_price,
                'target_split_ratio': trading_params.get('target_split_ratio', 0.7),  # V14
                'entry_reason': trading_params.get('entry_reason', ''),
                'target_reason': trading_params.get('target_reason', ''),
                'stop_loss_reason': trading_params.get('stop_loss_reason', ''),
                'position_size_percent': trading_params.get('position_size_percent', 50),
                'market_data': coin_data
            }
            
            return db_strategy
            
        except Exception as e:
            print(f"❌ DB 데이터 준비 오류: {e}")
            return {}
    
    def _display_strategy_result(self, strategy: Dict):
        try:
            params = strategy.get('trading_parameters', {})
            risk = strategy.get('risk_assessment', {})
            
            def format_price(price):
                if price >= 1000:
                    return f"{price:,.0f}원"
                elif price >= 10:
                    return f"{price:.1f}원"
                elif price >= 1:
                    return f"{price:.2f}원"
                else:
                    return f"{price:.4f}원"
            
            entry = params.get('entry_price', 0)
            target1 = params.get('target_price_1', 0)  # V14
            target2 = params.get('target_price_2', 0)  # V14
            stop = params.get('stop_loss_price', 0)
            position_size = params.get('position_size_percent', 50)
            split_ratio = params.get('target_split_ratio', 0.7)  # V14
            
            print(f"\n📋 GPT-5 자율 전략 완성 (V14: 2-Target)")
            print(f"   💰 코인: {params.get('coin_ticker')}")
            print(f"   📈 진입가: {format_price(entry)} (딜레이 고려)")
            
            # V14: 2개 목표가 표시
            if target1 > 0:
                target1_return = (target1 - entry) / entry * 100 if entry > 0 else 0
                print(f"   🎯 1차 목표: {format_price(target1)} (+{target1_return:.2f}%) [{split_ratio*100:.0f}% 청산]")
            
            if target2 > 0:
                target2_return = (target2 - entry) / entry * 100 if entry > 0 else 0
                print(f"   🚀 2차 목표: {format_price(target2)} (+{target2_return:.2f}%) [{(1-split_ratio)*100:.0f}% 추격]")
            
            print(f"   🛑 손절가: {format_price(stop)}")
            print(f"   💼 포지션: {position_size}% (자율 결정)")
            
            # 수익률 계산
            if entry > 0 and target1 > 0:
                risk_return = (stop - entry) / entry * 100
                
                # V14: 혼합 수익률 계산
                if target2 > 0:
                    avg_return = (target1_return * split_ratio) + (target2_return * (1 - split_ratio))
                    rr_ratio = abs(avg_return / risk_return) if risk_return != 0 else 0
                    
                    print(f"\n📊 리스크/리워드 (V14 혼합):")
                    print(f"   예상 수익: +{avg_return:.2f}% (가중평균)")
                    print(f"   리스크: {risk_return:.2f}%")
                    print(f"   R:R 비율: 1:{rr_ratio:.1f}")
                else:
                    rr_ratio = abs(target1_return / risk_return) if risk_return != 0 else 0
                    print(f"\n📊 리스크/리워드:")
                    print(f"   예상 수익: +{target1_return:.2f}%")
                    print(f"   리스크: {risk_return:.2f}%")
                    print(f"   R:R 비율: 1:{rr_ratio:.1f}")
            
            # 실행 긴급도
            urgency = risk.get('execution_urgency', 'MEDIUM')
            print(f"\n⚡ 실행 긴급도: {urgency}")
            
            if urgency == "HIGH":
                print("   → 즉시 진입 권장")
            elif urgency == "LOW":
                print("   → 인내심 있게 대기")
            
            # V14: 분할 익절 전략 설명
            print(f"\n💡 V14 Scaling Out 전략:")
            print(f"   1️⃣ {split_ratio*100:.0f}% 물량은 1차 목표에서 안전하게 익절")
            print(f"   2️⃣ {(1-split_ratio)*100:.0f}% 물량은 손절가를 본절로 이동 후 추격")
            print(f"   3️⃣ 최악의 경우 1차 목표 수익만 확보, 최선의 경우 잭팟")
            
            print(f"\n" + "="*50)
            
        except Exception as e:
            print(f"❌ 결과 출력 오류: {e}")