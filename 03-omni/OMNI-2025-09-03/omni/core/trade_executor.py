# core/trade_executor.py
# "Phase 4: 수립된 전략에 따라 실제 거래를 실행하고 모니터링하는 거래 실행 파일"

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from data.upbit_client import UpbitClient
from data.database import TradeDatabase
from config.settings import settings
import traceback

class TradeExecutor:

    # "TradeExecutor 클래스를 초기화하고 이전 거래를 복구하는 메서드" (인자: self)
    def __init__(self):
        self.upbit = UpbitClient()
        self.db = TradeDatabase()
        self.active_trade = None
        self.monitoring_thread = None
        self.should_stop = False
        self._recover_active_trade()
    
    # "현재 시장 추세를 조회하는 메서드" (인자: self)
    def get_current_market_regime(self) -> str:
        try:
            from core.market_analyzer import MarketAnalyzer
            analyzer = MarketAnalyzer()
            regime = analyzer.get_market_regime()
            
            if settings.POSITION_SIZE_LOGGING:
                print(f"📊 현재 시장 추세: {regime}")
            
            return regime
        except Exception as e:
            print(f"❌ 시장 추세 조회 실패: {e}")
            return "SIDEWAYS"

    # "시장 추세 기반 동적 포지션 크기를 계산하는 메서드" (인자: self, market_regime)
    def calculate_dynamic_position_size(self, market_regime: str) -> float:
        try:
            # 기본 사용 가능 잔고 비율
            base_ratio = settings.AVAILABLE_BALANCE_RATIO
            
            # 시장 추세별 배수 적용
            regime_multipliers = {
                "BULL_TREND": settings.POSITION_SIZE_BULL,      
                "SIDEWAYS": settings.POSITION_SIZE_SIDEWAYS,    
                "BEAR_TREND": settings.POSITION_SIZE_BEAR       
            }

            regime_multiplier = regime_multipliers.get(market_regime, settings.POSITION_SIZE_SIDEWAYS)

            final_ratio = base_ratio * regime_multiplier

            final_ratio = max(settings.MIN_POSITION_SIZE, min(settings.MAX_POSITION_SIZE, final_ratio))

            if settings.POSITION_SIZE_LOGGING:
                print(f"💰 동적 포지션 크기 계산:")
                print(f"   📊 시장 추세: {market_regime}")
                print(f"   🔢 기본 비율: {base_ratio:.1%}")
                print(f"   ⚡ 추세 배수: {regime_multiplier:.1%}")
                print(f"   🎯 최종 비율: {final_ratio:.1%}")
            
            return final_ratio
            
        except Exception as e:
            print(f"❌ 동적 포지션 크기 계산 오류: {e}")
            return settings.AVAILABLE_BALANCE_RATIO 

    # "프로그램 재시작시 활성 거래를 복구하는 메서드" (인자: self)
    def _recover_active_trade(self):
        try:
            print("🔄 이전 거래 상태 복구 시도 중...")

            recent_trades = self.db.get_recent_trades(limit=1)
            
            if not recent_trades:
                print("✅ 복구할 거래 없음 (깨끗한 시작)")
                return
            
            last_trade = recent_trades[0]
            trade_status = last_trade.get('status', '')
            trade_id = last_trade.get('trade_id')

            if trade_status not in ['ACTIVE', 'WAITING_ENTRY']:
                print(f"✅ 복구할 활성 거래 없음 (마지막 상태: {trade_status})")
                return
            
            print(f"🎯 활성 거래 발견! 상태: {trade_status}")
            print(f"   코인: {last_trade.get('coin_ticker', 'N/A')}")
            print(f"   시작: {last_trade.get('timestamp', 'N/A')}")

            full_trade_data = self.db.get_trade_with_context(trade_id) if hasattr(self.db, 'get_trade_with_context') else None
            
            if full_trade_data and full_trade_data.get('gpt_context'):
                print("📝 GPT 컨텍스트 발견 - 복구 중...")
                gpt_context = full_trade_data['gpt_context']

                try:
                    from ai.gpt_client import get_gpt_client
                    gpt = get_gpt_client()
                    
                    if hasattr(gpt, 'restore_context_for_recovery'):
                        gpt.restore_context_for_recovery(gpt_context)
                        print("✅ GPT 컨텍스트 복구 완료")
                    else:
                        print("⚠️ GPT 컨텍스트 복구 메서드 없음")
                except Exception as e:
                    print(f"⚠️ GPT 컨텍스트 복구 실패: {e}")
            else:
                print("⚠️ GPT 컨텍스트 없음 - 기본 복구 진행")

            recovered_strategy = self._reconstruct_strategy_from_db(last_trade)
            
            if not recovered_strategy:
                print("❌ 전략 재구성 실패 - 수동 확인 필요")
                return

            self.active_trade = {
                'trade_id': last_trade['trade_id'],
                'strategy': recovered_strategy,
                'status': trade_status,
                'start_timestamp': datetime.fromisoformat(last_trade['timestamp']) if last_trade.get('timestamp') else datetime.now(),
                'target_achievement_hours': recovered_strategy.get('trading_parameters', {}).get('expected_duration_hours', 12),
                'planned_exit_timestamp': None,
                'entry_order_id': None,
                'actual_entry_price': last_trade.get('actual_entry_price'),
                'actual_volume': last_trade.get('actual_volume'),
                'actual_entry_amount': None,
                'entry_fee': last_trade.get('entry_fee'),
                'entry_timestamp': datetime.fromisoformat(last_trade['entry_timestamp']) if last_trade.get('entry_timestamp') else None,
                'has_recovered_context': bool(full_trade_data and full_trade_data.get('gpt_context'))  # 🆕 복구 플래그
            }

            if trade_status == 'ACTIVE':
                print(f"   💰 진입가: {last_trade.get('actual_entry_price', 0):,.4f}원")
                print(f"   🎯 목표가: {last_trade.get('target_price', 0):,.4f}원")
                print(f"   🛑 손절가: {last_trade.get('stop_loss_price', 0):,.4f}원")
                print(f"   📊 보유량: {last_trade.get('actual_volume', 0):.8f}개")

                current_price = self.upbit.get_current_price(last_trade['coin_ticker'])
                if current_price and last_trade.get('actual_entry_price'):
                    unrealized_pnl = (current_price - last_trade['actual_entry_price']) / last_trade['actual_entry_price'] * 100
                    print(f"   📈 현재가: {current_price:,.4f}원 (미실현: {unrealized_pnl:+.2f}%)")

            print("🚀 거래 모니터링 재시작")
            self._start_monitoring()
            
            print("✅ 거래 상태 복구 완료!")
            
        except Exception as e:
            print(f"❌ 거래 복구 중 오류: {e}")
            print("⚠️ 수동으로 거래 상태를 확인해주세요")

    # "DB 데이터로부터 거래 전략을 재구성하는 메서드" (인자: self, trade_data)
    def _reconstruct_strategy_from_db(self, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            trading_parameters = {
                'coin_ticker': trade_data.get('coin_ticker', ''),
                'entry_price': trade_data.get('entry_price', 0),
                'target_price': trade_data.get('target_price', 0),
                'stop_loss_price': trade_data.get('stop_loss_price', 0),
                'entry_reason': trade_data.get('entry_reason', ''),
                'target_reason': trade_data.get('target_reason', ''),
                'stop_loss_reason': trade_data.get('stop_loss_reason', ''),
                'expected_duration_hours': 12  
            }

            reconstructed_strategy = {
                'trade_id': trade_data['trade_id'],
                'trading_parameters': trading_parameters,
                'altcoin_execution_plan': {
                    'btc_dependency_level': 'LOW',
                    'individual_catalyst': '복구된 거래',
                    'independent_profit_driver': '이전 분석 기반',
                    'success_probability': 75,
                    'memory_applied': '거래 복구'
                },
                'altcoin_risk_matrix': {
                    'individual_coin_risk': 50,
                    'btc_independence_score': 70
                }
            }
            
            return reconstructed_strategy
            
        except Exception as e:
            print(f"❌ 전략 재구성 오류: {e}")
            return None

    # "활성 거래 요약 정보를 반환하는 메서드" (인자: self)
    def get_active_trade_summary(self) -> str:
        """활성 거래 요약 정보 반환"""
        if not self.active_trade:
            return None
            
        status = self.active_trade.get('status', '')
        strategy = self.active_trade.get('strategy', {})
        params = strategy.get('trading_parameters', {})
        ticker = params.get('coin_ticker', '')
        
        if status == 'WAITING_ENTRY':
            entry_price = params.get('entry_price', 0)

            start_time = self.active_trade.get('start_timestamp', datetime.now())
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            
            elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
            remaining_hours = max(0, settings.ENTRY_WAIT_TIMEOUT_HOURS - elapsed_hours)
            
            return f"{ticker} 진입 대기 중 (목표: {entry_price:,.0f}원, 남은시간: {remaining_hours:.1f}시간)"
            
        elif status == 'ACTIVE':
            entry_price = self.active_trade.get('actual_entry_price', 0)
            target_price = params.get('target_price', 0)
            stop_loss = params.get('stop_loss_price', 0)

            current_price = self.upbit.get_current_price(ticker)
            if current_price:
                profit_rate = ((current_price - entry_price) / entry_price) * 100
                return f"{ticker} 포지션 보유 중 (수익률: {profit_rate:+.2f}%, 목표: {target_price:,.0f}원)"
            else:
                return f"{ticker} 포지션 보유 중 (목표: {target_price:,.0f}원, 손절: {stop_loss:,.0f}원)"
        
        return None

    # "업비트 호가 단위로 가격을 변환하는 메서드" (인자: self, price, ticker)
    def _get_upbit_compatible_price(self, price: float, ticker: str) -> float:

        try:
            price = float(price)

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
            print(f"⚠️ 가격 변환 중 예외 발생: {price}")
            return float(price) if price else 0.0

    # "거래 전략을 실행하고 진입 조건 모니터링을 시작하는 메서드" (인자: self, strategy)
    def execute_trade(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        if not self.upbit.private_client:
            return {"error": "거래 클라이언트가 초기화되지 않음"}

        trade_id = strategy.get('trade_id')
        trading_params = strategy.get('trading_parameters', {})
        
        ticker = trading_params.get('coin_ticker', '')
        entry_price = trading_params.get('entry_price', 0)
        target_price = trading_params.get('target_price', 0)
        stop_loss_price = trading_params.get('stop_loss_price', 0)

        target_achievement_hours = trading_params.get('expected_duration_hours', 12)
        
        if not ticker or not entry_price:
            return {"error": "거래 파라미터가 불완전함"}
        
        print(f"🎯 알트코인 진입 조건 모니터링 시작: {ticker} (ID: {trade_id})")
        print(f"   ⏰ 예상 달성 시간: {target_achievement_hours}시간")

        if isinstance(entry_price, (int, float)):
            if entry_price >= 1:
                print(f"   📈 진입 조건: {entry_price:,.4f}원 근처 도달 시")
                print(f"   🎯 목표가: {target_price:,.4f}원")
                print(f"   🛑 손절가: {stop_loss_price:,.4f}원")
            else:
                print(f"   📈 진입 조건: {entry_price:.6f}원 근처 도달 시")
                print(f"   🎯 목표가: {target_price:.6f}원")
                print(f"   🛑 손절가: {stop_loss_price:.6f}원")

        print("\n📊 시장 상황 사전 분석 중...")
        market_regime = self.get_current_market_regime()
        position_ratio = self.calculate_dynamic_position_size(market_regime)
        
        print(f"✅ 시장 분석 완료:")
        print(f"   📊 시장 추세: {market_regime}")
        print(f"   💰 계획된 포지션 크기: {position_ratio:.1%}")

        start_timestamp = datetime.now()
        planned_exit_timestamp = start_timestamp + timedelta(hours=target_achievement_hours)

        self.active_trade = {
            'trade_id': trade_id,
            'strategy': strategy,
            'status': 'WAITING_ENTRY', 
            'start_timestamp': start_timestamp,
            'target_achievement_hours': target_achievement_hours,
            'planned_exit_timestamp': planned_exit_timestamp,
            'market_regime': market_regime,
            'position_ratio': position_ratio,
            'entry_order_id': None,
            'actual_entry_price': None,
            'actual_volume': None,
            'actual_entry_amount': None,
            'entry_fee': None,
            'entry_timestamp': None
        }

        self.db.update_trade_result(trade_id, {
            'status': 'WAITING_ENTRY',
            'planned_exit_timestamp': planned_exit_timestamp.isoformat()
        })

        self._start_monitoring()
        
        print(f"\n✅ 진입 조건 모니터링 시작:")
        print(f"   ⏰ 모니터링 시작 시간: {start_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   🔍 진입가 근처 도달 시 자동 매수 실행")
        
        return {"success": True, "message": "진입 조건 모니터링 시작"}

    # "진입 조건 달성시 시장가 매수를 실행하는 메서드" (인자: self, ticker, target_price)
    def _execute_entry_order(self, ticker: str, target_price: float = None) -> Dict[str, Any]:
            """진입 조건 달성 시 즉시 시장가 매수 (동적 포지션 크기 적용)"""
            try:
                krw_balance = self.upbit.get_balance("KRW")
                if krw_balance < 5000:  
                    return {"success": False, "message": "잔고 부족 (최소 5,000원 필요)"}

                current_regime = self.active_trade.get('market_regime', 'SIDEWAYS')
                dynamic_ratio = self.active_trade.get('position_ratio', 0.57)

                available_amount = krw_balance * dynamic_ratio
                
                print(f"🚀 진입 조건 달성! 동적 포지션 시장가 매수:")
                print(f"   💰 KRW 잔고: {krw_balance:,.0f}원")
                print(f"   📊 시장 추세: {current_regime} (사전 분석)")
                print(f"   🎯 사용 금액: {available_amount:,.0f}원 ({dynamic_ratio:.1%})")

                market_order_id = self.upbit.buy_market_order(ticker, available_amount)
                
                if not market_order_id:
                    print("❌ 시장가 주문 API 호출 실패")
                    return {"success": False, "message": "시장가 주문 실패"}
                
                print(f"✅ 시장가 매수 주문 성공: {market_order_id}")
                print(f"⏳ 체결 확인 중... (완전 체결까지 대기)")
                
                # 체결 확인 - 무한 대기
                check_interval = 1 
                check_count = 0
                
                while not self.should_stop:
                    time.sleep(check_interval)
                    check_count += 1

                    order_status = self._get_order_status_safe(market_order_id)
                    
                    if not order_status:
                        print(f"⚠️ 주문 상태 조회 실패 (재시도... {check_count})")
                        continue
                    
                    state = order_status.get('state', 'unknown')
                    executed_volume = float(order_status.get('executed_volume', 0))

                    if (state == 'done' and executed_volume > 0) or \
                    (state == 'cancel' and executed_volume > 0):
                        
                        if state == 'cancel':
                            print(f"✅ 시장가 매수 부분 체결 후 자동 취소 확인 (정상 처리, 시도: {check_count}회)")
                        else:
                            print(f"✅ 시장가 매수 체결 완료! (시도: {check_count}회)")

                        execution_info = self._get_order_execution_info(market_order_id)
                        
                        if execution_info:
                            return {
                                "success": True,
                                "order_id": market_order_id,
                                "method": "MARKET_ENTRY",
                                "regime": current_regime,
                                "position_ratio": dynamic_ratio,
                                "execution_info": execution_info
                            }
                        else:
                            return {
                                "success": True,
                                "order_id": market_order_id,
                                "method": "MARKET_ENTRY",
                                "regime": current_regime,
                                "position_ratio": dynamic_ratio
                            }

                    elif state == 'cancel' and executed_volume == 0:
                        print(f"❌ 주문이 취소됨 (체결량 없음)")
                        print(f"📋 주문 상세:")
                        print(f"   - 체결량: {executed_volume}")
                        print(f"   - 남은량: {order_status.get('remaining_volume', 0)}")
                        print(f"   - 상태: {state}")
                        return {"success": False, "message": "주문 취소됨", "order_id": market_order_id}

                    elif state == 'wait':
                        if check_count % 5 == 0:
                            print(f"⏳ 주문 대기 중... (체크: {check_count}회)")
                    
                    else:
                        if check_count % 10 == 0:
                            print(f"⚠️ 알 수 없는 상태: {state} (체크: {check_count}회)")
                
                print("🛑 모니터링이 중단되었습니다.")
                return {"success": False, "message": "모니터링 중단"}
                
            except Exception as e:
                print(f"❌ 동적 포지션 시장가 진입 주문 실행 오류: {e}")
                import traceback
                traceback.print_exc()
                return {"success": False, "message": str(e)}

    # "안전하게 주문 상태를 조회하는 메서드" (인자: self, order_id)
    def _get_order_status_safe(self, order_id: str) -> Optional[Dict]:
        try:
            return self.upbit.get_order_status(order_id)
        except Exception as e:
            print(f"⚠️ 주문 상태 조회 오류: {e}")
            return None
    
    # "주문 상태만 간단히 확인하는 메서드" (인자: self, order_id)
    def _check_order_status(self, order_id: str) -> Optional[str]:
        try:
            order_info = self._get_order_status_safe(order_id)
            if order_info:
                return order_info.get('state', 'unknown')
            return None
        except Exception as e:
            print(f"⚠️ 주문 상태 확인 오류: {e}")
            return None

    # "주문 체결 정보를 상세히 가져오는 메서드" (인자: self, order_id)
    def _get_order_execution_info(self, order_id: str) -> Optional[Dict[str, Any]]:
            try:
                print(f"📊 체결 정보 분석 중... (주문 ID: {order_id})")
                
                max_retries = 5
                retry_delay = 1
                
                for attempt in range(max_retries):
                    order_info = self._get_order_status_safe(order_id)
                    
                    if not order_info:
                        print(f"⚠️ 주문 정보 없음 (시도 {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue

                    state = order_info.get('state', 'unknown')
                    executed_volume = float(order_info.get('executed_volume', 0))

                    if (state == 'done' or state == 'cancel') and executed_volume > 0:
                        trades_count = int(order_info.get('trades_count', 0))
                        print(f"✅ 체결 내역 확인! (상태: {state}, 체결량: {executed_volume}, 건수: {trades_count})")
                        
                        final_fee = float(order_info.get('paid_fee', 0))
                        final_volume = executed_volume
                        
                        total_amount_before_fee = 0.0
                        avg_price = 0.0
                        
                        if 'trades' in order_info and order_info['trades']:
                            print(f"   📊 개별 체결 내역 {len(order_info['trades'])}건으로 평균 단가 정밀 계산")
                            for i, trade in enumerate(order_info['trades']):
                                trade_volume = float(trade.get('volume', 0))
                                trade_price = float(trade.get('price', 0))
                                trade_funds = float(trade.get('funds', 0))
                                
                                actual_funds = trade_funds if trade_funds > 0 else trade_volume * trade_price
                                total_amount_before_fee += actual_funds
                        else:
                            api_avg_price = order_info.get('avg_price')
                            if api_avg_price:
                                avg_price = float(api_avg_price)
                                total_amount_before_fee = avg_price * final_volume

                        if final_volume > 0 and total_amount_before_fee > 0:
                            executed_amount = total_amount_before_fee 
                            avg_price = total_amount_before_fee / final_volume if final_volume > 0 else avg_price
                            
                            print(f"   📊 최종 결과:")
                            print(f"     - 총 거래금액: {total_amount_before_fee:,.2f}원")
                            print(f"     - API 수수료: {final_fee:.2f}원")
                            print(f"     - 평균 단가: {avg_price:,.4f}원")
                            
                            return {
                                'avg_price': float(avg_price),
                                'executed_volume': float(final_volume),
                                'executed_amount': float(total_amount_before_fee),
                                'paid_fee': float(final_fee),
                                'trades_count': trades_count,
                                'calculation_method': 'FULL_EXECUTION'
                            }

                    elif state == 'wait':
                        print(f"⏳ 아직 체결 대기 중... (시도 {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                
                print(f"❌ {max_retries}회 시도 후에도 체결 정보를 확정할 수 없음")
                return None
                
            except Exception as e:
                print(f"❌ 체결 정보 조회 오류: {e}")
                traceback.print_exc()
                return None

    # "거래 모니터링 스레드를 시작하는 메서드" (인자: self)
    def _start_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.should_stop = True
            self.monitoring_thread.join()
        
        self.should_stop = False
        self.monitoring_thread = threading.Thread(target=self._monitor_trade)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    # "진입/청산 조건을 실시간 모니터링하는 메서드" (인자: self)
    def _monitor_trade(self):
        if not self.active_trade:
            return
            
        strategy = self.active_trade['strategy']
        trading_params = strategy.get('trading_parameters', {})
        
        ticker = trading_params.get('coin_ticker', '')
        planned_entry_price = trading_params.get('entry_price', 0)
        planned_target_price = trading_params.get('target_price', 0)
        planned_stop_loss_price = trading_params.get('stop_loss_price', 0)

        entry_price = self._get_upbit_compatible_price(planned_entry_price, ticker)
        target_price = self._get_upbit_compatible_price(planned_target_price, ticker)
        stop_loss_price = self._get_upbit_compatible_price(planned_stop_loss_price, ticker)
        
        print(f"👁️ 알트코인 모니터링 시작: {ticker}")
        print(f"🎯 진입가 터치 시 즉시 매수 (타임아웃: {settings.ENTRY_WAIT_TIMEOUT_HOURS}시간)")

        entry_wait_start = datetime.now()

        consecutive_errors = 0
        max_errors = 10
        
        while not self.should_stop and self.active_trade:
            try:
                current_price = self.upbit.get_current_price(ticker)
                
                if not current_price:
                    consecutive_errors += 1
                    if consecutive_errors >= max_errors:
                        print(f"❌ 연속 {max_errors}회 가격 조회 실패, 모니터링 중단")
                        break
                    time.sleep(5)
                    continue
                
                consecutive_errors = 0  

                if self.active_trade['status'] == 'WAITING_ENTRY':

                    elapsed_hours = (datetime.now() - entry_wait_start).total_seconds() / 3600
                    
                    if elapsed_hours >= settings.ENTRY_WAIT_TIMEOUT_HOURS:
                        print(f"⏰ 진입 대기 타임아웃 ({settings.ENTRY_WAIT_TIMEOUT_HOURS}시간 경과)")
                        print(f"   ❌ 진입가 {entry_price:,.4f}원 미도달")
                        print(f"   🔄 거래 취소하고 Phase 1부터 재시작")

                        self._cancel_waiting_trade("ENTRY_TIMEOUT")
                        break
                    
                    # 진입 허용 범위 0.1% (위아래 0.05%씩)
                    entry_tolerance_percent = 0.1
                    entry_lower_bound = entry_price * (1 - entry_tolerance_percent / 100)
                    entry_upper_bound = entry_price * (1 + entry_tolerance_percent / 100)

                    if entry_lower_bound <= current_price <= entry_upper_bound:
                        if current_price >= 1:
                            print(f"🎯 진입 조건 달성! 현재가 {current_price:,.4f}원이 진입 범위 내")
                        else:
                            print(f"🎯 진입 조건 달성! 현재가 {current_price:.6f}원이 진입 범위 내")

                        entry_result = self._execute_entry_order(ticker, current_price)

                        if entry_result['success']:
                            entry_info = entry_result.get('execution_info')  
                            
                            if entry_info:
                                self._update_trade_with_entry_info(entry_info)
                                print("✅ 매수 완료! 이제 청산 조건 모니터링으로 전환")
                            else:
                                print("❌ 매수는 성공했으나 체결 정보가 누락됨 - 모니터링 중단")
                                break
                        else:
                            print(f"❌ 매수 실행 실패: {entry_result.get('message', 'Unknown error')}")
                    
                    else:
                        if int(time.time()) % 30 == 0:
                            remaining_hours = settings.ENTRY_WAIT_TIMEOUT_HOURS - elapsed_hours
                            
                            if current_price >= 1:
                                print(f"🔍 진입 대기 중: {current_price:,.4f}원 (목표: {entry_price:,.4f}원 ±{entry_tolerance_percent}%)")
                            else:
                                print(f"🔍 진입 대기 중: {current_price:.6f}원 (목표: {entry_price:.6f}원 ±{entry_tolerance_percent}%)")
                            print(f"   📊 진입 범위: {entry_lower_bound:,.4f}원 ~ {entry_upper_bound:,.4f}원")
                            print(f"   ⏱️  남은 시간: {remaining_hours:.1f}시간")
                
                elif self.active_trade['status'] == 'ACTIVE':
                    entry_price = self.active_trade['actual_entry_price']
                    volume = self.active_trade['actual_volume']

                    active_sell_order_id = None

                    price_tolerance = 0.000001  

                    if current_price >= (target_price - price_tolerance):
                        if self.active_trade.get('entry_timestamp'):
                            entry_time = self.active_trade['entry_timestamp']
                            if isinstance(entry_time, str):
                                entry_time = datetime.fromisoformat(entry_time)
                            actual_time_to_target = (datetime.now() - entry_time).total_seconds() / 3600
                        else:
                            actual_time_to_target = None
                        
                        if current_price >= 1:
                            print(f"🎯 목표가 도달! {current_price:,.4f}원 >= {target_price:,.4f}원")
                        else:
                            print(f"🎯 목표가 도달! {current_price:.6f}원 >= {target_price:.6f}원")
                        
                        if actual_time_to_target:
                            print(f"   ⏱️  소요 시간: {actual_time_to_target:.1f}시간")

                        current_balance = self._get_actual_coin_balance(ticker)
                        
                        if current_balance > 0.00000001:
                            sell_success = self._execute_exit_order(ticker, target_price, current_balance, "TARGET_HIT", actual_time_to_target)
                            
                            if sell_success:
                                print("🎉 목표가 도달로 거래 완료!")
                                break
                            else:
                                print("🔄 매도 주문 진행 중 - 계속 모니터링")

                                if not hasattr(self, 'sell_order_in_progress'):
                                    self.sell_order_in_progress = True

                                time.sleep(5)
                                continue
                        else:
                            print("✅ 이미 전액 매도 완료")

                            if hasattr(self, 'accumulated_exit_data') and self.accumulated_exit_data:
                                self._force_complete_trade_with_accumulated_data("TARGET_HIT")
                            else:
                                self._finalize_trade_basic(target_price, "TARGET_HIT")
                            break
 
                    elif current_price <= (stop_loss_price + price_tolerance):
                        if current_price >= 1:
                            print(f"🚨 손절가 도달! {current_price:,.4f}원 <= {stop_loss_price:,.4f}원")
                        else:
                            print(f"🚨 손절가 도달! {current_price:.6f}원 <= {stop_loss_price:.6f}원")

                        if active_sell_order_id:
                            print("🔄 기존 매도 주문 취소 중...")
                            self.upbit.cancel_order(active_sell_order_id)
                            time.sleep(1)

                        current_balance = self._get_actual_coin_balance(ticker)
                        if current_balance > 0.00000001:
                            self._execute_market_sell(ticker, current_balance, "STOP_LOSS")
                            print("😢 손절로 거래 완료")
                        break
                    
                    else:
                        if int(time.time()) % 30 == 0:
                            profit_rate = ((current_price - entry_price) / entry_price) * 100
                            
                            if current_price >= 1:
                                print(f"💼 포지션 모니터링: {current_price:,.4f}원 (수익률: {profit_rate:+.2f}%)")
                            else:
                                print(f"💼 포지션 모니터링: {current_price:.6f}원 (수익률: {profit_rate:+.2f}%)")

                            current_balance = self._get_actual_coin_balance(ticker)
                            if current_balance < 0.00000001 and volume > 0:
                                print("✅ 전액 매도 확인 - 거래 완료 처리")
                                if hasattr(self, 'accumulated_exit_data'):
                                    self._finalize_trade_with_actual_info(self.accumulated_exit_data, "TARGET_HIT", actual_time_to_target)
                                else:
                                    self._finalize_trade_basic(target_price, "TARGET_HIT")
                                break

                            price_to_target = target_price - current_price
                            price_to_stop = current_price - stop_loss_price
                            
                            print(f"   💰 현재 보유량: {current_balance:.8f}개")
                            print(f"   📈 목표가까지: {price_to_target:,.4f}원")
                            print(f"   📉 손절가까지: {price_to_stop:,.4f}원")

                time.sleep(1)
                
            except Exception as e:
                print(f"❌ 모니터링 오류: {e}")
                consecutive_errors += 1
                
                if consecutive_errors >= max_errors:
                    print(f"❌ 연속 {max_errors}회 오류 발생, 모니터링 중단")
                    break
                
                time.sleep(1)
        
        print("🏁 거래 모니터링 종료")

    # "청산 주문을 실행하는 메서드" (인자: self, ticker, target_price, volume, exit_type, actual_time_to_target)
    def _execute_exit_order(self, ticker: str, target_price: float, volume: float, exit_type: str, actual_time_to_target: float = None):
        try:
            actual_balance = self._get_actual_coin_balance(ticker)
            
            if actual_balance < volume * 0.99:  
                print(f"⚠️ 보유량 조정: 요청 {volume:.8f} → 실제 {actual_balance:.8f}")
                if actual_balance < 0.00000001:  
                    print("❌ 매도할 코인이 없습니다. 거래 완료로 간주")
                    if hasattr(self, 'accumulated_exit_data') and self.accumulated_exit_data:
                        print("🎯 누적 매도 데이터 기반으로 거래 완료 처리")
                        self._force_complete_trade_with_accumulated_data(exit_type)
                    return
                volume = actual_balance * 0.999  

            if target_price >= 1:
                print(f"🔄 지정가 청산 주문: {volume:.8f}개 @ {target_price:,.4f}원")
            else:
                print(f"🔄 지정가 청산 주문: {volume:.8f}개 @ {target_price:.6f}원")

            if actual_time_to_target is not None:
                print(f"   ⏰ 실제 소요 시간: {actual_time_to_target:.2f}시간")
            
            if exit_type == "STOP_LOSS":
                print("🚨 손절가 도달 - 즉시 시장가 매도")
                return self._execute_market_sell(ticker, volume, exit_type, actual_time_to_target)
            
            else:
                print("🎯 목표가 도달 - 지정가 매도 (완전 체결까지 무한 대기)")
                return self._execute_persistent_limit_sell(ticker, target_price, volume, exit_type, actual_time_to_target)
                
        except Exception as e:
            print(f"❌ 청산 주문 실행 오류: {e}")
            traceback.print_exc()
            return False

    # "완전 체결까지 대기하는 지정가 매도 메서드" (인자: self, ticker, price, volume, exit_type, actual_time_to_target)
    def _execute_persistent_limit_sell(self, ticker: str, price: float, volume: float, exit_type: str, actual_time_to_target: float = None):
        try:
            compatible_price = self._get_upbit_compatible_price(price, ticker)
            
            if compatible_price >= 1:
                print(f"🔄 전액 지정가 매도: {compatible_price:,.4f}원 x {volume:.8f}개")
            else:
                print(f"🔄 전액 지정가 매도: {compatible_price:.6f}원 x {volume:.8f}개")

            order_id = self.upbit.sell_limit_order(ticker, compatible_price, volume)
            
            if not order_id:
                print(f"❌ 지정가 매도 주문 실패")
                return False
            
            print(f"✅ 지정가 매도 주문 성공: {order_id}")
            print(f"⏳ 완전 체결까지 무한 대기 시작...")
            
            check_interval = 2  
            check_count = 0
            last_executed_volume = 0
            partial_executions = []  
            
            while not self.should_stop:
                time.sleep(check_interval)
                check_count += 1

                order_status = self._get_order_status_safe(order_id)
                
                if not order_status:
                    print(f"⚠️ 주문 상태 조회 실패 (재시도...)")
                    continue
                
                state = order_status.get('state', 'unknown')
                current_executed = float(order_status.get('executed_volume', 0))
                remaining = float(order_status.get('remaining_volume', 0))

                if current_executed > last_executed_volume:
                    partial_volume = current_executed - last_executed_volume
                    print(f"📊 부분 체결 발생! +{partial_volume:.8f}개")
                    print(f"   누적 체결: {current_executed:.8f} / 전체: {volume:.8f}")
                    print(f"   남은 수량: {remaining:.8f}")
                    
                    partial_executions.append({
                        'time': datetime.now(),
                        'volume': partial_volume,
                        'cumulative': current_executed
                    })
                    
                    last_executed_volume = current_executed

                if state == 'done':
                    print("🎉 주문 완전 체결 확인!")
                    print(f"   총 체결량: {current_executed:.8f}개")
                    print(f"   부분 체결 횟수: {len(partial_executions)}회")

                    exit_info = self._get_order_execution_info(order_id)
                    
                    if exit_info:
                        print("✅ 거래 완료 처리 중...")
                        self._finalize_trade_with_actual_info(exit_info, exit_type, actual_time_to_target)
                        return True
                    else:
                        print("⚠️ 체결 정보 조회 실패 - 기본값으로 처리")
                        current_price = self.upbit.get_current_price(ticker)
                        self._finalize_trade_basic(current_price, exit_type)
                        return True
                
                elif state == 'wait':
                    if check_count % 15 == 0: 
                        current_price = self.upbit.get_current_price(ticker)
                        elapsed_time = check_count * check_interval
                        
                        print(f"⏳ 체결 대기 중... (경과: {elapsed_time}초)")
                        print(f"   현재가: {current_price:,.4f}원 / 매도가: {compatible_price:,.4f}원")
                        print(f"   체결 진행률: {(current_executed/volume*100):.1f}%")

                        if current_price < compatible_price * 0.995:
                            price_gap = ((compatible_price - current_price) / compatible_price) * 100
                            print(f"   📉 현재가가 매도가보다 {price_gap:.2f}% 낮음")
                            print(f"   💡 팁: 가격이 회복될 때까지 대기 중...")
                
                elif state == 'cancel':
                    print("❌ 주문이 취소되었습니다.")
                    
                    if current_executed > 0:
                        print(f"⚠️ 부분 체결된 {current_executed:.8f}개는 처리 완료")
                        current_price = self.upbit.get_current_price(ticker)
                        self._finalize_trade_basic(current_price, exit_type)
                    
                    return False
                
                else:
                    print(f"⚠️ 알 수 없는 주문 상태: {state}")
            
            print("🛑 모니터링이 중단되었습니다.")
            return False
            
        except Exception as e:
            print(f"❌ 지정가 매도 실행 오류: {e}")
            traceback.print_exc()
            return False

    # "실제 코인 보유량을 조회하는 메서드" (인자: self, ticker)
    def _get_actual_coin_balance(self, ticker: str) -> float:
        try:
            coin_symbol = ticker.split('-')[1] if '-' in ticker else ticker

            coin_balance = self.upbit.get_balance(coin_symbol)
            
            print(f"💰 {coin_symbol} 실제 보유량: {coin_balance:.8f}개")
            return float(coin_balance)
            
        except Exception as e:
            print(f"❌ {ticker} 보유량 조회 오류: {e}")
            return 0.0

    # "손절용 시장가 매도를 실행하는 메서드" (인자: self, ticker, volume, exit_type, actual_time_to_target)
    def _execute_market_sell(self, ticker: str, volume: float, exit_type: str, actual_time_to_target: float = None):
        try:
            print(f"🚨 시장가 즉시 매도: {volume:.8f}개")

            market_order_id = self.upbit.sell_market_order(ticker, volume)
            
            if market_order_id:
                print("⏳ 시장가 매도 체결 확인 중...")

                for i in range(5):
                    time.sleep(1)

                    exit_info = self._get_order_execution_info(market_order_id)
                    
                    if exit_info:
                        print("✅ 시장가 매도 체결 완료")
                        self._finalize_trade_with_actual_info(exit_info, exit_type, actual_time_to_target)
                        return True
                    
                    print(f"   ⏳ 시장가 확인 중... ({i+1}/5초)")

                print("✅ 시장가 매도 완료 (체결 추정)")

                current_price = self.upbit.get_current_price(ticker)
                if current_price:
                    self._finalize_trade_basic(current_price, exit_type)
                
                return True

            print("❌ 시장가 매도 주문 실패")
            return False
            
        except Exception as e:
            print(f"❌ 시장가 매도 실행 오류: {e}")
            return False

    # "진입 체결 정보로 거래 상태를 업데이트하는 메서드" (인자: self, entry_info)
    def _update_trade_with_entry_info(self, entry_info: Dict[str, Any]):
        if not self.active_trade:
            return

        self.active_trade['status'] = 'ACTIVE'
        self.active_trade['actual_entry_price'] = entry_info['avg_price']
        self.active_trade['actual_volume'] = entry_info['executed_volume']
        self.active_trade['actual_entry_amount'] = entry_info['executed_amount']
        self.active_trade['entry_fee'] = entry_info['paid_fee']
        self.active_trade['entry_timestamp'] = datetime.now()

        self.db.update_trade_result(self.active_trade['trade_id'], {
            'status': 'ACTIVE',
            'actual_entry_price': entry_info['avg_price'],
            'actual_volume': entry_info['executed_volume'],
            'executed_amount': entry_info['executed_amount'],
            'entry_fee': entry_info['paid_fee'],
            'entry_timestamp': datetime.now().isoformat()
        })
        
        print(f"📊 진입 체결 정보 업데이트 완료:")
        print(f"   💰 평균 진입가: {entry_info['avg_price']:,.4f}원")
        print(f"   📊 체결량: {entry_info['executed_volume']:.8f}개")
        print(f"   💸 수수료: {entry_info['paid_fee']:,.2f}원")

    # "대기 중인 거래를 취소하는 메서드" (인자: self, reason)
    def _cancel_waiting_trade(self, reason: str):
        if not self.active_trade:
            return
            
        trade_id = self.active_trade.get('trade_id')

        self.db.update_trade_result(trade_id, {
            'status': 'CANCELLED',
            'exit_reason': reason,
            'exit_timestamp': datetime.now().isoformat(),
            'profit_loss': 0,
            'profit_rate': 0,
            'entry_fee': 0,
            'exit_fee': 0,
            'actual_entry_price': self.active_trade['strategy']['trading_parameters']['entry_price'],
            'actual_exit_price': 0,
            'actual_volume': 0
        })

        self.active_trade = None
        self.should_stop = True  
        
        print(f"✅ 거래 취소 완료 (사유: {reason})")
        print(f"   📋 거래 ID: {trade_id}")
        print(f"   🔄 새로운 거래 기회를 찾기 위해 Phase 1부터 재시작합니다")

    # "누적 데이터로 거래를 강제 완료하는 메서드" (인자: self, exit_type)
    def _force_complete_trade_with_accumulated_data(self, exit_type: str):
        try:
            if not hasattr(self, 'accumulated_exit_data') or not self.accumulated_exit_data:
                print("❌ 누적 매도 데이터가 없어 기본 완료 처리")
                current_price = self.upbit.get_current_price(self.active_trade['strategy']['trading_parameters']['coin_ticker'])
                if current_price:
                    self._finalize_trade_basic(current_price, exit_type)
                return
            
            print("🎯 누적 매도 데이터로 거래 완료 처리")
            self._finalize_trade_with_actual_info(self.accumulated_exit_data, exit_type)

            delattr(self, 'accumulated_exit_data')
            
        except Exception as e:
            print(f"❌ 누적 데이터 기반 완료 처리 오류: {e}")
            current_price = self.upbit.get_current_price(self.active_trade['strategy']['trading_parameters']['coin_ticker'])
            if current_price:
                self._finalize_trade_basic(current_price, exit_type)

    # "실제 체결 정보로 거래를 완료하는 메서드" (인자: self, exit_info, exit_type, actual_time_to_target)
    def _finalize_trade_with_actual_info(self, exit_info: Dict[str, Any], exit_type: str, actual_time_to_target: float = None):
        if not self.active_trade:
            return
        
        try:
            entry_price = self.active_trade['actual_entry_price']
            entry_volume = self.active_trade['actual_volume']
            entry_fee = self.active_trade['entry_fee']
            
            exit_price = exit_info['avg_price']
            exit_volume = exit_info['executed_volume']
            exit_fee = exit_info['paid_fee']
            exit_amount = exit_info['executed_amount']

            entry_total_cost = entry_price * entry_volume + entry_fee
            exit_total_amount = exit_amount - exit_fee
            
            actual_profit_loss = exit_total_amount - entry_total_cost
            actual_profit_rate = actual_profit_loss / entry_total_cost * 100

            holding_period = "Unknown"
            if 'entry_timestamp' in self.active_trade and self.active_trade['entry_timestamp']:
                try:
                    entry_time = self.active_trade['entry_timestamp']
                    exit_time = datetime.now()

                    if not isinstance(entry_time, datetime):
                        entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    
                    duration = exit_time - entry_time
                    total_seconds = duration.total_seconds()
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    
                    if hours > 0:
                        holding_period = f"{hours}시간 {minutes}분"
                    else:
                        holding_period = f"{minutes}분"
                except Exception as e:
                    print(f"⚠️ 보유 기간 계산 오류: {e}")

            if actual_time_to_target is not None:
                print(f"   ⏰ 실제 소요 시간: {actual_time_to_target:.2f}시간")

            result_data = {
                'status': 'COMPLETED',
                'actual_exit_price': exit_price,
                'exit_volume': exit_volume,
                'exit_fee': exit_fee,
                'exit_timestamp': datetime.now().isoformat(),
                'profit_loss': actual_profit_loss,
                'profit_rate': actual_profit_rate
            }
            
            self.db.update_trade_result(self.active_trade['trade_id'], result_data)

            status_emoji = "💰" if actual_profit_loss > 0 else "📉"
            print(f"\n{status_emoji} 알트코인 거래 완료 (업비트 실제 정보)!")
            
            if entry_price >= 1:
                print(f"   📈 진입: {entry_price:,.4f}원 x {entry_volume:.8f}개 (수수료: {entry_fee:,.2f}원)")
                print(f"   📉 청산: {exit_price:,.4f}원 x {exit_volume:.8f}개 (수수료: {exit_fee:,.2f}원)")
            else:
                print(f"   📈 진입: {entry_price:.6f}원 x {entry_volume:.8f}개 (수수료: {entry_fee:,.2f}원)")
                print(f"   📉 청산: {exit_price:.6f}원 x {exit_volume:.8f}개 (수수료: {exit_fee:,.2f}원)")
            
            print(f"   💰 실제 손익: {actual_profit_loss:,.2f}원 ({actual_profit_rate:+.2f}%)")
            print(f"   ⏱️ 보유 기간: {holding_period}")
            print(f"   📚 종료 사유: {exit_type}")

            trade_result = {
                'trade_id': self.active_trade['trade_id'],
                'symbol': self.active_trade['strategy']['trading_parameters']['coin_ticker'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'profit_rate_percent': actual_profit_rate,
                'profit_amount_krw': actual_profit_loss,
                'holding_period': holding_period,
                'exit_type': exit_type
            }
            
            print(f"\n🔄 거래 완료 - 원칙 업데이트 시작...")

            from core.reflector import Reflector
            reflector = Reflector()

            phase_cache = {}
            gpt_client = reflector.gpt
            if hasattr(gpt_client, 'response_cache'):
                phase_cache = {
                    'phase1': gpt_client.response_cache.get('phase1'),
                    'phase2': gpt_client.response_cache.get('phase2'),
                    'phase3': gpt_client.response_cache.get('phase3')
                }

            existing_principles = reflector._read_principles()

            updated_principles = gpt_client.generate_updated_principles_after_trade(
                trade_result=trade_result,
                phase_cache=phase_cache,
                existing_principles=existing_principles
            )
            
            if updated_principles:
                reflector._save_principles(updated_principles)
                print("✅ 원칙 업데이트 완료")
            else:
                print("⚠️ 원칙 업데이트 실패")

            self.active_trade = None
            self.should_stop = True
            
            print(f"\n🔄 거래 사이클 완료 - 다음 기회를 찾습니다...")
            
        except Exception as e:
            print(f"❌ 거래 완료 처리 오류: {e}")
            import traceback
            traceback.print_exc()

    # "기본 방식으로 거래를 완료하는 백업 메서드" (인자: self, exit_price, exit_type)
    def _finalize_trade_basic(self, exit_price: float, exit_type: str):
        if not self.active_trade:
            return
        
        entry_price = self.active_trade['actual_entry_price']
        volume = self.active_trade['actual_volume']

        profit_loss = (exit_price - entry_price) * volume
        profit_rate = (exit_price - entry_price) / entry_price * 100

        result_data = {
            'status': 'COMPLETED',
            'actual_exit_price': exit_price,
            'exit_timestamp': datetime.now().isoformat(),
            'profit_loss': profit_loss,
            'profit_rate': profit_rate,
        }
        
        self.db.update_trade_result(self.active_trade['trade_id'], result_data)

        status_emoji = "💰" if profit_loss > 0 else "📉"
        print(f"{status_emoji} 거래 완료!")
        print(f"   진입가: {entry_price:,.0f}원")
        print(f"   청산가: {exit_price:,.0f}원")
        print(f"   손익: {profit_loss:,.0f}원 ({profit_rate:+.2f}%)")
        print(f"   종료 사유: {exit_type}")

        trade_id = self.active_trade['trade_id']
        print(f"\n📝 Phase 5: 거래 회고 및 원칙 업데이트 즉시 실행 - {trade_id}")

        try:
            from core.reflector import Reflector
            reflector = Reflector()

            import time
            time.sleep(2)
            
            reflection_success = reflector.record_trade_reflection(trade_id)
            if reflection_success:
                print("✅ 거래 회고 및 원칙 업데이트 완료")
            else:
                print("⚠️ 거래 회고 및 원칙 업데이트 실패")
                
        except Exception as reflection_error:
            print(f"❌ 회고 실행 중 오류: {reflection_error}")
            import traceback
            traceback.print_exc()

        self.active_trade = None
        self.should_stop = True
        
        print(f"\n🔄 거래 사이클 완료 - 다음 기회를 찾습니다...")
    
    # "현재 거래가 활성 상태인지 확인하는 메서드" (인자: self)
    def is_trading_active(self) -> bool:
        return self.active_trade is not None
    
    # "모니터링을 중단하는 메서드" (인자: self)
    def stop_monitoring(self):
        """모니터링 중단"""
        self.should_stop = True
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join()

    # "현재 거래 상태를 조회하는 메서드" (인자: self)
    def get_current_trade_status(self) -> Optional[Dict[str, Any]]:
        if not self.active_trade:
            return None
        
        strategy = self.active_trade['strategy']
        trading_params = strategy.get('trading_parameters', {})
        
        return {
            'trade_id': self.active_trade['trade_id'],
            'ticker': trading_params.get('coin_ticker', ''),
            'entry_price': self.active_trade['actual_entry_price'],
            'target_price': trading_params.get('target_price', 0),
            'stop_loss_price': trading_params.get('stop_loss_price', 0),
            'volume': self.active_trade['actual_volume'],
            'status': self.active_trade['status']
        }