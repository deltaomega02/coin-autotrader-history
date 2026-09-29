# AI 프롬프트 — 진입 필터

import json
import numpy as np
from typing import Dict, Any


class NumpyEncoder(json.JSONEncoder):
    """NumPy 타입을 JSON 직렬화 가능하게 변환"""
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """NumPy 타입 안전 JSON 직렬화"""
    return json.dumps(obj, cls=NumpyEncoder, ensure_ascii=False, **kwargs)


def create_entry_filter_prompt(
    market_data: Dict[str, Any],
    regime: str,
    direction: str,
    signal_reason: str,
    signal_score: int
) -> str:
    """AI 진입 필터 프롬프트 — PASS/REJECT 이진 판단"""
    return f"""You are a Risk Auditor reviewing a trade entry decision.
The trading system has already determined the market regime and generated an entry signal.
Your job is NOT to decide direction or strategy. Your job is to check for red flags the system might have missed.

## System Decision (Already Made)
- Detected Regime: {regime}
- Signal: {direction}
- Entry Reason: {signal_reason}
- Signal Score: {signal_score}/100

## Current Market Data (1H Timeframe)
{safe_json_dumps(market_data, indent=2)}

## Your Task
Review this entry decision and check for:
1. Is there an obvious structural contradiction the system missed?
   (e.g., system says BULLISH but price just broke major support)
2. Is there an extreme condition that makes entry dangerous RIGHT NOW?
   (e.g., massive wick rejection, divergence at key level, funding rate extreme)
3. Is the system's regime classification reasonable given the data?

## Decision Rules
- **PASS**: The entry is reasonable. No critical red flags detected.
  You don't need to agree it's the best trade ever. You just need to confirm
  there's no obvious reason NOT to enter. When in doubt, PASS.
- **REJECT**: There is a specific, articulable structural reason this entry is dangerous.
  "Momentum is weakening" is NOT enough to reject.
  "Price just broke below the support level the system is using as entry basis" IS enough.

## IMPORTANT
- Bias toward PASS. The system has already filtered extensively.
  Excessive rejection defeats the purpose of the system.
- REJECT only when you can point to a SPECIFIC structural problem.
- Do NOT reject based on "the market might go the other way" — that's always true.

## Output Language Rule
- Write 'review' and 'reason' in KOREAN.
- Keep JSON keys and PASS/REJECT in ENGLISH.

## Response Format (JSON only)
{{
    "decision": "PASS" or "REJECT",
    "review": "Brief structural assessment (2-3 sentences). What you checked and what you found. In KOREAN.",
    "reason": "One sentence: why PASS (no red flags) or why REJECT (specific structural problem). In KOREAN.",
    "risk_note": "Optional: any risk the system should be aware of even if PASS. In KOREAN. null if none."
}}

Respond with JSON only, no additional text."""
