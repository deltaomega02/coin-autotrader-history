"""ATHENA — Smart DCA + AI Guardian.

학술 SOTA 통합:
- UCLA: BTC DCA 3년 100% 양수 (검증)
- FinAgent (arxiv 2402.18485): Multimodal AI agent +36% alpha
- CryptoTrade (EMNLP 2024): Reflective LLM agent
- Pi Cycle / MVRV Z-Score: 사이클 위치

운영:
- 매일 02:00 UTC: DCA 자동 매수 (코드, AI 호출 X)
  매수량 = base × 마지막 AI multiplier (0.0-2.0)
- 매주 일요일 09:00 KST: AI Guardian 점검 (1회)
- 24시간 monitoring: 가격 -10% / 위기 뉴스 → AI 즉시 호출

"""

import sys
import signal
import time
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from config import (
    setup_logging, get_logger,
    BYBIT, ATHENA, AGENTIC, SAFETY, SCHEDULER,
)
from ai import run_decision
from core import safety, portfolio_manager, dca_engine, emergency_monitor
from exchange import bybit_spot
from database import db
from utils import telegram

setup_logging()
logger = get_logger("main")

# ─ 스케줄 상수 ─
DCA_HOUR_UTC = 2          # 매일 02:00 UTC
GUARDIAN_DAY_UTC = 6      # 일요일 (KST 일요일 09:00 = UTC 일요일 00:00)
GUARDIAN_HOUR_UTC = 0
EMERGENCY_CHECK_INTERVAL_MIN = 15  # 15분마다 위기 체크


