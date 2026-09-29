# core/reflector.py
# "Phase 5: 거래 완료 후 학습을 수행하고 원칙을 업데이트하는 반성 및 학습 파일"

import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from data.database import TradeDatabase
from ai.gpt_client import get_gpt_client
from config.settings import settings

class Reflector:

    # "Reflector 클래스를 초기화하고 필요한 구성 요소를 설정하는 메서드" (인자: self)
    def __init__(self):
        self.db = TradeDatabase()
        self.gpt = get_gpt_client()
        self.principles_file = settings.PRINCIPLES_FILE
        self._ensure_principles_file()
    
    # "원칙 파일이 존재하는지 확인하고 없으면 생성하는 메서드" (인자: self)
    def _ensure_principles_file(self):
            """Ensures the principles file exists and creates it if it doesn't."""
            os.makedirs(os.path.dirname(self.principles_file), exist_ok=True)
            
            if not os.path.exists(self.principles_file):
                with open(self.principles_file, 'w', encoding='utf-8') as f:
                    f.write("""### OMNI Trading System - Trading Principles (Ver 8.0 - Genesis)

### 📌 FIXED SECTION (DO NOT MODIFY)

#### System Architecture (How OMNI Operates)
1.  **Phase 1 (Scan):** Analyze market regime, select the most effective strategy, and find candidates.
2.  **Phase 2 (Select):** Deep-dive on candidates based on the selected strategy to choose the single best coin.
3.  **Phase 3 (Strategize):** Formulate a precise, strategy-aligned entry, target, and stop-loss plan.
4.  **Phase 4 (Execute):** Place orders and monitor the trade automatically.
5.  **Phase 5 (Evolve):** Analyze the result and update the Dynamic Rules on HOW to better apply the fixed Strategy Playbook.
**※ BTC market condition is the highest priority variable.**

#### Core System Constraints
* **Single Entry/Exit:** One entry, one target, one stop per trade.
* **No Manual Intervention:** Fully autonomous once initiated.
* **All-In, All-Out:** No partial profit taking.
* **No Averaging Down:** No adding to losing positions.
* **Sequential:** One trade at a time.

####  playbook>
The AI must choose ONE of these six strategies. These strategies themselves are fixed and cannot be changed.

1.  **Strategy A: Momentum Breakout (모멘텀 돌파)**
    -   **Best Used When:** The market is in a clear, high-volume BULL trend.
    -   **Signals:** Coins already breaking out with massive volume and strong RSI.

2.  **Strategy B: Pre-Breakout Condensation (폭발 직전 포착)**
    -   **Best Used When:** The market is SIDEWAYS, consolidating, or uncertain.
    -   **Signals:** 4H Bollinger Band Squeeze, rising OBV, Bullish Divergence.

3.  **Strategy C: Blue-Chip Reversal (대장주 반등 매매)**
    -   **Best Used When:** The market is "risk-off" after a drop but showing signs of bottoming.
    -   **Signals:** Major altcoins (ETH, XRP, SOL etc.) showing relative strength at a major support level.

4.  **Strategy D: Mean Reversion ('고무줄' 전략)**
    -   **Best Used When:** A specific, sound coin has dropped too far, too fast without a market-wide reason.
    -   **Signals:** Deeply oversold RSI (<30) far below its 1H 20EMA, touching the lower Bollinger Band.

5.  **Strategy E: Range Trading ('박스권' 매매)**
    -   **Best Used When:** The market is boring, low-volume, and directionless.
    -   **Signals:** A clear, well-tested horizontal range on the 4H chart. Buy near support, sell near resistance.

6.  **Strategy F: Narrative Momentum ('주도 테마' 추종)**
    -   **Best Used When:** A specific theme (e.g., AI, GameFi) is dominating market volume and attention.
    -   **Signals:** Multiple coins from the same category are in the top gainers list.

---

### 📊 DYNAMIC SECTION (Continuously updated by the AI)

#### Market State Analysis
* ⚠️ **Overheat Filter:** If a coin's 1h volume > 200% of average, avoid entry (pump & dump risk).
* 🟡 **BTC Weakness Filter:** If BTC 1h change < -0.5%, pause new long entries.

#### Position Sizing
* **Market Trend Multiplier:** BULL: 100%, SIDEWAYS: 60%, BEAR: 30% of base position size.

#### Core Strategy: DOs & DON'Ts

##### 🟢 DO THIS: AI learns how to better SELECT and APPLY the fixed strategies.
1.  Analyze the Market Regime to select the single best strategy from the FIXED Strategy Playbook.
2.  Find setups that perfectly match the signals of the CHOSEN strategy.
3.  (This rule can be updated by AI based on experience)

##### 🔴 DON'T DO THIS: AI learns which combinations to avoid.
1.  **Strategy Mismatch:** Do not use a Momentum strategy in a BEAR market.
2.  **Chasing Pumps:** Never chase a coin that has already pumped >+5% in the last hour.
3.  **Unconfirmed Moves:** Ignore any price action not confirmed by significant volume.

#### Exit Rules
* **Stop-Loss:** Place stop at a price that structurally invalidates the chosen strategy's thesis.
* **Take-Profit:** Aim for a high Risk:Reward ratio (minimum 1:2), targeting a major resistance level.
* **Early Exit:** If momentum dies after entry, exit at the entry price to preserve capital.

#### ⚡ Quick Decision Checklist
* □ **Market-Strategy Fit:** Is the chosen strategy from the playbook appropriate for the current market? (If NO → CANCEL)
* □ **Signal Confirmation:** Are the signals for the chosen strategy clear and confirmed by volume? (If NO → CANCEL)
* □ **High R:R Setup:** Is the Risk:Reward ratio at least 1:2 with a clear stop-loss? (If NO → CANCEL)

**Only when all checks are passed, execute the trade with the calculated position size.**
""")
        
    # "거래 완료 후 즉시 원칙을 업데이트하는 메서드" (인자: self, trade_id, is_recovered)
    # def update_principles_after_trade(self, trade_id: str, is_recovered: bool = False) -> bool:
    #     try:
    #         if is_recovered:
    #             print(f"🔍 복구된 거래의 원칙 업데이트 중... (ID: {trade_id})")
    #         else:
    #             print(f"🔍 거래 완료, 원칙 업데이트 시작... (ID: {trade_id})")
            
    #         # 1. DB에서 거래 데이터 조회
    #         recent_trades = self.db.get_recent_trades(limit=1)
    #         if not recent_trades or recent_trades[0]['trade_id'] != trade_id:
    #             # 복구 모드에서 특정 거래 조회
    #             if is_recovered and hasattr(self.db, 'get_trade_by_id'):
    #                 trade_data = self.db.get_trade_by_id(trade_id)
    #                 if not trade_data:
    #                     print(f"❌ 거래 데이터를 찾을 수 없음: {trade_id}")
    #                     return False
    #             else:
    #                 print(f"❌ 거래 데이터를 찾을 수 없음: {trade_id}")
    #                 return False
    #         else:
    #             trade_data = recent_trades[0]
            
    #         # 2. 거래 결과 준비
    #         trade_result = {
    #             'trade_id': trade_id,
    #             'symbol': trade_data['coin_ticker'],
    #             'entry_price': trade_data['entry_price'],
    #             'actual_entry_price': trade_data['actual_entry_price'],
    #             'target_price': trade_data['target_price'],
    #             'stop_loss_price': trade_data['stop_loss_price'],
    #             'exit_price': trade_data['actual_exit_price'],

    #             'profit_amount_krw': trade_data['profit_loss'],  
    #             'profit_rate_percent': trade_data['profit_rate'],  
                
    #             'status': trade_data['status'],
    #             'entry_reason': trade_data.get('entry_reason', ''),
    #             'exit_reason': trade_data.get('exit_reason', ''),

    #             'holding_period': self._calculate_holding_period(
    #                 trade_data.get('timestamp'),  
    #                 trade_data.get('exit_timestamp')  
    #             )
    #         }
            
    #         # 수익률 검증 계산
    #         if (trade_result['actual_entry_price'] and 
    #             trade_result['exit_price'] and 
    #             trade_result['actual_entry_price'] > 0):
                
    #             computed_rate = ((trade_result['exit_price'] - trade_result['actual_entry_price']) 
    #                         / trade_result['actual_entry_price'] * 100)
    #             trade_result['computed_profit_rate'] = computed_rate
                
    #             # 검증: 제공된 수익률과 계산된 수익률 비교
    #             if trade_result['profit_rate_percent'] is not None:
    #                 rate_diff = abs(trade_result['profit_rate_percent'] - computed_rate)
    #                 if rate_diff > 1.0:  # 1% 포인트 이상 차이
    #                     print(f"   ⚠️ 수익률 불일치 감지: DB={trade_result['profit_rate_percent']:.2f}%, "
    #                         f"계산={computed_rate:.2f}% (차이: {rate_diff:.2f}%p)")
    #                     # 계산된 값을 사용
    #                     trade_result['profit_rate_percent'] = computed_rate
    #                     print(f"   ✅ 계산된 수익률로 교정: {computed_rate:.2f}%")
            
    #         # 3. GPT 클라이언트에서 캐시된 Phase 데이터 가져오기
    #         phase_cache = {}
    #         if hasattr(self.gpt, 'response_cache'):
    #             phase_cache = {
    #                 'phase1': self.gpt.response_cache.get('phase1'),
    #                 'phase2': self.gpt.response_cache.get('phase2'),
    #                 'phase3': self.gpt.response_cache.get('phase3')
    #             }
    #             print(f"   📦 캐시된 Phase 데이터 사용 (세션: {self.gpt.current_session_id})")
            
    #         # 4. 기존 원칙 읽기
    #         existing_principles = self._read_principles()
            
    #         # 5. GPT를 통해 원칙 업데이트
    #         updated_principles = self.gpt.generate_updated_principles_after_trade(
    #             trade_result=trade_result,
    #             phase_cache=phase_cache,
    #             existing_principles=existing_principles
    #         )
            
    #         # 복구된 응답인지 확인
    #         if hasattr(self.gpt, 'last_response_was_recovered') and self.gpt.last_response_was_recovered:
    #             print("⚠️ 원칙 생성 중 JSON 복구됨 - 데이터 손실 우려로 기존 원칙 유지")
    #             return False
            
    #         if not updated_principles:
    #             print("⚠️ 원칙 생성 실패 - 기존 원칙 유지")
    #             return False
            
    #         # 원칙 형식 기본 검증
    #         if not isinstance(updated_principles, str) or len(updated_principles) < 100:
    #             print(f"⚠️ 원칙 형식 오류 (길이: {len(updated_principles) if updated_principles else 0}) - 기존 원칙 유지")
    #             return False
            
    #         # 6. 원칙 파일 저장
    #         self._save_principles(updated_principles)
            
    #         # 7. 통계 정보 출력
    #         stats = self.get_trading_statistics()
    #         if stats.get('completed_trades', 0) > 0:
    #             print(f"✅ 원칙 업데이트 완료 (누적 거래: {stats['completed_trades']}개, "
    #                 f"승률: {stats.get('win_rate', 0):.1f}%, "
    #                 f"평균 수익률: {stats.get('avg_profit_rate', 0):.2f}%)")
    #         else:
    #             print("✅ 원칙 업데이트 완료")

    #         return True
            
    #     except Exception as e:
    #         print(f"❌ 원칙 업데이트 오류: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return False

    # "거래 보유 기간을 계산하여 문자열로 반환하는 메서드" (인자: self, entry_timestamp, exit_timestamp)
    def _calculate_holding_period(self, entry_timestamp: str, exit_timestamp: str = None) -> str:
        try:
            if not entry_timestamp:
                return "Unknown"

            if isinstance(entry_timestamp, str):
                entry_time = datetime.fromisoformat(entry_timestamp.replace('Z', '+00:00'))
            else:
                entry_time = entry_timestamp

            if exit_timestamp:
                if isinstance(exit_timestamp, str):
                    exit_time = datetime.fromisoformat(exit_timestamp.replace('Z', '+00:00'))
                else:
                    exit_time = exit_timestamp
            else:
                exit_time = datetime.now()

            duration = exit_time - entry_time

            total_seconds = duration.total_seconds()
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            
            if hours > 0:
                return f"{hours}시간 {minutes}분"
            else:
                return f"{minutes}분"
                
        except Exception as e:
            print(f"⚠️ 보유 기간 계산 오류: {e}")
            return "Unknown"
    
    # "기존 원칙 파일을 읽어 문자열로 반환하는 메서드" (인자: self)
    def _read_principles(self) -> str:
        try:
            if os.path.exists(self.principles_file):
                with open(self.principles_file, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            print(f"⚠️ 원칙 파일 읽기 실패: {e}")
            return ""
    
    # "원칙을 파일에 저장하는 메서드" (인자: self, principles)
    def _save_principles(self, principles: str):
        try:
            with open(self.principles_file, 'w', encoding='utf-8') as f:
                f.write(principles)
        except Exception as e:
            print(f"⚠️ 원칙 파일 저장 실패: {e}")
    
    # "장기 원칙과 단기 거래 내역을 조회하는 메서드" (인자: self, limit)
    # def get_recent_memory(self, limit: int = 5) -> Dict[str, str]:
    #     try:
    #         # 장기 기억 (Principles.md)
    #         long_term_memory = self._read_principles()
            
    #         # 단기 기억 - 최근 완료된 거래 내역
    #         recent_trades = self.db.get_recent_trades(limit=limit)
            
    #         # 완료된 거래만 필터링
    #         completed_trades = [t for t in recent_trades if t.get('status') == 'COMPLETED']
            
    #         if completed_trades:
    #             short_term_memory = f"최근 완료된 {len(completed_trades)}개 거래:\n"
                
    #             for i, trade in enumerate(completed_trades[:limit], 1):
    #                 profit_rate = trade.get('profit_rate', 0)
    #                 profit_emoji = "✅" if profit_rate > 0 else "❌"
                    
    #                 # 거래 시간 계산
    #                 holding_period = self._calculate_holding_period(
    #                     trade.get('timestamp'),
    #                     trade.get('exit_timestamp')
    #                 )
                    
    #                 short_term_memory += (
    #                     f"{i}. {trade['coin_ticker']} {profit_emoji} "
    #                     f"수익률: {profit_rate:+.2f}% "
    #                     f"(보유: {holding_period})\n"
    #                 )
    #         else:
    #             short_term_memory = "최근 완료된 거래 없음"
            
    #         return {
    #             'long_term': long_term_memory,
    #             'short_term': short_term_memory
    #         }
            
    #     except Exception as e:
    #         print(f"⚠️ 메모리 로드 실패: {e}")
    #         return {
    #             'long_term': '',
    #             'short_term': '메모리 로드 실패'
    #         }
    
    # "전체 거래 통계를 계산하여 반환하는 메서드" (인자: self)
    def get_trading_statistics(self) -> Dict[str, Any]:
        try:
            all_trades = self.db.get_recent_trades(limit=100)
            completed_trades = [t for t in all_trades if t.get('status') == 'COMPLETED']
            
            if not completed_trades:
                return {
                    'completed_trades': 0,
                    'win_rate': 0,
                    'avg_profit_rate': 0,
                    'total_profit': 0
                }

            wins = [t for t in completed_trades if t.get('profit_rate', 0) > 0]
            losses = [t for t in completed_trades if t.get('profit_rate', 0) <= 0]
            
            total_profit = sum(t.get('profit_loss', 0) for t in completed_trades)
            avg_profit_rate = sum(t.get('profit_rate', 0) for t in completed_trades) / len(completed_trades)
            
            return {
                'completed_trades': len(completed_trades),
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': (len(wins) / len(completed_trades) * 100) if completed_trades else 0,
                'avg_profit_rate': avg_profit_rate,
                'total_profit': total_profit
            }
            
        except Exception as e:
            print(f"⚠️ 통계 조회 실패: {e}")
            return {
                'completed_trades': 0,
                'win_rate': 0,
                'avg_profit_rate': 0,
                'total_profit': 0
            }