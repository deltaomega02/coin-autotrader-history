# main.py
# "OMNI Trading System - 3-Phase 실행 (Phase 2 제거)"

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from core.market_analyzer import MarketAnalyzer
from core.strategy_maker import StrategyMaker
from core.trade_executor import TradeExecutor
from config.settings import settings

class OMNITradingSystem:

    # "Initialize OMNI Trading System" (args: self)
    def __init__(self):
        print("\n" + "="*70)
        print("🔮 OMNI Trading System 초기화")
        print("="*70)
        
        # 3-Phase 컴포넌트 초기화
        self.market_analyzer = MarketAnalyzer()
        self.strategy_maker = StrategyMaker()
        self.trade_executor = TradeExecutor()  

        self.is_running = False
        self.cycle_count = 0

        self._check_startup_status()
        
    # "Check active trade status on startup" (args: self)
    def _check_startup_status(self):
        active_summary = self.trade_executor.get_active_trade_summary()
        
        if active_summary:
            print(f"\n🎯 활성 거래 감지:")
            print(f"   {active_summary}")
            print("📋 이전 거래가 계속 진행됩니다")
            
            if self.trade_executor.active_trade:
                status = self.trade_executor.active_trade.get('status', '')
                if status == 'ACTIVE':
                    print("   💡 목표가 도달 시 자동 매도")
                elif status == 'WAITING_ENTRY':
                    print("   💡 진입가 도달 시 자동 매수")
        else:
            print("\n✅ 활성 거래 없음 - 새로운 기회 탐색")

    # "Run complete 3-Phase trading cycle" (args: self)
    def run_trading_cycle(self):
        
        # 활성 거래 체크
        if self.trade_executor.is_trading_active():
            active_summary = self.trade_executor.get_active_trade_summary()
            print(f"\n⏳ 활성 거래 진행 중: {active_summary}")
            print("   현재 거래 완료까지 대기")
            return

        self.cycle_count += 1
        
        try:
            session_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n{'='*70}")
            print(f"🔄 거래 사이클 #{self.cycle_count} 시작 - {session_time}")
            print(f"{'='*70}")
            
            # ==================== Phase 1: Gemini 시장 분석 ====================
            print("\n📊 Phase 1: Gemini 2.5 Pro 시장 분석...")
            phase1_start = time.time()
            
            market_result = self.market_analyzer.analyze_market_condition()
            
            phase1_elapsed = time.time() - phase1_start
            print(f"   ⏱️ Phase 1 소요시간: {phase1_elapsed:.1f}초")
            
            # Phase 1 실패 처리
            if market_result.get('error'):
                print(f"❌ Phase 1 오류: {market_result['error']}")
                self._wait_and_retry(60)
                return

            # Phase 1 결과 확인
            action = market_result.get('action', 'wait')
            
            if action == 'wait':
                wait_minutes = market_result.get('wait_minutes', 30)
                reason = market_result.get('reason', '적합한 기회 없음')
                
                print(f"\n⏸️ 거래 대기 결정")
                print(f"   📝 사유: {reason}")
                print(f"   ⏰ 대기: {wait_minutes}분")
                
                self._wait_and_retry(wait_minutes * 60)
                return
            
            # 선정된 코인 확인
            selected_coin = market_result.get('selected_coin', '')
            signal_score = market_result.get('signal_score', 0)
            confidence = market_result.get('confidence_level', 0)
            
            if not selected_coin:
                print(f"\n⏸️ 선정된 코인 없음 - 30분 대기")
                self._wait_and_retry(1800)
                return
            
            print(f"\n✅ Phase 1 완료:")
            print(f"   🎯 선정: {selected_coin}")
            print(f"   📊 신호: {signal_score}점")
            print(f"   🔮 신뢰도: {confidence}%")
            
            # ==================== Phase 3: GPT-5 전략 수립 ====================
            print(f"\n📋 Phase 3: GPT-5 자율 전략 수립...")
            phase3_start = time.time()
            
            strategy = self.strategy_maker.create_trading_strategy(
                selected_coin, 
                market_result  # Phase 1 결과 전달
            )
            
            phase3_elapsed = time.time() - phase3_start
            print(f"   ⏱️ Phase 3 소요시간: {phase3_elapsed:.1f}초")
            
            # Phase 3 실패 처리
            if strategy.get('error'):
                print(f"❌ Phase 3 오류: {strategy['error']}")
                self._wait_and_retry(60)
                return
            
            # 전략 요약 출력
            self._display_strategy_summary(strategy)
            
            # ==================== Phase 4: 거래 실행 ====================
            print(f"\n🚀 Phase 4: 거래 실행...")
            phase4_start = time.time()
            
            execution_result = self.trade_executor.execute_trade(strategy)
            
            phase4_elapsed = time.time() - phase4_start
            print(f"   ⏱️ Phase 4 소요시간: {phase4_elapsed:.1f}초")
            
            # Phase 4 실패 처리
            if execution_result.get('error'):
                print(f"❌ Phase 4 오류: {execution_result['error']}")
                self._wait_and_retry(60)
                return
            
            print("✅ 거래 실행 완료 - 모니터링 시작")
            
            # 총 소요시간
            total_elapsed = phase1_elapsed + phase3_elapsed + phase4_elapsed
            print(f"\n⏱️ 총 처리 시간: {total_elapsed:.1f}초")
            
            # 거래 완료 대기
            self._wait_for_trade_completion(strategy.get('trade_id', 'unknown'))
            
            # 거래 완료 후
            print("\n" + "="*70)
            print("✅ 거래 사이클 완료")
            print("="*70)
            
            # 다음 사이클까지 대기
            self._wait_and_retry(600)  # 10분 대기
            
        except KeyboardInterrupt:
            print("\n⚠️ 사용자 중단 요청")
            raise
            
        except Exception as e:
            print(f"\n❌ 거래 사이클 오류: {e}")
            import traceback
            traceback.print_exc()
            self._wait_and_retry(300)  # 5분 대기

    # "Display strategy summary" (args: self, strategy)
    def _display_strategy_summary(self, strategy: Dict[str, Any]):
        params = strategy.get('trading_parameters', {})
        
        if not params:
            return
        
        ticker = params.get('coin_ticker', '')
        entry = params.get('entry_price', 0)
        
        # V14: 2개 목표가
        target1 = params.get('target_price_1', 0)
        target2 = params.get('target_price_2', 0)
        split_ratio = params.get('target_split_ratio', 0.7)
        
        stop = params.get('stop_loss_price', 0)
        position = params.get('position_size_percent', 50)
        
        if entry > 0:
            # V14: 2개 목표가 수익률 계산
            target1_rate = (target1 - entry) / entry * 100 if target1 > 0 else 0
            target2_rate = (target2 - entry) / entry * 100 if target2 > 0 else 0
            stop_rate = (stop - entry) / entry * 100
            
            # V14: 혼합 수익률
            if target1 > 0 and target2 > 0:
                blended_rate = (target1_rate * split_ratio) + (target2_rate * (1 - split_ratio))
            else:
                blended_rate = target1_rate
            
            print(f"\n📊 전략 요약 (V14: 2-Target):")
            print(f"   코인: {ticker}")
            print(f"   진입가: {entry:,.0f}원")
            
            # V14: 2개 목표가 표시
            if target1 > 0:
                print(f"   🎯 목표가 1: {target1:,.0f}원 (+{target1_rate:.2f}%) [{split_ratio*100:.0f}% 청산]")
            if target2 > 0:
                print(f"   🚀 목표가 2: {target2:,.0f}원 (+{target2_rate:.2f}%) [{(1-split_ratio)*100:.0f}% 추격]")
            
            print(f"   🛑 손절가: {stop:,.0f}원 ({stop_rate:.2f}%)")
            print(f"   💼 포지션: {position}%")
            
            # V14: 혼합 수익률 표시
            if target1 > 0 and target2 > 0:
                print(f"   📈 혼합 수익률: +{blended_rate:.2f}% (가중평균)")

    # "Wait for trade completion" (args: self, trade_id)
    def _wait_for_trade_completion(self, trade_id: str):
        print(f"\n⏳ 거래 완료 대기 중... (ID: {trade_id})")
        
        last_status_time = time.time()
        status_interval = 60
        
        while self.trade_executor.is_trading_active():
            current_time = time.time()
            
            if current_time - last_status_time >= status_interval:
                active_summary = self.trade_executor.get_active_trade_summary()
                if active_summary:
                    print(f"   📊 상태: {active_summary}")
                last_status_time = current_time
            
            time.sleep(10)
        
        print(f"✅ 거래 완료!")
    
    # "Wait and show countdown" (args: self, seconds)
    def _wait_and_retry(self, seconds: int):
        minutes = seconds / 60
        end_time = datetime.now() + timedelta(seconds=seconds)
        
        if minutes >= 1:
            print(f"\n⏰ {minutes:.1f}분 대기...")
            print(f"   재개: {end_time.strftime('%H:%M:%S')}")
        
        # 5분마다 알림
        while seconds > 0:
            if seconds > 300:
                time.sleep(300)
                seconds -= 300
                remaining = seconds / 60
                if remaining > 0:
                    print(f"   ⏳ {remaining:.1f}분 남음")
            else:
                time.sleep(seconds)
                break
    
    # "Display trading statistics" (args: self)
    def _display_trading_stats(self):
        try:
            from data.database import TradeDatabase
            db = TradeDatabase()
            recent_trades = db.get_recent_trades(limit=10)
            
            if recent_trades:
                completed = [t for t in recent_trades if t.get('status') == 'COMPLETED']
                if completed:
                    wins = sum(1 for t in completed if t.get('profit_rate', 0) > 0)
                    total = len(completed)
                    win_rate = (wins / total * 100) if total > 0 else 0
                    
                    print(f"\n📈 최근 거래 통계:")
                    print(f"   총 거래: {total}회")
                    print(f"   승률: {win_rate:.1f}%")
        except:
            pass
    
    # "Start continuous trading mode" (args: self)
    def start_continuous_trading(self):
        print("\n" + "="*70)
        print("🚀 OMNI Trading System 시작")
        print("   3-Phase System (Gemini + GPT-5)")
        print("="*70)
        print("⚠️  Ctrl+C로 중단 가능")
        print("🔄 재시작시 거래 자동 복구")
        print("="*70 + "\n")
        
        self.is_running = True
        
        try:
            while self.is_running:
                if not self.trade_executor.is_trading_active():
                    self.run_trading_cycle()
                else:
                    # 활성 거래 모니터링
                    active_summary = self.trade_executor.get_active_trade_summary()
                    if active_summary:
                        print(f"\n📊 [모니터링] {active_summary}")
                    
                    time.sleep(60)
                    
        except KeyboardInterrupt:
            print("\n\n🛑 시스템 종료 요청...")
            self.stop_system()
        except Exception as e:
            print(f"\n❌ 시스템 오류: {e}")
            import traceback
            traceback.print_exc()
            self.stop_system()
    
    # "Stop system safely" (args: self)
    def stop_system(self):
        print("\n" + "="*70)
        print("🛑 OMNI Trading System 종료 중...")
        print("="*70)
        
        self.is_running = False

        if self.trade_executor.is_trading_active():
            active_summary = self.trade_executor.get_active_trade_summary()
            print(f"\n⚠️ 활성 거래 진행 중:")
            print(f"   {active_summary}")
            print(f"   💡 재시작시 자동 복구됩니다")

        self._display_trading_stats()
        self.trade_executor.stop_monitoring()
        
        print("\n✅ OMNI Trading System 종료")
        print(f"   실행 사이클: {self.cycle_count}회")
        print("="*70 + "\n")

# "Main entry point" (args: None)
def main():
    import sys

    omni = OMNITradingSystem()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--once":
            print("🔄 단일 사이클 실행")
            omni.run_trading_cycle()
        elif sys.argv[1] == "--test":
            print("🧪 테스트 모드")
            print("✅ 시스템 초기화 성공")
            return
        elif sys.argv[1] == "--help":
            print("\n사용법:")
            print("  python main.py          # 연속 거래 (기본)")
            print("  python main.py --once   # 단일 사이클")
            print("  python main.py --test   # 시스템 체크")
            print("  python main.py --help   # 도움말")
            return
        else:
            print(f"❌ 알 수 없는 옵션: {sys.argv[1]}")
            return
    else:
        omni.start_continuous_trading()


if __name__ == "__main__":
    main()