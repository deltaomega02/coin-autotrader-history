# core/trade_executor.py - FIXED VERSION
# "Phase 4: 업비트 시장가 주문 부분 체결 처리 개선"

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
                
                # 2. DB에서 최근 거래 확인 - 비활성화된 메서드 대체
                print("   ℹ️ DB 조회 비활성화 - 보유 코인만으로 복구 시도")
                
                # 첫 번째 보유 코인으로 거래 복구 (수동 개입 필요할 수 있음)
                if holding_coins:
                    holding = holding_coins[0]
                    print(f"⚠️ {holding['ticker']} 보유 중 - 수동 확인 필요")
                    print(f"   보유량: {holding['volume']:.8f}개")
                    print(f"   평균가: {holding['avg_price']:,.0f}원")
                    print("   목표가/손절가는 수동 설정 필요")
            else:
                print("✅ 업비트에 보유 코인 없음 - 새 거래 가능")
                
        except Exception as e:
            print(f"❌ 거래 복구 중 오류: {e}")
            traceback.print_exc()

    # def execute_trade(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
    #     """거래 실행 - 초기 설정만"""
    #     if not self.upbit.private_client:
    #         return {"error": "거래 클라이언트가 초기화되지 않음"}

    #     trade_id = strategy.get('trade_id')
    #     trading_params = strategy.get('trading_parameters', {})
        
    #     ticker = trading_params.get('coin_ticker', '')
    #     entry_price = trading_params.get('entry_price', 0)
    #     target_price = trading_params.get('target_price', 0)
    #     stop_loss_price = trading_params.get('stop_loss_price', 0)
    #     position_size_percent = trading_params.get('position_size_percent', 50)
        
    #     if not ticker or not entry_price:
    #         return {"error": "거래 파라미터가 불완전함"}
        
    #     print(f"🎯 거래 실행 시작: {ticker} (ID: {trade_id})")
    #     print(f"   💼 포지션: {position_size_percent}%")
    #     print(f"   📈 진입가: {entry_price:,.0f}원")
    #     print(f"   🎯 목표가: {target_price:,.0f}원")
    #     print(f"   🛑 손절가: {stop_loss_price:,.0f}원")

    #     self.active_trade = {
    #         'trade_id': trade_id,
    #         'strategy': strategy,
    #         'status': 'WAITING_ENTRY',
    #         'start_timestamp': datetime.now(),
    #         'position_size_percent': position_size_percent
    #     }

    #     self.db.update_trade_result(trade_id, {
    #         'status': 'WAITING_ENTRY',
    #         'position_size_percent': position_size_percent
    #     })

    #     self._start_monitoring()
        
    #     print(f"\n✅ 모니터링 시작 - 진입 조건 달성 시 자동 매수")
        
    #     return {"success": True, "message": "거래 모니터링 시작"}

    def execute_trade(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
            """거래 실행 - 초기 설정 (V14: 2-Target)"""
            if not self.upbit.private_client:
                return {"error": "거래 클라이언트가 초기화되지 않음"}

            trade_id = strategy.get('trade_id')
            trading_params = strategy.get('trading_parameters', {})
            
            ticker = trading_params.get('coin_ticker', '')
            entry_price = trading_params.get('entry_price', 0)
            
            # V14: 2개 목표가 추출
            target_price_1 = trading_params.get('target_price_1', 0)
            target_price_2 = trading_params.get('target_price_2', 0)
            target_split_ratio = trading_params.get('target_split_ratio', 0.7)
            
            stop_loss_price = trading_params.get('stop_loss_price', 0)
            position_size_percent = trading_params.get('position_size_percent', 50)
            
            if not ticker or not entry_price:
                return {"error": "거래 파라미터가 불완전함"}
            
            print(f"🎯 거래 실행 시작 (V14): {ticker} (ID: {trade_id})")
            print(f"   💼 포지션: {position_size_percent}%")
            print(f"   📈 진입가: {entry_price:,.0f}원")
            print(f"   🎯 1차 목표: {target_price_1:,.0f}원 ({target_split_ratio*100:.0f}% 청산)")
            print(f"   🚀 2차 목표: {target_price_2:,.0f}원 ({(1-target_split_ratio)*100:.0f}% 추격)")
            print(f"   🛑 손절가: {stop_loss_price:,.0f}원")

            # V14: 2-Target 정보 저장
            self.active_trade = {
                'trade_id': trade_id,
                'strategy': strategy,
                'status': 'WAITING_ENTRY',
                'start_timestamp': datetime.now(),
                'position_size_percent': position_size_percent,
                # V14 추가 필드
                'target_price_1': target_price_1,
                'target_price_2': target_price_2,
                'target_split_ratio': target_split_ratio,
                'stage': 1,  # V14: 현재 스테이지 (1=진입전, 2=T1대기, 3=T2추격)
                'target_1_reached': False,  # V14: T1 도달 여부
                'breakeven_stop': None  # V14: 본절 손절가 (T1 도달 후 설정)
            }

            self.db.update_trade_result(trade_id, {
                'status': 'WAITING_ENTRY',
                'position_size_percent': position_size_percent
            })

            self._start_monitoring()
            
            print(f"\n✅ 모니터링 시작 (V14: 2-Stage) - 진입 조건 달성 시 자동 매수")
            
            return {"success": True, "message": "거래 모니터링 시작 (V14)"}

    def _monitor_trade(self):
        """거래 모니터링 (V14: 2-Target Stage System)"""
        if not self.active_trade:
            return
            
        strategy = self.active_trade['strategy']
        trading_params = strategy.get('trading_parameters', {})
        
        ticker = trading_params.get('coin_ticker', '')
        entry_price = trading_params.get('entry_price', 0)
        
        # V14: 2개 목표가
        target_price_1 = self.active_trade.get('target_price_1', 0)
        target_price_2 = self.active_trade.get('target_price_2', 0)
        target_split_ratio = self.active_trade.get('target_split_ratio', 0.7)
        stop_loss_price = trading_params.get('stop_loss_price', 0)
        
        print(f"👁️ 모니터링 시작 (V14): {ticker}")
        print(f"   🎯 T1: {target_price_1:,.0f}원 ({target_split_ratio*100:.0f}%)")
        print(f"   🚀 T2: {target_price_2:,.0f}원 ({(1-target_split_ratio)*100:.0f}%)")
        
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
                
                # === STAGE 1: 진입 대기 ===
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
                        
                        if self._execute_and_verify_buy(ticker):
                            # 매수 성공 → STAGE 2로 전환
                            self.active_trade['stage'] = 2
                            continue
                        else:
                            self._cancel_trade("BUY_FAILED")
                            break
                    else:
                        if int(time.time()) % 30 == 0:
                            gap_pct = ((current_price - entry_price) / entry_price) * 100
                
                # === STAGE 2: T1 대기 (전체 보유) ===
                elif self.active_trade['status'] == 'ACTIVE' and self.active_trade['stage'] == 2:
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
                    
                    # T1 도달 체크
                    if current_price >= target_price_1:
                        print(f"\n🎯 TARGET 1 도달! {current_price:,.0f}원 ({profit_rate:+.2f}%)")
                        print(f"   📦 {target_split_ratio*100:.0f}% 물량 부분 익절 시작...")
                        
                        # V14: 70% 부분 매도
                        if self._execute_partial_sell(ticker, target_split_ratio, "TARGET_1"):
                            # T1 매도 성공 → STAGE 3로 전환
                            self.active_trade['stage'] = 3
                            self.active_trade['target_1_reached'] = True
                            
                            # V14: 손절가를 본절(진입가)로 이동
                            self._move_stop_to_breakeven(actual_entry)
                            
                            print(f"\n✅ STAGE 3 진입: 본절 보호 + T2 추격")
                            print(f"   🎯 남은 {(1-target_split_ratio)*100:.0f}% 물량으로 T2 목표: {target_price_2:,.0f}원")
                            continue
                        else:
                            print("⚠️ T1 부분 매도 실패 - 재시도")
                            time.sleep(5)
                            continue
                    
                    # 손절가 도달 (전량 청산)
                    elif current_price <= stop_loss_price:
                        print(f"🚨 손절가 도달! {current_price:,.0f}원 ({profit_rate:+.2f}%)")
                        if self._execute_and_verify_sell(ticker, None, "STOP_LOSS"):
                            break
                    
                    else:
                        if int(time.time()) % 30 == 0:
                            to_target = ((target_price_1 - current_price) / current_price) * 100
                            # print(f"💼 [STAGE 2] 보유: {profit_rate:+.2f}% - T1까지 {to_target:.2f}%")
                
                # === STAGE 3: T2 추격 (30% 남은 물량) ===
                elif self.active_trade['status'] == 'ACTIVE' and self.active_trade['stage'] == 3:
                    if int(time.time()) % 60 == 0:
                        self._verify_holding(ticker)
                    
                    actual_entry = self.active_trade.get('actual_entry_price', 0)
                    remaining_volume = self.active_trade.get('actual_volume', 0)  # T1 후 남은 물량
                    breakeven_stop = self.active_trade.get('breakeven_stop', actual_entry)
                    
                    if remaining_volume == 0:
                        print("✅ 모든 물량 청산 완료!")
                        self.active_trade = None
                        break
                    
                    profit_rate = ((current_price - actual_entry) / actual_entry) * 100
                    
                    # T2 도달 체크 (잭팟!)
                    if current_price >= target_price_2:
                        print(f"\n🚀 TARGET 2 도달! (JACKPOT!) {current_price:,.0f}원 ({profit_rate:+.2f}%)")
                        print(f"   💰 남은 {(1-target_split_ratio)*100:.0f}% 물량 익절!")
                        
                        # V14: 남은 30% 전량 매도
                        if self._execute_partial_sell(ticker, 1.0, "TARGET_2"):
                            print("🎉 V14 전략 완벽 성공! T1+T2 모두 달성!")
                            break
                    
                    # 본절 손절 체크 (무손실 청산)
                    elif current_price <= breakeven_stop:
                        print(f"🛡️ 본절 손절 도달! {current_price:,.0f}원")
                        print(f"   📦 남은 {(1-target_split_ratio)*100:.0f}% 물량 무손실 청산")
                        
                        if self._execute_partial_sell(ticker, 1.0, "BREAKEVEN"):
                            print("✅ 본절 청산 완료 - T1 수익은 확보!")
                            break
                    
                    else:
                        if int(time.time()) % 30 == 0:
                            to_target = ((target_price_2 - current_price) / current_price) * 100
                            # print(f"🚀 [STAGE 3] 추격: {profit_rate:+.2f}% - T2까지 {to_target:.2f}% (본절보호)")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ 모니터링 오류: {e}")
                traceback.print_exc()
                time.sleep(5)
        
        print("🏁 모니터링 종료 (V14)")

    def _execute_and_verify_buy(self, ticker: str) -> bool:
        """매수 실행 후 업비트에서 체결 확인 - 부분 체결 처리 개선"""
        try:
            # 1. KRW 잔고 확인
            krw_balance = self.upbit.get_balance("KRW")
            position_percent = self.active_trade.get('position_size_percent', 50)
            buy_amount = krw_balance * (position_percent / 100)
            
            # 최소 주문 금액 체크
            if buy_amount < 5000:
                print(f"❌ 잔고 부족: {krw_balance:,.0f}원")
                return False
            
            # 금액 보정 (업비트는 정수 단위)
            buy_amount = int(buy_amount)
            
            print(f"🚀 시장가 매수 실행:")
            print(f"   💰 KRW 잔고: {krw_balance:,.0f}원")
            print(f"   📊 사용 금액: {buy_amount:,.0f}원 ({position_percent}%)")
            
            # 2. 시장가 매수 주문
            order_uuid = self.upbit.buy_market_order(ticker, buy_amount)
            
            if not order_uuid:
                print("❌ 매수 주문 실패")
                return False
            
            print(f"📋 매수 주문 ID: {order_uuid}")
            
            # 3. 체결 확인 (최대 30초)
            for i in range(30):
                time.sleep(1)
                
                # 업비트에서 주문 상태 조회
                order_info = self.upbit.get_order_status(order_uuid)
                
                if not order_info:
                    continue
                
                state = order_info.get('state', '')
                executed_volume = float(order_info.get('executed_volume', 0))
                
                # 체결 완료 또는 부분 체결 후 취소
                if state in ['done', 'cancel', 'canceled']:
                    # 부분 체결이라도 수량이 있으면 성공으로 처리
                    if executed_volume > 0:
                        # 수수료 정보
                        paid_fee = float(order_info.get('paid_fee', 0))
                        
                        # trades 정보에서 평균 체결가 계산
                        trades = order_info.get('trades', [])
                        if trades:
                            total_funds = sum(float(t.get('funds', 0)) for t in trades)
                            avg_price = total_funds / executed_volume if executed_volume > 0 else 0
                        else:
                            # trades 정보가 없으면 executed_funds에서 계산
                            executed_funds = float(order_info.get('executed_funds', 0))
                            if executed_funds > 0 and executed_volume > 0:
                                avg_price = executed_funds / executed_volume
                            else:
                                # 그것도 없으면 현재가 사용
                                avg_price = self.upbit.get_current_price(ticker)
                        
                        if avg_price > 0:
                            print(f"✅ 매수 체결 완료! (상태: {state})")
                            print(f"   평균가: {avg_price:,.0f}원")
                            print(f"   수량: {executed_volume:.8f}개")
                            print(f"   수수료: {paid_fee:,.0f}원")
                            
                            if state in ['cancel', 'canceled']:
                                print(f"   ⚠️ 부분 체결 후 취소됨 (슬리피지 발생)")
                            
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
                                'executed_amount': buy_amount,  # 실제 사용한 금액
                                'entry_fee': paid_fee,
                                'entry_timestamp': datetime.now().isoformat()
                            })
                            
                            # 7. 업비트에서 실제 보유 재확인
                            time.sleep(2)
                            self._verify_holding(ticker)
                            
                            return True
                        else:
                            print(f"⚠️ 체결가 정보 없음")
                            # 체결은 되었으나 가격 정보가 없으면 보유 확인으로 복구
                            time.sleep(2)
                            currency = ticker.replace('KRW-', '')
                            actual_balance = self.upbit.get_balance(currency)
                            
                            if actual_balance > 0:
                                print(f"✅ 보유 확인: {actual_balance:.8f}개")
                                # 현재가로 대체
                                current_price = self.upbit.get_current_price(ticker)
                                
                                self.active_trade['status'] = 'ACTIVE'
                                self.active_trade['actual_entry_price'] = current_price
                                self.active_trade['actual_volume'] = actual_balance
                                self.active_trade['entry_fee'] = paid_fee
                                self.active_trade['entry_timestamp'] = datetime.now()
                                
                                self.db.update_trade_result(self.active_trade['trade_id'], {
                                    'status': 'ACTIVE',
                                    'actual_entry_price': current_price,
                                    'actual_volume': actual_balance,
                                    'entry_fee': paid_fee,
                                    'entry_timestamp': datetime.now().isoformat()
                                })
                                
                                return True
                    else:
                        # 체결량이 0인 경우만 실패 처리
                        print(f"❌ 주문 실패: {state} (체결량: 0)")
                        return False
            
            # 타임아웃 - 마지막으로 체결 여부 확인
            print("⏰ 체결 확인 타임아웃 - 최종 확인")
            
            final_order = self.upbit.get_order_status(order_uuid)
            if final_order:
                final_volume = float(final_order.get('executed_volume', 0))
                if final_volume > 0:
                    print(f"✅ 타임아웃 시점 체결 확인: {final_volume:.8f}개")
                    # 재귀 호출 없이 여기서 처리
                    executed_funds = float(final_order.get('executed_funds', 0))
                    avg_price = executed_funds / final_volume if final_volume > 0 else self.upbit.get_current_price(ticker)
                    
                    self.active_trade['status'] = 'ACTIVE'
                    self.active_trade['actual_entry_price'] = avg_price
                    self.active_trade['actual_volume'] = final_volume
                    self.active_trade['entry_timestamp'] = datetime.now()
                    
                    self.db.update_trade_result(self.active_trade['trade_id'], {
                        'status': 'ACTIVE',
                        'actual_entry_price': avg_price,
                        'actual_volume': final_volume,
                        'entry_timestamp': datetime.now().isoformat()
                    })
                    
                    return True
            
            # 완전 실패 시 주문 취소 시도
            try:
                self.upbit.cancel_order(order_uuid)
            except:
                pass
                
            return False
            
        except Exception as e:
            print(f"❌ 매수 실행 오류: {e}")
            traceback.print_exc()
            return False

    def _execute_and_verify_sell(self, ticker: str, target_price: Optional[float], exit_type: str) -> bool:
        """매도 실행 후 업비트에서 체결 확인"""
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
                # 🔴 안전장치: 현재가가 목표가보다 높으면 즉시 시장가 매도
                current_price = self.upbit.get_current_price(ticker)
                if current_price and current_price > target_price:
                    print(f"   ⚠️ 현재가({current_price:,.0f}원)가 목표가({target_price:,.0f}원)를 초과!")
                    print(f"   방식: 시장가로 즉시 매도 (안전장치 작동)")
                    order_uuid = self.upbit.sell_market_order(ticker, actual_balance)
                else:
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
            
            # 3. 체결 확인 (지정가는 60초, 시장가는 30초)
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

    def _execute_partial_sell(self, ticker: str, ratio: float, exit_type: str) -> bool:
                    """
                    V14: 부분 매도 실행 (70% 또는 30%)
                    
                    Args:
                        ticker: 코인 티커
                        ratio: 매도 비율 (0.7 = 70%, 1.0 = 100%)
                        exit_type: "TARGET_1", "TARGET_2", "BREAKEVEN"
                    
                    Returns:
                        bool: 매도 성공 여부
                    """
                    try:
                        print(f"\n💼 부분 매도 실행: {ratio*100:.0f}% ({exit_type})")
                        
                        # 현재 보유량 조회
                        balances = self.upbit.get_balances()
                        currency = ticker.replace('KRW-', '')
                        
                        holding = next((b for b in balances if b.get('currency') == currency), None)
                        if not holding:
                            print(f"   ❌ {ticker} 보유 정보 없음")
                            return False
                        
                        total_volume = float(holding.get('balance', 0))
                        if total_volume <= 0:
                            print(f"   ❌ 보유량 없음")
                            return False
                        
                        # 매도할 물량 계산
                        sell_volume = total_volume * ratio
                        
                        # 업비트 최소 주문 금액 체크 (5,000원)
                        current_price = self.upbit.get_current_price(ticker)
                        sell_amount = sell_volume * current_price
                        
                        if sell_amount < 5000:
                            print(f"   ⚠️ 매도 금액 {sell_amount:,.0f}원 < 5,000원 → 전량 매도로 전환")
                            sell_volume = total_volume
                            ratio = 1.0
                        
                        print(f"   📦 매도량: {sell_volume:.8f}개 (전체의 {ratio*100:.0f}%)")
                        print(f"   💰 예상 금액: {sell_amount:,.0f}원")
                        
                        # 시장가 매도 주문 (정상 작동 버전과 동일하게 처리)
                        order_uuid = self.upbit.sell_market_order(ticker, sell_volume)

                        if not order_uuid:
                            print(f"   ❌ 매도 주문 실패")
                            return False

                        print(f"   ✅ 매도 주문 성공: {order_uuid}")
                        
                        # 주문 체결 대기 (최대 30초)
                        time.sleep(3)
                        
                        for i in range(30):
                            order_info = self.upbit.get_order_status(order_uuid)
                            
                            if not order_info:
                                time.sleep(1)
                                continue
                            
                            state = order_info.get('state')
                            
                            if state == 'done':
                                # 체결 완료
                                executed_volume = float(order_info.get('executed_volume', 0))
                                paid_fee = float(order_info.get('paid_fee', 0))
                                trades = order_info.get('trades', [])
                                
                                if not trades:
                                    print("   ⚠️ 거래 내역 없음")
                                    return False
                                
                                # 평균 체결가 계산
                                total_price = sum(float(t.get('price', 0)) * float(t.get('volume', 0)) for t in trades)
                                avg_price = total_price / executed_volume if executed_volume > 0 else 0
                                
                                print(f"   ✅ 체결 완료!")
                                print(f"      체결량: {executed_volume:.8f}개")
                                print(f"      평균가: {avg_price:,.0f}원")
                                print(f"      수수료: {paid_fee:,.0f}원")
                                
                                # DB 업데이트 (exit_type에 따라)
                                actual_entry = self.active_trade.get('actual_entry_price', 0)
                                profit_loss = (avg_price - actual_entry) * executed_volume - paid_fee
                                profit_rate = ((avg_price - actual_entry) / actual_entry) * 100 if actual_entry > 0 else 0
                                
                                if exit_type == "TARGET_1":
                                    # ✅ T1 매도 기록 (수익/수수료 포함)
                                    self.db.update_trade_result(self.active_trade['trade_id'], {
                                        'target_1_reached_time': datetime.now().isoformat(),
                                        'target_1_exit_price': avg_price,
                                        'target_1_exit_volume': executed_volume,
                                        'target_1_profit': profit_loss,  # ✅ T1 수익 저장
                                        'target_1_fee': paid_fee  # ✅ T1 수수료 저장
                                    })
                                    
                                    # 남은 물량 업데이트
                                    original_volume = self.active_trade.get('original_volume', self.active_trade.get('actual_volume', 0))
                                    remaining_volume = original_volume * (1 - ratio)
                                    self.active_trade['actual_volume'] = remaining_volume
                                    
                                    if 'original_volume' not in self.active_trade:
                                        self.active_trade['original_volume'] = original_volume
                                    
                                    print(f"   📊 T1 매도 완료 - 남은 물량: {remaining_volume:.8f}개")
                                    print(f"   💰 T1 수익: {profit_loss:,.0f}원 (수익률: {profit_rate:+.2f}%)")
                                    
                                elif exit_type == "TARGET_2":
                                    # ✅ T2 매도 기록 (T1 수익 누적)
                                    # 1. DB에서 T1 데이터 조회
                                    trade_data = self.db.get_trade(self.active_trade['trade_id'])
                                    t1_profit = trade_data.get('target_1_profit', 0)
                                    t1_fee = trade_data.get('target_1_fee', 0)
                                    t1_volume = trade_data.get('target_1_exit_volume', 0)
                                    t1_price = trade_data.get('target_1_exit_price', 0)
                                    
                                    # 2. T1 + T2 누적 계산
                                    total_profit = t1_profit + profit_loss
                                    total_fee = t1_fee + paid_fee
                                    total_exit_volume = t1_volume + executed_volume
                                    
                                    # 3. 가중평균 청산가 계산
                                    weighted_exit_price = (
                                        (t1_price * t1_volume + avg_price * executed_volume) / total_exit_volume
                                    ) if total_exit_volume > 0 else avg_price
                                    
                                    # 4. 전체 수익률 재계산
                                    entry_amount = trade_data.get('entry_amount', 0)
                                    total_profit_rate = (total_profit / entry_amount) * 100 if entry_amount > 0 else 0
                                    
                                    print(f"   💰 T2 수익: {profit_loss:,.0f}원")
                                    print(f"   📊 전체 수익: {total_profit:,.0f}원 (T1: {t1_profit:,.0f} + T2: {profit_loss:,.0f})")
                                    print(f"   📈 전체 수익률: {total_profit_rate:+.2f}%")
                                    
                                    self.db.update_trade_result(self.active_trade['trade_id'], {
                                        'target_2_exit_price': avg_price,
                                        'target_2_exit_volume': executed_volume,
                                        'target_2_profit': profit_loss,
                                        'target_2_fee': paid_fee,
                                        'status': 'COMPLETED',
                                        'actual_exit_price': weighted_exit_price,  # ✅ 가중평균 청산가
                                        'exit_timestamp': datetime.now().isoformat(),
                                        'profit_loss': total_profit,  # ✅ 누적 수익
                                        'profit_rate': total_profit_rate,  # ✅ 전체 수익률
                                        'total_exit_fee': total_fee  # ✅ 총 수수료
                                    })
                                    
                                    self.active_trade['actual_volume'] = 0  # 전량 청산
                                    self.active_trade = None
                                    
                                elif exit_type == "BREAKEVEN":
                                    # ✅ 본절 청산 기록 (T1 수익 누적)
                                    # 1. DB에서 T1 데이터 조회
                                    trade_data = self.db.get_trade(self.active_trade['trade_id'])
                                    t1_profit = trade_data.get('target_1_profit', 0)
                                    t1_fee = trade_data.get('target_1_fee', 0)
                                    t1_volume = trade_data.get('target_1_exit_volume', 0)
                                    t1_price = trade_data.get('target_1_exit_price', 0)
                                    
                                    # 2. T1 + 본절 누적 계산
                                    total_profit = t1_profit + profit_loss
                                    total_fee = t1_fee + paid_fee
                                    total_exit_volume = t1_volume + executed_volume
                                    
                                    # 3. 가중평균 청산가 계산
                                    weighted_exit_price = (
                                        (t1_price * t1_volume + avg_price * executed_volume) / total_exit_volume
                                    ) if total_exit_volume > 0 else avg_price
                                    
                                    # 4. 전체 수익률 재계산
                                    entry_amount = trade_data.get('entry_amount', 0)
                                    total_profit_rate = (total_profit / entry_amount) * 100 if entry_amount > 0 else 0
                                    
                                    print(f"   💰 본절 청산: {profit_loss:,.0f}원")
                                    print(f"   📊 전체 수익: {total_profit:,.0f}원 (T1: {t1_profit:,.0f} + 본절: {profit_loss:,.0f})")
                                    print(f"   📈 전체 수익률: {total_profit_rate:+.2f}%")
                                    
                                    self.db.update_trade_result(self.active_trade['trade_id'], {
                                        'breakeven_exit_price': avg_price,
                                        'breakeven_exit_volume': executed_volume,
                                        'breakeven_profit': profit_loss,
                                        'breakeven_fee': paid_fee,
                                        'status': 'COMPLETED',
                                        'actual_exit_price': weighted_exit_price,  # ✅ 가중평균 청산가
                                        'exit_timestamp': datetime.now().isoformat(),
                                        'profit_loss': total_profit,  # ✅ 누적 수익 (T1 포함!)
                                        'profit_rate': total_profit_rate,  # ✅ 전체 수익률
                                        'total_exit_fee': total_fee  # ✅ 총 수수료
                                    })
                                    
                                    self.active_trade['actual_volume'] = 0
                                    self.active_trade = None
                                
                                return True
                            
                            time.sleep(1)
                        
                        print("   ⏰ 체결 대기 시간 초과")
                        return False
                        
                    except Exception as e:
                        print(f"   ❌ 부분 매도 실행 오류: {e}")
                        traceback.print_exc()
                        return False

    def _move_stop_to_breakeven(self, entry_price: float):
        """
        V14: T1 도달 시 손절가를 본절(진입가)로 이동
        
        Args:
            entry_price: 실제 진입가
        """
        try:
            self.active_trade['breakeven_stop'] = entry_price
            
            print(f"\n🛡️ 손절가 본절 이동!")
            print(f"   기존 손절가: {self.active_trade['strategy']['trading_parameters'].get('stop_loss_price', 0):,.0f}원")
            print(f"   새 손절가: {entry_price:,.0f}원 (진입가 = 본절)")
            print(f"   📌 이제 남은 30% 물량은 리스크 ZERO 상태!")
            
            # DB 기록
            self.db.update_trade_result(self.active_trade['trade_id'], {
                'breakeven_stop_moved': True
            })
            
        except Exception as e:
            print(f"   ⚠️ 본절 이동 실패: {e}")

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