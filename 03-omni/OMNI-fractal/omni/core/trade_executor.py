# core/trade_executor.py - V2 EXACT LOGIC VERSION
# "Phase 4: V2의 검증된 매수/매도 로직을 정확히 그대로 사용"

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from data.upbit_client import UpbitClient
from data.database import TradeDatabase
from config.settings import settings
import traceback

class TradeExecutor:

    def __init__(self):
        self.upbit = UpbitClient()
        self.db = TradeDatabase()
        self.active_trade = None
        self.monitoring_thread = None
        self.should_stop = False
        self._recover_active_trade()
    
    def _recover_active_trade(self):
        """재시작 시 업비트에서 실제 보유 현황 확인"""
        try:
            print("🔄 업비트에서 실제 보유 현황 확인 중...")
            
            # 1. 업비트에서 실제 보유 코인 조회
            balances = self.upbit.get_balances()
            holding_coins = []
            
            for balance in balances:
                currency = balance.get('currency', '')
                if currency != 'KRW':
                    # 실제 보유량이 있는 코인만
                    balance_amount = float(balance.get('balance', 0))
                    locked_amount = float(balance.get('locked', 0))
                    total_amount = balance_amount + locked_amount
                    
                    if total_amount > 0:
                        avg_buy_price = float(balance.get('avg_buy_price', 0))
                        holding_coins.append({
                            'ticker': f'KRW-{currency}',
                            'volume': total_amount,
                            'avg_price': avg_buy_price,
                            'balance': balance_amount,
                            'locked': locked_amount
                        })
            
            if holding_coins:
                print(f"📊 업비트 실제 보유 코인 발견:")
                for coin in holding_coins:
                    print(f"   {coin['ticker']}: {coin['volume']:.8f}개 (평균가: {coin['avg_price']:,.0f}원)")
                
                # 2. DB에서 최근 거래 확인
                recent_trades = self.db.get_recent_trades(limit=10)
                
                for trade in recent_trades:
                    if trade.get('status') in ['ACTIVE', 'WAITING_ENTRY']:
                        ticker = trade.get('coin_ticker')
                        
                        # 실제 보유와 매칭
                        for holding in holding_coins:
                            if holding['ticker'] == ticker:
                                print(f"✅ 활성 거래 매칭: {ticker}")
                                
                                # 업비트 데이터로 거래 복구
                                self._restore_trade_from_upbit(trade, holding)
                                return
                
                print("⚠️ DB와 매칭되지 않는 보유 코인 - 수동 확인 필요")
            else:
                print("✅ 업비트에 보유 코인 없음 - 새 거래 가능")
                
        except Exception as e:
            print(f"❌ 거래 복구 중 오류: {e}")
            traceback.print_exc()
    
    def _restore_trade_from_upbit(self, db_trade: Dict, upbit_holding: Dict):
        """업비트 데이터로 거래 상태 복원"""
        try:
            # 전략 재구성
            strategy = {
                'trade_id': db_trade['trade_id'],
                'trading_parameters': {
                    'coin_ticker': db_trade['coin_ticker'],
                    'entry_price': db_trade.get('entry_price', upbit_holding['avg_price']),
                    'target_price': db_trade.get('target_price', 0),
                    'stop_loss_price': db_trade.get('stop_loss_price', 0),
                    'position_size_percent': db_trade.get('position_size_percent', 50)
                }
            }
            
            self.active_trade = {
                'trade_id': db_trade['trade_id'],
                'strategy': strategy,
                'status': 'ACTIVE',  # 실제 보유 중이므로 ACTIVE
                'start_timestamp': datetime.fromisoformat(db_trade['timestamp']),
                'position_size_percent': db_trade.get('position_size_percent', 50),
                'actual_entry_price': upbit_holding['avg_price'],  # 업비트 평균가
                'actual_volume': upbit_holding['volume'],  # 업비트 보유량
                'entry_fee': 0,  # 수수료는 주문 조회로 확인
                'entry_timestamp': datetime.fromisoformat(db_trade.get('entry_timestamp', db_trade['timestamp']))
            }
            
            print(f"🎯 거래 복구 완료:")
            print(f"   코인: {db_trade['coin_ticker']}")
            print(f"   보유량: {upbit_holding['volume']:.8f}개")
            print(f"   평균가: {upbit_holding['avg_price']:,.0f}원")
            print(f"   목표가: {db_trade.get('target_price', 0):,.0f}원")
            
            # DB 업데이트 (업비트 데이터로)
            self.db.update_trade_result(db_trade['trade_id'], {
                'status': 'ACTIVE',
                'actual_entry_price': upbit_holding['avg_price'],
                'actual_volume': upbit_holding['volume']
            })
            
            # 모니터링 재시작
            self._start_monitoring()
            print("🚀 거래 모니터링 재시작")
            
        except Exception as e:
            print(f"❌ 거래 복원 실패: {e}")

    def execute_trade(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """거래 실행 - 초기 설정만"""
        if not self.upbit.private_client:
            return {"error": "거래 클라이언트가 초기화되지 않음"}

        trade_id = strategy.get('trade_id')
        trading_params = strategy.get('trading_parameters', {})
        
        ticker = trading_params.get('coin_ticker', '')
        entry_price = trading_params.get('entry_price', 0)
        target_price = trading_params.get('target_price', 0)
        stop_loss_price = trading_params.get('stop_loss_price', 0)
        position_size_percent = trading_params.get('position_size_percent', 50)
        
        if not ticker or not entry_price:
            return {"error": "거래 파라미터가 불완전함"}
        
        print(f"🎯 거래 실행 시작: {ticker} (ID: {trade_id})")
        print(f"   💼 포지션: {position_size_percent}%")
        print(f"   📈 진입가: {entry_price:,.0f}원")
        print(f"   🎯 목표가: {target_price:,.0f}원")
        print(f"   🛑 손절가: {stop_loss_price:,.0f}원")

        self.active_trade = {
            'trade_id': trade_id,
            'strategy': strategy,
            'status': 'WAITING_ENTRY',
            'start_timestamp': datetime.now(),
            'position_size_percent': position_size_percent
        }

        self.db.update_trade_result(trade_id, {
            'status': 'WAITING_ENTRY',
            'position_size_percent': position_size_percent
        })

        self._start_monitoring()
        
        print(f"\n✅ 모니터링 시작 - 진입 조건 달성 시 자동 매수")
        
        return {"success": True, "message": "거래 모니터링 시작"}

    def _monitor_trade(self):
        """거래 모니터링 - 업비트 API 기반"""
        if not self.active_trade:
            return
            
        strategy = self.active_trade['strategy']
        trading_params = strategy.get('trading_parameters', {})
        
        ticker = trading_params.get('coin_ticker', '')
        entry_price = trading_params.get('entry_price', 0)
        target_price = trading_params.get('target_price', 0)
        stop_loss_price = trading_params.get('stop_loss_price', 0)
        
        print(f"👁️ 모니터링 시작: {ticker}")
        
        entry_wait_start = datetime.now()
        last_check_time = time.time()
        
        while not self.should_stop and self.active_trade:
            try:
                # API 호출 간격 제어 (2초)
                if time.time() - last_check_time < 2:
                    time.sleep(1)
                    continue
                
                last_check_time = time.time()
                
                # 현재가 조회
                current_price = self.upbit.get_current_price(ticker)
                if not current_price:
                    time.sleep(5)
                    continue
                
                if self.active_trade['status'] == 'WAITING_ENTRY':
                    elapsed_hours = (datetime.now() - entry_wait_start).total_seconds() / 3600
                    
                    # 타임아웃 체크
                    if elapsed_hours >= settings.ENTRY_WAIT_TIMEOUT_HOURS:
                        print(f"⏰ 진입 타임아웃 ({settings.ENTRY_WAIT_TIMEOUT_HOURS}시간)")
                        self._cancel_trade("TIMEOUT")
                        break
                    
                    # 진입 조건 체크
                    if abs(current_price - entry_price) / entry_price < 0.002:
                        print(f"🎯 진입 조건 달성! 현재가: {current_price:,.0f}원")
                        
                        # 매수 실행 및 업비트 확인
                        if self._execute_and_verify_buy(ticker):
                            # 매수 성공 - 상태는 _execute_and_verify_buy에서 변경됨
                            continue
                        else:
                            # 매수 실패
                            self._cancel_trade("BUY_FAILED")
                            break
                    else:
                        if int(time.time()) % 30 == 0:
                            print(f"🔍 대기 중: {current_price:,.0f}원 (목표: {entry_price:,.0f}원)")
                
                elif self.active_trade['status'] == 'ACTIVE':
                    # 실제 보유량 확인 (주기적)
                    if int(time.time()) % 60 == 0:
                        self._verify_holding(ticker)
                    
                    actual_entry = self.active_trade.get('actual_entry_price', 0)
                    actual_volume = self.active_trade.get('actual_volume', 0)
                    
                    if actual_entry == 0 or actual_volume == 0:
                        print("⚠️ 보유 정보 없음 - 재확인")
                        self._verify_holding(ticker)
                        continue
                    
                    profit_rate = ((current_price - actual_entry) / actual_entry) * 100
                    
                    # 목표가 도달
                    if current_price >= target_price:
                        print(f"🎯 목표가 도달! {current_price:,.0f}원 ({profit_rate:+.2f}%)")
                        if self._execute_and_verify_sell(ticker, target_price, "TARGET"):
                            break
                    
                    # 손절가 도달
                    elif current_price <= stop_loss_price:
                        print(f"🚨 손절가 도달! {current_price:,.0f}원 ({profit_rate:+.2f}%)")
                        if self._execute_and_verify_sell(ticker, None, "STOP_LOSS"):
                            break
                    
                    else:
                        if int(time.time()) % 30 == 0:
                            print(f"💼 보유 중: {current_price:,.0f}원 ({profit_rate:+.2f}%)")
                
                time.sleep(2)
                
            except Exception as e:
                print(f"❌ 모니터링 오류: {e}")
                traceback.print_exc()
                time.sleep(5)
        
        print("🏁 모니터링 종료")

    def _execute_and_verify_buy(self, ticker: str) -> bool:
        """
        V2의 정확한 매수 로직 사용
        """
        try:
            # 1. KRW 잔고 확인
            krw_balance = self.upbit.get_balance("KRW")
            position_percent = self.active_trade.get('position_size_percent', 50)
            buy_amount = krw_balance * (position_percent / 100)
            
            if buy_amount < 5000:
                print(f"❌ 잔고 부족: {krw_balance:,.0f}원")
                return False
            
            print(f"🚀 시장가 매수 실행:")
            print(f"   💰 KRW 잔고: {krw_balance:,.0f}원")
            print(f"   📊 사용 금액: {buy_amount:,.0f}원 ({position_percent}%)")
            
            # 2. 시장가 매수 주문
            order_uuid = self.upbit.buy_market_order(ticker, buy_amount)
            
            if not order_uuid:
                print("❌ 매수 주문 실패")
                return False
            
            print(f"📋 매수 주문 ID: {order_uuid}")
            
            # 3. 체결 확인 (최대 30초) - V2 로직 그대로
            for i in range(30):
                time.sleep(1)
                
                # 업비트에서 주문 상태 조회
                order_info = self.upbit.get_order_status(order_uuid)
                
                if not order_info:
                    continue
                
                state = order_info.get('state', '')
                
                if state == 'done':
                    # 4. 체결 완료 - 업비트에서 정확한 데이터 추출
                    executed_volume = float(order_info.get('executed_volume', 0))
                    paid_fee = float(order_info.get('paid_fee', 0))
                    
                    # trades 정보에서 평균 체결가 계산
                    trades = order_info.get('trades', [])
                    if trades:
                        total_funds = sum(float(t.get('funds', 0)) for t in trades)
                        avg_price = total_funds / executed_volume if executed_volume > 0 else 0
                    else:
                        # trades 정보가 없으면 order_info에서 직접
                        avg_price = float(order_info.get('price', 0))
                    
                    if executed_volume > 0 and avg_price > 0:
                        print(f"✅ 매수 체결 완료!")
                        print(f"   평균가: {avg_price:,.0f}원")
                        print(f"   수량: {executed_volume:.8f}개")
                        print(f"   수수료: {paid_fee:,.0f}원")
                        
                        # 5. 상태 업데이트
                        self.active_trade['status'] = 'ACTIVE'
                        self.active_trade['actual_entry_price'] = avg_price
                        self.active_trade['actual_volume'] = executed_volume
                        self.active_trade['entry_fee'] = paid_fee
                        self.active_trade['entry_timestamp'] = datetime.now()
                        self.active_trade['entry_order_uuid'] = order_uuid
                        
                        # 6. DB 업데이트
                        self.db.update_trade_result(self.active_trade['trade_id'], {
                            'status': 'ACTIVE',
                            'actual_entry_price': avg_price,
                            'actual_volume': executed_volume,
                            'entry_fee': paid_fee,
                            'entry_timestamp': datetime.now().isoformat(),
                            'entry_order_uuid': order_uuid
                        })
                        
                        # 7. 업비트에서 실제 보유 재확인
                        time.sleep(2)
                        self._verify_holding(ticker)
                        
                        return True
                    else:
                        print(f"⚠️ 체결 정보 불완전: volume={executed_volume}, price={avg_price}")
                        return False
                        
                elif state == 'cancel' or state == 'canceled':
                    print(f"❌ 주문 취소됨: {order_info.get('reason', 'unknown')}")
                    return False
            
            print("⏰ 체결 확인 타임아웃")
            # 타임아웃 시 주문 취소
            self.upbit.cancel_order(order_uuid)
            return False
            
        except Exception as e:
            print(f"❌ 매수 실행 오류: {e}")
            traceback.print_exc()
            return False

    def _execute_and_verify_sell(self, ticker: str, target_price: Optional[float], exit_type: str) -> bool:
        """
        V2의 정확한 매도 로직 사용
        """
        try:
            # 1. 실제 보유량 확인
            currency = ticker.replace('KRW-', '')
            actual_balance = self.upbit.get_balance(currency)
            
            if actual_balance <= 0:
                print(f"❌ 매도할 수량 없음: {actual_balance}")
                return False
            
            print(f"📊 매도 실행:")
            print(f"   보유량: {actual_balance:.8f}개")
            
            # 2. 매도 주문 (목표가면 지정가, 손절이면 시장가)
            if exit_type == "TARGET" and target_price:
                # 지정가 매도
                print(f"   방식: 지정가 {target_price:,.0f}원")
                order_uuid = self.upbit.sell_limit_order(ticker, target_price, actual_balance)
            else:
                # 시장가 매도
                print(f"   방식: 시장가 (즉시 청산)")
                order_uuid = self.upbit.sell_market_order(ticker, actual_balance)
            
            if not order_uuid:
                print("❌ 매도 주문 실패")
                return False
            
            print(f"📋 매도 주문 ID: {order_uuid}")
            
            # 3. 체결 확인 (지정가는 60초, 시장가는 30초) - V2 로직 그대로
            max_wait = 60 if exit_type == "TARGET" else 30
            
            for i in range(max_wait):
                time.sleep(1)
                
                # 업비트에서 주문 상태 조회
                order_info = self.upbit.get_order_status(order_uuid)
                
                if not order_info:
                    continue
                
                state = order_info.get('state', '')
                
                if state == 'done':
                    # 4. 체결 완료 - 업비트에서 정확한 데이터 추출
                    executed_volume = float(order_info.get('executed_volume', 0))
                    paid_fee = float(order_info.get('paid_fee', 0))
                    
                    # trades 정보에서 평균 체결가 계산
                    trades = order_info.get('trades', [])
                    if trades:
                        total_funds = sum(float(t.get('funds', 0)) for t in trades)
                        avg_price = total_funds / executed_volume if executed_volume > 0 else 0
                    else:
                        avg_price = float(order_info.get('price', 0))
                    
                    if executed_volume > 0 and avg_price > 0:
                        print(f"✅ 매도 체결 완료!")
                        print(f"   평균가: {avg_price:,.0f}원")
                        print(f"   수량: {executed_volume:.8f}개")
                        print(f"   수수료: {paid_fee:,.0f}원")
                        
                        # 5. 손익 계산
                        entry_price = self.active_trade.get('actual_entry_price', 0)
                        entry_fee = self.active_trade.get('entry_fee', 0)
                        
                        profit_loss = (avg_price - entry_price) * executed_volume - entry_fee - paid_fee
                        profit_rate = ((avg_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                        
                        # 6. DB 업데이트
                        self.db.update_trade_result(self.active_trade['trade_id'], {
                            'status': 'COMPLETED',
                            'actual_exit_price': avg_price,
                            'exit_volume': executed_volume,
                            'exit_fee': paid_fee,
                            'exit_timestamp': datetime.now().isoformat(),
                            'exit_order_uuid': order_uuid,
                            'profit_loss': profit_loss,
                            'profit_rate': profit_rate,
                            'exit_type': exit_type
                        })
                        
                        # 7. 결과 출력
                        emoji = "💰" if profit_loss > 0 else "📉"
                        print(f"\n{emoji} 거래 완료!")
                        print(f"   진입: {entry_price:,.0f}원")
                        print(f"   청산: {avg_price:,.0f}원")
                        print(f"   손익: {profit_loss:,.0f}원 ({profit_rate:+.2f}%)")
                        print(f"   사유: {exit_type}")
                        
                        # 8. 거래 종료
                        self.active_trade = None
                        self.should_stop = True
                        
                        return True
                        
                elif state == 'wait' and exit_type == "TARGET":
                    # 지정가 대기 중
                    if i % 10 == 0:
                        print(f"⏳ 지정가 체결 대기 중... ({i}/{max_wait}초)")
            
            # 4. 타임아웃 처리
            if exit_type == "TARGET":
                print("⏰ 지정가 매도 미체결 - 시장가로 전환")
                self.upbit.cancel_order(order_uuid)
                time.sleep(1)
                return self._execute_and_verify_sell(ticker, None, "STOP_LOSS")
            else:
                print("❌ 시장가 매도 실패")
                return False
            
        except Exception as e:
            print(f"❌ 매도 실행 오류: {e}")
            traceback.print_exc()
            return False

    def _verify_holding(self, ticker: str):
        """업비트에서 실제 보유량 확인 및 동기화"""
        try:
            currency = ticker.replace('KRW-', '')
            
            # 업비트에서 실제 잔고 조회
            balance_info = None
            balances = self.upbit.get_balances()
            
            for balance in balances:
                if balance.get('currency') == currency:
                    balance_info = balance
                    break
            
            if balance_info:
                actual_volume = float(balance_info.get('balance', 0)) + float(balance_info.get('locked', 0))
                avg_buy_price = float(balance_info.get('avg_buy_price', 0))
                
                if actual_volume > 0:
                    # 메모리와 다르면 업데이트
                    if abs(self.active_trade.get('actual_volume', 0) - actual_volume) > 0.00000001:
                        print(f"📊 보유량 동기화:")
                        print(f"   이전: {self.active_trade.get('actual_volume', 0):.8f}개")
                        print(f"   현재: {actual_volume:.8f}개")
                        
                        self.active_trade['actual_volume'] = actual_volume
                        
                        if avg_buy_price > 0 and self.active_trade.get('actual_entry_price', 0) == 0:
                            self.active_trade['actual_entry_price'] = avg_buy_price
                        
                        # DB 업데이트
                        self.db.update_trade_result(self.active_trade['trade_id'], {
                            'actual_volume': actual_volume,
                            'actual_entry_price': self.active_trade.get('actual_entry_price', avg_buy_price)
                        })
                else:
                    print(f"⚠️ {ticker} 보유량 0 - 거래 종료 처리")
                    self._cancel_trade("NO_HOLDING")
            else:
                print(f"⚠️ {ticker} 보유 정보 없음")
                
        except Exception as e:
            print(f"❌ 보유량 확인 오류: {e}")

    def _cancel_trade(self, reason: str):
        """거래 취소"""
        if not self.active_trade:
            return
            
        self.db.update_trade_result(self.active_trade['trade_id'], {
            'status': 'CANCELLED',
            'exit_reason': reason,
            'exit_timestamp': datetime.now().isoformat()
        })
        
        self.active_trade = None
        self.should_stop = True
        
        print(f"✅ 거래 취소: {reason}")

    def _start_monitoring(self):
        """모니터링 스레드 시작"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.should_stop = True
            self.monitoring_thread.join()
        
        self.should_stop = False
        self.monitoring_thread = threading.Thread(target=self._monitor_trade)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

    def is_trading_active(self) -> bool:
        """거래 활성 여부"""
        return self.active_trade is not None
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.should_stop = True
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join()

    def get_active_trade_summary(self) -> str:
        """활성 거래 요약"""
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
            volume = self.active_trade.get('actual_volume', 0)
            
            # 업비트에서 현재가 조회
            current_price = self.upbit.get_current_price(ticker)
            if current_price and entry_price > 0:
                profit_rate = ((current_price - entry_price) / entry_price) * 100
                return f"{ticker} 보유 중 ({volume:.8f}개, 수익률: {profit_rate:+.2f}%, 목표: {target_price:,.0f}원)"
            else:
                return f"{ticker} 보유 중 ({volume:.8f}개, 목표: {target_price:,.0f}원)"
        
        return None

    def get_order_history(self, ticker: str = None, hours: int = 24) -> List[Dict]:
        """업비트에서 주문 내역 조회"""
        try:
            # 최근 24시간 주문 내역
            orders = self.upbit.get_order_history(ticker=ticker, state='done', limit=100)
            
            if orders:
                print(f"📋 최근 {hours}시간 체결 내역:")
                for order in orders[:5]:  # 최근 5개만 출력
                    side = order.get('side', '')
                    price = float(order.get('price', 0))
                    volume = float(order.get('executed_volume', 0))
                    created = order.get('created_at', '')
                    
                    print(f"   [{side}] {volume:.8f}개 @ {price:,.0f}원 ({created})")
                
                return orders
            
            return []
            
        except Exception as e:
            print(f"❌ 주문 내역 조회 오류: {e}")
            return []