class Athena:
    """Smart DCA + AI Guardian 오케스트레이터."""

    def __init__(self):
        self.running = False
        self.paper_mode = ATHENA.PAPER_MODE

        # 상태
        self.cycle_count = 0
        self.consecutive_errors = 0
        self.current_multiplier = 1.0   # 마지막 Guardian 결정
        self.last_decisions: list = []  # 안티패턴 차단용 (같은 결정 반복)
        self.current_target_weights = None

        # 마지막 실행 timestamps
        self.last_dca_date = None        # YYYY-MM-DD (중복 방지)
        self.last_guardian_date = None
        self.last_emergency_check = 0    # epoch

    def start(self):
        logger.info("=" * 70)
        logger.info("ATHENA — Smart DCA + AI Guardian")
        logger.info(f"Mode: {'PAPER' if self.paper_mode else 'LIVE'}")
        logger.info(f"Network: {'TESTNET' if BYBIT.USE_TESTNET else 'MAINNET'}")
        logger.info(f"AI: {AGENTIC.MODEL_ID}")
        logger.info(f"Tools: {len(__import__('ai').ALL_TOOLS)}")
        logger.info(f"DCA: 매일 02:00 UTC (base × multiplier)")
        logger.info(f"Guardian: 매주 일요일 (KST 09:00)")
        logger.info(f"Emergency: 15분마다 모니터링")
        logger.info("=" * 70)

        self.running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # 시작 잔고
        try:
            portfolio = bybit_spot.get_portfolio_value_usdt()
            total = portfolio.get("total_usdt", 0)
            logger.info(f"시작 잔고: ${total:.2f}")
            telegram.system_start(self.paper_mode, total)
            db.save_snapshot(
                cycle_id=None,
                total_value=total,
                weights=portfolio.get("weights", {}),
                values=portfolio.get("values", {}),
            )
        except Exception as e:
            logger.error(f"시작 잔고 조회 실패: {e}")
            if not self.paper_mode:
                logger.error("실전 모드 — 잔고 없이 가동 불가")
                return

        # 시작 시 Guardian — 최근 결정 있으면 스킵 + 이전 multiplier 복원
        # 재시작이 잦아도 매번 새 매수 결정 X
        if not self._restore_from_recent_decision():
            logger.info("최근 결정 없음 → 초기 Guardian 실행")
            self._run_guardian(trigger="initial")

        # 메인 루프
        self._main_loop()

    def _restore_from_recent_decision(self) -> bool:
        """DB에서 최근 24h 내 Guardian 결정 찾아 multiplier 복원.

        Returns:
            True = 복원 성공 (Guardian 스킵)
            False = 최근 결정 없음 (Guardian 실행 필요)
        """
        try:
            recent = db.get_recent_decisions(days=1)
            if not recent:
                return False

            from datetime import datetime, timedelta, timezone
            now = datetime.now(timezone.utc)

            for r in recent:
                # 24h 이내만
                try:
                    ts_str = r["timestamp"]
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    decision_ts = datetime.fromisoformat(ts_str)
                    if (now - decision_ts) > timedelta(hours=24):
                        continue
                except (ValueError, KeyError):
                    continue

                # manager_json에서 multiplier 추출
                manager_json = r.get("manager_json")
                if not manager_json:
                    continue
                try:
                    manager = json.loads(manager_json)
                    if not isinstance(manager, dict):
                        continue
                    dca = manager.get("dca_decision", {})
                    mult = dca.get("multiplier")
                    if mult is None:
                        continue
                    self.current_multiplier = float(mult)
                    self.last_decisions.append(manager)
                    logger.info(
                        f"최근 결정 복원: multiplier {self.current_multiplier:.2f} "
                        f"(at {ts_str}) — Guardian 스킵"
                    )
                    return True
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

            return False
        except Exception as e:
            logger.error(f"결정 복원 실패: {e}")
            return False

    def _main_loop(self):
        """1분마다 polling — 각 작업 시간 도달 시 실행."""
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")

                # 1. DCA 체크 (매일 02:00 UTC)
                if (now.hour >= DCA_HOUR_UTC and
                        self.last_dca_date != today_str):
                    self._run_dca()
                    self.last_dca_date = today_str

                # 2. Guardian 체크 (매주 일요일 KST 09:00 = UTC 일요일 00:00)
                if (now.weekday() == GUARDIAN_DAY_UTC and
                        now.hour >= GUARDIAN_HOUR_UTC and
                        self.last_guardian_date != today_str):
                    self._run_guardian(trigger="weekly")
                    self.last_guardian_date = today_str

                # 3. Emergency 체크 (15분마다)
                if time.time() - self.last_emergency_check > EMERGENCY_CHECK_INTERVAL_MIN * 60:
                    self._run_emergency_check()
                    self.last_emergency_check = time.time()

                # DD 체크 (매분)
                self._check_drawdown()

            except Exception as e:
                self.consecutive_errors += 1
                logger.exception(f"Main loop error: {e}")
                telegram.error("main_loop", type(e).__name__, str(e)[:300])

                if self.consecutive_errors >= SAFETY.MAX_API_ERRORS_BEFORE_BACKOFF:
                    logger.warning(f"연속 에러 {self.consecutive_errors}회 — backoff")
                    time.sleep(SAFETY.BACKOFF_MINUTES * 60)
                    self.consecutive_errors = 0

            time.sleep(60)

    # ────────────────────────────────────────
    # DCA 실행
    # ────────────────────────────────────────

    def _run_dca(self):
        """일별 DCA 매수."""
        cycle_id = f"dca-{uuid.uuid4().hex[:8]}"
        logger.info(f"━━━ DCA 실행 (multiplier={self.current_multiplier}) ━━━")

        try:
            results = dca_engine.execute_daily_dca(
                multiplier=self.current_multiplier,
                paper_mode=self.paper_mode,
            )
        except Exception as e:
            logger.exception(f"DCA 실행 실패: {e}")
            telegram.error("dca", type(e).__name__, str(e)[:300])
            return

        # DB 저장
        for res in results:
            if not res.get("executed"):
                continue
            try:
                db.save_execution(
                    cycle_id=cycle_id,
                    paper_mode=self.paper_mode,
                    asset=res["asset"],
                    side="Buy",
                    value_usdt=res["value_usdt"],
                    qty=res.get("qty"),
                    price=res.get("price"),
                    order_id=res.get("order_id"),
                    error=res.get("reason"),
                )
                telegram.execution(
                    res["asset"], "Buy", res["value_usdt"],
                    res.get("qty", 0), res.get("price", 0),
                    self.paper_mode,
                )
            except Exception as e:
                logger.error(f"DCA DB 저장 실패: {e}")

        # 사후 스냅샷
        self._save_snapshot(cycle_id)

        executed_count = sum(1 for r in results if r.get("executed"))
        logger.info(f"DCA 완료 — {executed_count}/{len(results)} 자산 매수")

    # ────────────────────────────────────────
    # Guardian 실행
    # ────────────────────────────────────────

    def _run_guardian(self, trigger: str = "weekly"):
        """AI Guardian 점검."""
        cycle_id = f"guard-{uuid.uuid4().hex[:8]}"
        self.cycle_count += 1
        logger.info(f"━━━ Guardian #{self.cycle_count} ({trigger}) — id={cycle_id} ━━━")

        # 현재 상태
        try:
            portfolio = bybit_spot.get_portfolio_value_usdt()
        except Exception as e:
            logger.error(f"포트폴리오 조회 실패: {e}")
            return

        total = portfolio.get("total_usdt", 0)

        # AI 호출
        agent_result = run_decision(
            user_prompt=(
                f"Guardian cycle #{self.cycle_count} ({trigger}). "
                f"Current portfolio: ${total:.2f}. "
                f"Last DCA multiplier: {self.current_multiplier:.2f}. "
                f"Determine new multiplier and portfolio adjustments."
            ),
            trigger=trigger,
            on_tool_call=self._on_tool_call,
        )

        # DB 기록
        decision = agent_result.get("decision")
        try:
            db.save_decision(
                cycle_id=cycle_id,
                paper_mode=self.paper_mode,
                analyst=None,
                risk=None,
                manager=decision or {"raw_text": agent_result.get("raw_text", "")[:1000]},
                input_hash=cycle_id,
            )
        except Exception as e:
            logger.error(f"Guardian DB 저장 실패: {e}")

        if not agent_result["success"]:
            logger.warning(f"Guardian 실패: {agent_result.get('stop_reason')} / "
                         f"{agent_result.get('validation_errors')}")
            telegram.error(
                "guardian",
                agent_result.get("stop_reason", "unknown"),
                f"비용 ${agent_result['usage'].get('cost_usd',0):.4f} / "
                f"{agent_result.get('validation_errors')}",
            )
            return

        # decision 방어 (None / 필수키 누락 시 skip)
        if not decision or not isinstance(decision, dict):
            logger.warning(f"Guardian: decision 형식 비정상 (decision={decision})")
            return
        if "dca_decision" not in decision or not decision.get("dca_decision"):
            logger.warning(f"Guardian: dca_decision 누락 (keys={list(decision.keys())})")
            return

        # multiplier 업데이트
        new_multiplier = float(decision["dca_decision"]["multiplier"])
        old_multiplier = self.current_multiplier
        self.current_multiplier = new_multiplier
        logger.info(f"Multiplier {old_multiplier:.2f} → {new_multiplier:.2f}")

        # 포트폴리오 조정 (HOLD가 아니면)
        pf_decision = decision["portfolio_decision"]
        if pf_decision["action"] != "HOLD":
            target = pf_decision["target_weights"]
            current_weights = portfolio.get("weights", {})

            orders = portfolio_manager.compute_rebalance_orders(
                current_weights=current_weights,
                target_weights=target,
                total_value_usdt=total,
            )

            if orders:
                logger.info(f"포트폴리오 조정 ({pf_decision['action']}): {len(orders)} 주문")
                results = portfolio_manager.execute_orders(orders, paper_mode=self.paper_mode)
                for res in results:
                    db.save_execution(
                        cycle_id=cycle_id,
                        paper_mode=self.paper_mode,
                        asset=res["asset"],
                        side=res["side"],
                        value_usdt=res["value_usdt"],
                        qty=res.get("qty"),
                        price=res.get("price"),
                        order_id=res.get("order_id"),
                        error=res.get("error"),
                    )
                    if res.get("executed"):
                        telegram.execution(
                            res["asset"], res["side"], res["value_usdt"],
                            res.get("qty", 0), res.get("price", 0),
                            self.paper_mode,
                        )
        else:
            logger.info(f"포트폴리오 HOLD (조정 없음)")

        # Guardian 알림 (Telegram)
        self._notify_guardian_decision(decision, agent_result["usage"])

        # 사후 스냅샷
        self._save_snapshot(cycle_id)

        usage = agent_result["usage"]
        logger.info(
            f"━━━ Guardian #{self.cycle_count} 완료 — "
            f"iter {agent_result['iterations']}, tools {len(agent_result['tool_calls'])}, "
            f"cost ${usage.get('cost_usd',0):.4f} ━━━"
        )

    # ────────────────────────────────────────
    # Emergency 체크
    # ────────────────────────────────────────

    def _run_emergency_check(self):
        """가격 급락 또는 위기 뉴스 감지 시 Guardian 즉시 호출."""
        try:
            crisis = emergency_monitor.check_all()
        except Exception as e:
            logger.error(f"Emergency check 실패: {e}")
            return

        if crisis:
            logger.critical(f"⚠️ EMERGENCY 감지: {crisis}")
            telegram.crisis(
                "emergency_monitor",
                crisis.get("type", "unknown"),
                crisis.get("message", "")[:300],
            )

            # 마지막 Guardian 호출이 1시간 이내면 스킵 (중복 방지)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
            if hasattr(self, "_last_emergency_guardian") and self._last_emergency_guardian == today_str:
                logger.info("최근 1시간 내 Guardian 실행 — 중복 호출 스킵")
                return

            self._last_emergency_guardian = today_str
            self._run_guardian(trigger="emergency")

    # ────────────────────────────────────────
    # 헬퍼
    # ────────────────────────────────────────

    def _check_drawdown(self):
        try:
            portfolio = bybit_spot.get_portfolio_value_usdt()
            total = portfolio.get("total_usdt", 0)
            peak = db.get_peak_value()
            if peak > 0 and safety.check_drawdown_shutdown(total, peak):
                dd_pct = (peak - total) / peak
                logger.critical(f"DD 셧다운: {dd_pct*100:.1f}%")
                telegram.drawdown_shutdown(total, peak, dd_pct)
                self.running = False
        except Exception:
            pass

    def _save_snapshot(self, cycle_id: str):
        try:
            portfolio = bybit_spot.get_portfolio_value_usdt()
            db.save_snapshot(
                cycle_id=cycle_id,
                total_value=portfolio.get("total_usdt", 0),
                weights=portfolio.get("weights", {}),
                values=portfolio.get("values", {}),
            )
        except Exception as e:
            logger.error(f"스냅샷 저장 실패: {e}")

    def _on_tool_call(self, name: str, args: dict, result):
        result_brief = str(result)[:80] if result else "None"
        logger.info(f"  [tool] {name}({args}) → {result_brief}")

    def _notify_guardian_decision(self, decision: dict, usage: dict):
        """Guardian 결정 텔레그램 알림."""
        try:
            regime = decision.get("regime", "?")
            score = decision.get("cycle_position_score", "?")
            multiplier = decision["dca_decision"]["multiplier"]
            action = decision["portfolio_decision"]["action"]
            confidence = decision.get("confidence", 0)
            reasoning = decision["dca_decision"].get("reasoning", "")[:200]

            target_weights = decision["portfolio_decision"].get("target_weights", {})
            weights_str = " · ".join(
                f"{a} {w*100:.0f}%" for a, w in target_weights.items() if float(w) > 0.01
            )

            msg = (
                f"🏛️ ATHENA Guardian (신뢰 {confidence}/10)\n"
                f"────────────────────\n"
                f"Regime: {regime} (사이클 {score}/100)\n"
                f"DCA Multiplier: {multiplier:.2f}\n"
                f"Portfolio: {action}\n"
                f"비중: {weights_str}\n"
                f"\n"
                f"근거:\n  {reasoning}\n"
                f"\n"
                f"비용: ${usage.get('cost_usd',0):.4f}"
            )
            telegram._send(msg)
        except Exception as e:
            logger.error(f"Guardian 알림 실패: {e}")

    def _shutdown(self, *_):
        logger.info("종료 요청...")
        self.running = False
        telegram.system_stop("정상 종료")
        sys.exit(0)


if __name__ == "__main__":
    Athena().start()
