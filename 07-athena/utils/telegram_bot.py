"""ATHENA 텔레그램 알림.

정책 (HERMES/KAIROS와 동일):
- 보냄: 시스템 가동/종료, 거래 체결, AI 결정 요약(4H), DD 셧다운, 에러
- 안 보냄: 데이터 수집 로그, 정상 작동 heartbeat
"""

import requests
from typing import Optional, Dict, Any, List

from config import TELEGRAM, get_logger

logger = get_logger("telegram")

SEP = "─" * 28


class TelegramBot:
    def __init__(self):
        self.token = TELEGRAM.BOT_TOKEN
        self.chat_id = TELEGRAM.CHAT_ID
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        if not self.token or not self.chat_id:
            logger.warning("Telegram 미설정")

    def _send(self, text: str) -> bool:
        if not self.token:
            return False
        try:
            r = requests.post(self.url, json={"chat_id": self.chat_id, "text": text}, timeout=5)
            r.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"텔레그램 전송 실패: {e}")
            return False

    def system_start(self, paper_mode: bool, total_value_usdt: float):
        mode = "📋 PAPER" if paper_mode else "🟢 LIVE"
        # 실제 스케줄 동적 표시
        from config import SCHEDULER, AGENTIC
        return self._send(
            f"🏛️ ATHENA 가동 ({mode})\n{SEP}\n"
            f"잔고  ${total_value_usdt:,.2f}\n"
            f"AI    {AGENTIC.MODEL_ID}\n"
            f"DCA   매일 02:00 UTC (누적 매수)\n"
            f"Guardian  주 1회 (일요일 KST 09:00)\n"
            f"Emergency 15분마다 모니터링"
        )

    def system_stop(self, reason: str = ""):
        return self._send(f"🔴 ATHENA 종료\n{SEP}\n{reason}")

    def cycle_decision(self, manager_output: Dict[str, Any],
                       paper_mode: bool):
        """4H 결정 요약 알림."""
        weights = manager_output.get("target_weights", {})
        actions = manager_output.get("rebalance_actions", [])
        confidence = manager_output.get("confidence", 0)
        reasoning = manager_output.get("reasoning", "")

        weights_str = " · ".join(
            f"{a} {w*100:.0f}%" for a, w in weights.items() if w > 0.01
        )

        action_lines = []
        for a in actions[:5]:
            action_lines.append(
                f"  {a.get('action', '?')} {a.get('asset', '?')} {a.get('delta_pct', 0)*100:+.1f}%p"
            )

        mode = "📋" if paper_mode else "🟢"
        return self._send(
            f"{mode} ATHENA 결정 (신뢰 {confidence}/10)\n{SEP}\n"
            f"목표 비중\n  {weights_str}\n"
            f"\n조정\n" + "\n".join(action_lines) + "\n"
            f"\n근거\n  {reasoning[:200]}"
        )

    def execution(self, asset: str, side: str, value_usdt: float,
                  qty: float, price: float, paper_mode: bool):
        mode = "📋" if paper_mode else "🟢"
        return self._send(
            f"{mode} {side} {asset}\n{SEP}\n"
            f"금액  ${value_usdt:.2f}\n"
            f"수량  {qty:.6f}\n"
            f"가격  ${price:,.2f}"
        )

    def drawdown_shutdown(self, current: float, peak: float, dd_pct: float):
        return self._send(
            f"🚨 DD 셧다운\n{SEP}\n"
            f"피크  ${peak:,.2f}\n"
            f"현재  ${current:,.2f}\n"
            f"DD    -{dd_pct*100:.1f}%"
        )

    def error(self, location: str, error_type: str, message: str):
        return self._send(
            f"🚨 에러\n{SEP}\n"
            f"위치  {location}\n"
            f"유형  {error_type}\n"
            f"{message[:300]}"
        )

    def crisis(self, source: str, crisis_type: str, message: str):
        """위기 신호 감지 (시스템 에러 아님). emergency_trigger 등에 사용."""
        return self._send(
            f"⚠️ 위기 신호 감지\n{SEP}\n"
            f"트리거  {source}\n"
            f"유형    {crisis_type}\n"
            f"{message[:300]}"
        )


telegram = TelegramBot()
