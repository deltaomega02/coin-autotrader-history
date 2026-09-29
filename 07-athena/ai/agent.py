"""ATHENA Agent — Guardian 모드 단일 진입점.

run_decision() 호출 → Gemini Agentic Loop → 5단계 결정 JSON 검증.

새 결정 형식:
- dca_decision: { multiplier, reasoning }
- portfolio_decision: { action, target_weights, reasoning }
- regime: EXTREME_BOTTOM ~ EXTREME_TOP
- cycle_position_score: 0-100
"""

import json
import re
from typing import Dict, Any, Optional

from ai.gemini_client import gemini_client
from ai.prompts import ATHENA_SYSTEM_PROMPT
from ai.tools import ALL_TOOLS
from config import AGENTIC, get_logger

logger = get_logger("agent")

VALID_REGIMES = {"EXTREME_BOTTOM", "ACCUMULATION", "NEUTRAL", "OVERHEATED", "EXTREME_TOP"}
VALID_ACTIONS = {"HOLD", "DEFENSIVE", "AGGRESSIVE"}


def run_decision(user_prompt: str = "Weekly cycle. 시장 분석 후 DCA multiplier + 포트폴리오 결정.",
                 trigger: str = "scheduled",
                 on_tool_call=None) -> Dict[str, Any]:
    """ATHENA Guardian 1 사이클.

    Args:
        user_prompt: 사용자 입력
        trigger: "scheduled" | "emergency" | "manual"
        on_tool_call: 도구 콜백
    """
    if not gemini_client.is_ready:
        return _failure("client_not_ready")

    logger.info(f"━━━ ATHENA Guardian Cycle ({trigger}) ━━━")

    # 긴급 호출 시 추가 컨텍스트
    if trigger == "emergency":
        user_prompt = (
            "**EMERGENCY TRIGGER**. " + user_prompt +
            " 위기 상황 가능 — 신중히 분석 후 방어 모드 검토."
        )

    result = gemini_client.run_agentic_loop(
        system_prompt=ATHENA_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tools=ALL_TOOLS,
        on_tool_call=on_tool_call,
    )

    logger.info(
        f"Agentic 결과: success={result['success']} "
        f"iter={result['iterations']} tools={len(result['tool_calls'])} "
        f"cost=${result['usage'].get('cost_usd',0):.4f} "
        f"stop={result['stop_reason']}"
    )

    if not result["success"]:
        return {
            **result,
            "decision": None,
            "raw_text": result.get("final_text", ""),
            "validation_errors": [f"agentic_failed: {result.get('stop_reason')}"],
        }

    # JSON 추출
    decision = _parse_decision_json(result["final_text"])
    if not decision:
        return {
            **result,
            "decision": None,
            "raw_text": result["final_text"],
            "validation_errors": ["json_parse_failed"],
        }

    # 검증
    errors = _validate_guardian_decision(decision)
    if errors:
        logger.warning(f"검증 실패: {errors}")
        return {
            **result,
            "decision": decision,
            "raw_text": result["final_text"],
            "validation_errors": errors,
            "success": False,
        }

    return {
        **result,
        "decision": decision,
        "raw_text": result["final_text"],
        "validation_errors": [],
    }


def _parse_decision_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first:last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse 실패: {e}\n앞 500: {text[:500]}")
        return None


def _validate_guardian_decision(d: Dict[str, Any]) -> list:
    errors = []

    # 필수 필드
    required = ["regime", "dca_decision", "portfolio_decision", "confidence"]
    for f in required:
        if f not in d:
            errors.append(f"필수 필드 누락: {f}")
    if errors:
        return errors

    # regime
    if d["regime"] not in VALID_REGIMES:
        errors.append(f"regime 오류: {d['regime']} (허용: {VALID_REGIMES})")

    # dca_decision
    dca = d.get("dca_decision", {})
    if "multiplier" not in dca:
        errors.append("dca_decision.multiplier 누락")
    else:
        try:
            m = float(dca["multiplier"])
            if m < 0.0 or m > 2.0:
                errors.append(f"multiplier 범위 오류: {m} (0.0-2.0)")
        except (TypeError, ValueError):
            errors.append("multiplier 타입 오류")

    # portfolio_decision
    pf = d.get("portfolio_decision", {})
    if "action" not in pf:
        errors.append("portfolio_decision.action 누락")
    elif pf["action"] not in VALID_ACTIONS:
        errors.append(f"action 오류: {pf['action']} (허용: {VALID_ACTIONS})")

    # target_weights
    target = pf.get("target_weights", {})
    if not target:
        errors.append("target_weights 누락")
    else:
        allowed = {"BTC", "ETH", "SOL", "USDT"}
        for asset in target:
            if asset not in allowed:
                errors.append(f"허용 안 된 자산: {asset}")
        try:
            total = sum(float(v) for v in target.values())
            if abs(total - 1.0) > 0.01:
                errors.append(f"비중 합 오류: {total:.3f}")
        except (TypeError, ValueError):
            errors.append("비중 값 타입 오류")
        for a, w in target.items():
            try:
                wf = float(w)
                if wf > 0.80:
                    errors.append(f"{a} 비중 초과: {wf:.2f} > 0.80")
                if wf < 0:
                    errors.append(f"{a} 음수")
            except (TypeError, ValueError):
                pass
        try:
            usdt = float(target.get("USDT", 0))
            if usdt < 0.05:
                errors.append(f"USDT 최소 미달: {usdt:.3f}")
        except (TypeError, ValueError):
            pass

    # confidence
    try:
        c = int(d["confidence"])
        if c < AGENTIC.MIN_CONFIDENCE_TO_ACT:
            errors.append(f"신뢰도 부족: {c} < {AGENTIC.MIN_CONFIDENCE_TO_ACT}")
    except (TypeError, ValueError):
        errors.append("confidence 타입 오류")

    return errors


def _failure(error: str) -> Dict[str, Any]:
    return {
        "success": False,
        "decision": None,
        "raw_text": "",
        "iterations": 0,
        "tool_calls": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        "stop_reason": "error",
        "error": error,
        "validation_errors": [error],
    }
