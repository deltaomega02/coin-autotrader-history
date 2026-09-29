# main.py
# "OMNI Trading System의 메인 실행 파일 - 전체 거래 사이클을 관리하고 각 Phase를 순차적으로 실행하는 파일"

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from core.market_analyzer import MarketAnalyzer
from core.deep_analyzer import DeepAnalyzer
from core.strategy_maker import StrategyMaker
from core.trade_executor import TradeExecutor
from config.settings import settings

class OMNITradingSystem:

    # "시스템을 초기화하고 모든 컴포넌트를 생성하며 이전 거래를 복구하는 메서드" (인자: self)
    def __init__(self):
        print("\n" + "="*70)
        print("🔮 OMNI Trading System 초기화")
        print("="*70)
        
        # 핵심 컴포넌트 초기화
        self.market_analyzer = MarketAnalyzer()
        self.deep_analyzer = DeepAnalyzer()
        self.strategy_maker = StrategyMaker()
        self.trade_executor = TradeExecutor()  

        self.is_running = False
        self.current_session_id = None
        self.cycle_count = 0

        self._check_startup_status()

        self._display_gpt_cache_status()
        
    # "현재 시간대에 따라 대기 시간을 차등적으로 결정하는 메서드" (인자: self)
    def _get_wait_minutes(self) -> int:
        current_hour = datetime.now().hour
        
        # 위험한 시간 (새벽 1시 ~ 아침 9시)
        if 1 <= current_hour < 9:
            print("   -> 🌃 위험 시간대: 4시간(240분) 대기")
            return 240 
        
        # 활발한 시간
        else:
            print("   -> 🌇 활발한 시간대: 2시간(120분) 대기")
            return 120

    # "시작시 활성 거래 상태를 확인하고 출력하는 메서드" (인자: self)
    def _check_startup_status(self):
        active_summary = self.trade_executor.get_active_trade_summary()
        
        if active_summary:
            print(f"\n🎯 활성 거래 감지:")
            print(f"   {active_summary}")
            print("📋 이전 거래가 계속 진행됩니다")
            
            # 상세 정보 출력
            if self.trade_executor.active_trade:
                status = self.trade_executor.active_trade.get('status', '')
                if status == 'ACTIVE':
                    print("   💡 목표가 도달 시 자동 매도 또는 손절가 도달 시 자동 손절")
                elif status == 'WAITING_ENTRY':
                    print("   💡 진입가 도달 시 자동 매수 후 모니터링 시작")
                    
                # 예상 종료 시간 출력
                planned_exit = self.trade_executor.active_trade.get('planned_exit_timestamp')
                if planned_exit:
                    if isinstance(planned_exit, str):
                        planned_exit = datetime.fromisoformat(planned_exit)
                    remaining = (planned_exit - datetime.now()).total_seconds() / 3600
                    if remaining > 0:
                        print(f"   ⏰ 예상 종료까지: {remaining:.1f}시간")
        else:
            print("\n✅ 활성 거래 없음 - 새로운 거래 기회를 찾습니다")
    
    # "GPT-5 캐시 상태를 조회하여 출력하는 메서드" (인자: self)
    def _display_gpt_cache_status(self):
        try:
            from ai.gpt_client import GPTClient
            if not hasattr(self, 'gpt_client'):
                self.gpt_client = GPTClient()
            cache_status = self.gpt_client.get_cache_status()
            
            if cache_status['cached_phases']:
                print(f"\n📊 GPT-5 캐시 상태:")
                print(f"   세션 ID: {cache_status['session_id']}")
                print(f"   캐시된 Phase: {', '.join(cache_status['cached_phases'])}")
                for phase, age in cache_status['cache_age'].items():
                    print(f"   - {phase}: {age}")
        except Exception as e:
            print(f"⚠️ 캐시 상태 조회 실패: {e}")

    # "완전한 거래 사이클(Phase 1~4)을 실행하는 핵심 메서드" (인자: self)
    def run_trading_cycle(self):

        if self.trade_executor.is_trading_active():
            active_summary = self.trade_executor.get_active_trade_summary()
            print(f"\n⏳ 활성 거래 진행 중: {active_summary}")
            print("   새로운 거래 시작 불가 - 현재 거래 완료까지 대기")
            return

        self.cycle_count += 1

        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                session_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n{'='*70}")
                print(f"🔄 거래 사이클 #{self.cycle_count} 시작 - {session_time}")
                print(f"{'='*70}")

                self._start_new_gpt_session()
                
                # ==================== Phase 1: 시장 진단 ====================
                print("\n📊 Phase 1: 시장 진단 및 후보 선별...")
                phase1_start = time.time()
                
                market_result = self.market_analyzer.analyze_market_condition()
                
                phase1_elapsed = time.time() - phase1_start
                print(f"   ⏱️ Phase 1 소요시간: {phase1_elapsed:.1f}초")
                
                # Phase 1 실패 처리
                if market_result.get('error'):
                    print(f"❌ Phase 1 오류: {market_result['error']}")
                    return

                market_assessment = market_result.get('market_assessment', {})
                print(f"\n🌍 시장 평가:")
                print(f"   • BTC 트렌드: {market_assessment.get('btc_trend', 'N/A')}")
                print(f"   • 기회 개수: {market_assessment.get('opportunity_count', 0)}개")

                final_decision = market_result.get('final_decision', {})
                print(f"\n🎯 Phase 1 결정:")
                print(f"   • 액션: {final_decision.get('action', 'N/A').upper()}")
                print(f"   • TOP 3: {', '.join(final_decision.get('top_3_tickers', []))}")
                print(f"   • 신뢰도: {final_decision.get('confidence_level', 0)}%")

                if market_result.get('action') == 'wait':
                    wait_minutes = final_decision.get('wait_minutes', 120)
                    wait_reason = final_decision.get('wait_reason', '시장 조건 부적합')
                    
                    print(f"\n⏸️ 거래 대기 ({wait_minutes}분)")
                    print(f"   📝 사유: {wait_reason}")
                    
                    end_time = datetime.now() + timedelta(minutes=wait_minutes)
                    print(f"   ⏰ 재개 예정: {end_time.strftime('%H:%M:%S')}")
                    
                    time.sleep(wait_minutes * 60)
                    return
                
                # TOP 3 후보 추출
                top_3_candidates = final_decision.get('top_3_tickers', [])
                
                if not top_3_candidates:
                    print(f"\n⏸️ 적합한 거래 기회 없음 - 120분 대기")
                    time.sleep(7200)
                    return
                
                print(f"✅ TOP 3 후보: {', '.join(top_3_candidates)}")
                
                # ==================== Phase 2: 심층 분석 ====================
                print(f"\n🔍 Phase 2: 후보 심층 분석...")
                phase2_start = time.time()
                
                deep_result = self.deep_analyzer.analyze_candidates(top_3_candidates)
                
                phase2_elapsed = time.time() - phase2_start
                print(f"   ⏱️ Phase 2 소요시간: {phase2_elapsed:.1f}초")
                
                # Phase 2 실패 처리
                if deep_result.get('error'):
                    print(f"❌ Phase 2 오류: {deep_result['error']}")
                    return
                
                # Phase 2 최종 선정
                final_selection = deep_result.get('final_selection', {})
                print(f"\n🎯 Phase 2 결정:")
                print(f"   • 액션: {deep_result.get('action', 'N/A').upper()}")
                print(f"   • 선정 코인: {final_selection.get('selected_coin', 'None')}")
                print(f"   • 신뢰도: {final_selection.get('confidence_score', 0)}/100")
                
                # Phase 2 대기 결정 처리
                if deep_result.get('action') == 'wait':
                    print(f"\n⏸️ Phase 2 대기 결정")
                    
                    # GPT 응답에서 대기 시간 직접 가져오기 (기본값 120분)
                    wait_minutes = final_selection.get('wait_minutes', 120)
                    wait_reason = final_selection.get('wait_reason', '후보들이 최소 품질 기준 미달')
                    
                    print(f"   📊 대기 시간: {wait_minutes}분")
                    print(f"   📝 사유: {wait_reason}")
                    
                    end_time = datetime.now() + timedelta(minutes=wait_minutes)
                    
                    print(f"⏲️ {wait_minutes}분 후 Phase 1부터 재시작...")
                    print(f"   재개 예정: {end_time.strftime('%H:%M:%S')}")
                    
                    time.sleep(wait_minutes * 60)
                    
                    retry_count += 1
                    print(f"\n🔄 재시도 {retry_count}/{max_retries}")
                    continue
                
                # 최종 코인 선정
                selected_coin = final_selection.get('selected_coin', '')
                
                if not selected_coin or selected_coin.upper() == 'NONE':
                    print(f"⏸️ 최종 코인 선정 실패 - 적합한 코인 없음")
                    return
                
                print(f"\n✅ 최종 선정: {selected_coin}")
                print(f"   신뢰도: {final_selection.get('confidence_score', 0)}%")
                
                # ==================== Phase 3: 전략 수립 ====================
                print(f"\n📋 Phase 3: 거래 전략 수립...")
                phase3_start = time.time()
                
                strategy = self.strategy_maker.create_trading_strategy(selected_coin, deep_result)
                
                phase3_elapsed = time.time() - phase3_start
                print(f"   ⏱️ Phase 3 소요시간: {phase3_elapsed:.1f}초")
                
                # Phase 3 실패 처리
                if strategy.get('error'):
                    print(f"❌ Phase 3 오류: {strategy['error']}")
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
                    return
                
                print("✅ 거래 실행 완료 - 모니터링 시작")
                
                # 총 소요시간 출력
                total_elapsed = phase1_elapsed + phase2_elapsed + phase3_elapsed + phase4_elapsed
                print(f"\n⏱️ 총 분석 시간: {total_elapsed:.1f}초")
                
                # 거래 완료 대기
                self._wait_for_trade_completion(strategy.get('trade_id', 'unknown'))
                
                # ==================== 거래 완료 후 30분 대기 ====================
                print("\n" + "="*70)
                print("✅ 거래 사이클 완료")
                print("="*70)
                
                # 10분 대기
                print(f"\n⏰ 다음 거래까지 10분 대기...")
                end_time = datetime.now() + timedelta(minutes=10)
                print(f"   재개 예정: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 5분 후 한 번 알림
                time.sleep(300)
                print(f"   ⏳ 대기 중... 5분 남음 ({datetime.now().strftime('%H:%M:%S')})")
                time.sleep(300)
                
                print(f"\n🔄 대기 완료 - 새로운 사이클 준비")

                break
                
            except KeyboardInterrupt:
                print("\n⚠️ 사용자 중단 요청")
                raise
                
            except Exception as e:
                print(f"\n❌ 거래 사이클 오류: {e}")
                import traceback
                traceback.print_exc()
                
                retry_count += 1
                if retry_count < max_retries:
                    print(f"\n🔄 재시도 {retry_count}/{max_retries} - 30초 후...")
                    time.sleep(30)
                else:
                    print(f"\n❌ 최대 재시도 횟수 초과 - 사이클 종료")
                    break

    # "GPT-5 새 세션을 시작하고 캐시를 정리하는 메서드" (인자: self)
    def _start_new_gpt_session(self):
        try:
            from ai.gpt_client import GPTClient
            
            if not hasattr(self, 'gpt_client'):
                self.gpt_client = GPTClient()
            
            self.current_session_id = self.gpt_client._start_new_session()
            print(f"✅ GPT-5 세션 시작: {self.current_session_id}")
        except Exception as e:
            print(f"⚠️ GPT 세션 시작 실패: {e}")
            self.current_session_id = f"FALLBACK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # "수립된 전략 요약을 포맷팅하여 출력하는 메서드" (인자: self, strategy)
    def _display_strategy_summary(self, strategy: Dict[str, Any]):
        params = strategy.get('trading_parameters', {})
        
        if not params:
            return
        
        entry_price = params.get('entry_price', 0)
        target_price = params.get('target_price', 0)
        stop_loss_price = params.get('stop_loss_price', 0)
        
        if entry_price > 0:
            target_rate = (target_price - entry_price) / entry_price * 100
            stop_rate = (stop_loss_price - entry_price) / entry_price * 100
            
            print(f"\n📊 전략 요약:")
            print(f"   진입가: {entry_price:,.2f}원")
            print(f"   목표가: {target_price:,.2f}원 (+{target_rate:.2f}%)")
            print(f"   손절가: {stop_loss_price:,.2f}원 ({stop_rate:.2f}%)")
            print(f"   예상시간: {params.get('expected_duration_hours', 12):.1f}시간")
    
    # "거래가 완료될 때까지 대기하며 진행상황을 출력하는 메서드" (인자: self, trade_id)
    def _wait_for_trade_completion(self, trade_id: str):
        print(f"\n⏳ 거래 완료 대기 중... (ID: {trade_id})")
        
        last_status_time = time.time()
        status_interval = 60 
        
        while self.trade_executor.is_trading_active():
            current_time = time.time()

            if current_time - last_status_time >= status_interval:
                active_summary = self.trade_executor.get_active_trade_summary()
                if active_summary:
                    print(f"   📊 진행상황: {active_summary}")
                last_status_time = current_time
            
            time.sleep(10) 
        
        print(f"✅ 거래 완료!")

        if hasattr(self.trade_executor, 'last_trade_result'):
            result = self.trade_executor.last_trade_result
            profit_rate = result.get('profit_rate', 0)
            if profit_rate > 0:
                print(f"💰 수익: +{profit_rate:.2f}%")
            else:
                print(f"📉 손실: {profit_rate:.2f}%")
    
    # "최근 거래 통계를 조회하여 출력하는 선택적 메서드" (인자: self)
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
    
    # "연속 거래 모드를 시작하여 무한 루프로 거래를 실행하는 메서드" (인자: self)
    def start_continuous_trading(self):
        print("\n" + "="*70)
        print("🚀 OMNI Trading System 시작")
        print("="*70)
        print("⚠️  Ctrl+C로 중단 가능")
        print("🔄 프로그램 재시작시 이전 거래 자동 복구")
        print("="*70 + "\n")
        
        self.is_running = True
        last_cycle_time = 0
        
        try:
            while self.is_running:
                current_time = time.time()

                if not self.trade_executor.is_trading_active():
                    if current_time - last_cycle_time >= 1800:
                        self.run_trading_cycle()
                        last_cycle_time = current_time
                    else:
                        remaining = 1800 - (current_time - last_cycle_time)
                        if int(remaining) % 300 == 0 or remaining < 60:
                            if remaining > 0:
                                print(f"⏳ 다음 사이클까지: {remaining/60:.1f}분")
                        time.sleep(10)
                else:
                    if int(current_time) % 30 == 0: 
                        active_summary = self.trade_executor.get_active_trade_summary()
                        if active_summary:
                            print(f"\n📊 [모니터링] {active_summary}")
                    
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("\n\n🛑 시스템 종료 요청...")
            self.stop_system()
        except Exception as e:
            print(f"\n❌ 시스템 오류: {e}")
            import traceback
            traceback.print_exc()
            self.stop_system()
    
    # "시스템을 안전하게 종료하고 정리하는 메서드" (인자: self)
    def stop_system(self):
        print("\n" + "="*70)
        print("🛑 OMNI Trading System 종료 중...")
        print("="*70)
        
        self.is_running = False

        if self.trade_executor.is_trading_active():
            active_summary = self.trade_executor.get_active_trade_summary()
            print(f"\n⚠️ 활성 거래가 계속 진행 중입니다:")
            print(f"   {active_summary}")
            print(f"   💡 프로그램을 다시 시작하면 자동으로 복구됩니다")

        self._display_trading_stats()

        self.trade_executor.stop_monitoring()
        
        print("\n✅ OMNI Trading System 종료 완료")
        print(f"   총 실행 사이클: {self.cycle_count}회")
        print("="*70 + "\n")

# 모듈 레벨 함수:
# "프로그램의 진입점으로 실행 모드를 결정하고 시스템을 시작하는 함수" (인자: 없음)
def main():
    import sys

    omni = OMNITradingSystem()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--once":
            print("🔄 단일 거래 사이클 실행 모드")
            omni.run_trading_cycle()
        elif sys.argv[1] == "--test":
            print("🧪 테스트 모드 - 시스템 체크만 수행")
            print("✅ 시스템 초기화 성공")
            return
        elif sys.argv[1] == "--help":
            print("\n사용법:")
            print("  python main.py          # 연속 거래 모드 (기본)")
            print("  python main.py --once   # 단일 사이클 실행")
            print("  python main.py --test   # 시스템 체크")
            print("  python main.py --help   # 도움말")
            return
        else:
            print(f"❌ 알 수 없는 옵션: {sys.argv[1]}")
            print("   --help 옵션으로 사용법을 확인하세요")
            return
    else:
        omni.start_continuous_trading()


if __name__ == "__main__":
    main()