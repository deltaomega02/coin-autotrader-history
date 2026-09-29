"""ATHENA Safety Layer.

AI 결정을 검증하는 마지막 게이트.
HERMES 학습 + METIS-F "AI 거부권" 패턴 통합.
"""

from typing import Dict, Any, Tuple, List

from config import SAFETY, ATHENA, get_logger

logger = get_logger("safety")


def validate_manager_decision(decision: Dict[str, Any],
                              current_portfolio: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Manager 결정 검증.

    Returns:
        (is_valid, [error_messages])
    """
    errors = []

    # 1. 필수 필드
    required = ["target_weights", "confidence", "rebalance_actions", "reasoning"]
    for f in required:
        if f not in decision:
            errors.append(f"필수 필드 누락: {f}")

    if errors:
        return False, errors

    target = decision["target_weights"]
    confidence = decision.get("confidence", 0)

    # 2. 신뢰도 컷오프
    if confidence < SAFETY.CONFIDENCE_CUTOFF:
        errors.append(f"신뢰도 부족: {confidence} < {SAFETY.CONFIDENCE_CUTOFF}")

    # 3. 자산 화이트리스트
    for asset in target:
        if asset not in ATHENA.ALLOWED_ASSETS:
            errors.append(f"허용 안 된 자산: {asset}")

    # 4. 비중 합 = 1.0 (±0.01 허용)
    total = sum(target.values())
    if abs(total - 1.0) > 0.01:
        errors.append(f"비중 합 오류: {total:.3f} (1.0이어야)")

    # 5. 단일 자산 한도
    for asset, w in target.items():
        if w > SAFETY.MAX_SINGLE_ASSET_WEIGHT:
            errors.append(f"{asset} 비중 초과: {w:.2f} > {SAFETY.MAX_SINGLE_ASSET_WEIGHT}")
        if w < 0:
            errors.append(f"{asset} 음수 비중: {w}")

    # 6. USDT 최소
    usdt_weight = target.get("USDT", 0)
    if usdt_weight < SAFETY.MIN_USDT_WEIGHT:
        errors.append(f"USDT 최소 비중 미달: {usdt_weight:.3f} < {SAFETY.MIN_USDT_WEIGHT}")

    # 7. 한 번에 너무 큰 변경 금지
    current_weights = current_portfolio.get("weights", {})
    total_change = sum(
        abs(target.get(a, 0) - current_weights.get(a, 0))
        for a in ATHENA.ALLOWED_ASSETS
    )
    if total_change > SAFETY.MAX_TOTAL_CHANGE_PER_CYCLE:
        errors.append(
            f"한 번 변경 한도 초과: {total_change:.2f} > {SAFETY.MAX_TOTAL_CHANGE_PER_CYCLE}"
        )

    return len(errors) == 0, errors


def check_drawdown_shutdown(current_value: float, peak_value: float) -> bool:
    """DD -15% 도달 시 셧다운 신호."""
    if peak_value <= 0:
        return False
    dd = (peak_value - current_value) / peak_value
    return dd >= SAFETY.MAX_DRAWDOWN_PCT


def check_consecutive_same_decision(recent_decisions: List[Dict[str, Any]]) -> bool:
    """같은 결정 N회 연속 = 경고 (무가치한 호출 가능성)."""
    if len(recent_decisions) < SAFETY.MAX_CONSECUTIVE_SAME_DECISION:
        return False
    last_n = recent_decisions[-SAFETY.MAX_CONSECUTIVE_SAME_DECISION:]
    actions_strs = [str(d.get("rebalance_actions", [])) for d in last_n]
    return len(set(actions_strs)) == 1
