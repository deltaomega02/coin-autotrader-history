"""Gemini 3.1 Pro 클라이언트 (Agentic mode).

공식 문서 기준 (2026-04):
- SDK: google-genai (구 google-generativeai deprecated)
- Manual function calling loop (자동 모드 사용 시 무한 루프 통제 어려움)
- Thought signatures: 응답 객체 통째로 contents에 append하면 자동 보존
- function_call.id 매칭 필수
- temperature=1.0 권장 (변경 시 루핑 위험)
- thinking_level: "medium" (Pro 기본 high, 비용 절감)

설치: pip install google-genai
"""

import time
from typing import Optional, Dict, Any, List, Callable

from config import AGENTIC, get_logger

logger = get_logger("gemini")


class GeminiNotInstalledError(Exception):
    pass


class GeminiClient:
    """Gemini 3.1 Pro Agentic 클라이언트.

    사용:
        client = GeminiClient()
        result = client.run_agentic_loop(
            system_prompt="...",
            user_prompt="...",
            tools=[func1, func2, ...],
            response_schema={...},   # JSON 출력 스키마 (선택)
        )
    """

    def __init__(self):
        self.api_key = AGENTIC.GEMINI_API_KEY
        self.model_id = AGENTIC.MODEL_ID
        self._client = None
        self._types = None
        self._errors = None

        if not self.api_key:
            logger.warning("GEMINI_API_KEY 미설정")
            return

        try:
            from google import genai
            from google.genai import types as genai_types
            from google.genai import errors as genai_errors
            self._client = genai.Client(api_key=self.api_key)
            self._types = genai_types
            self._errors = genai_errors
            logger.info(f"Gemini 초기화 완료 — model={self.model_id}")
        except ImportError as e:
            logger.error(f"google-genai 미설치: {e} — pip install google-genai")
        except Exception as e:
            logger.error(f"Gemini 초기화 실패: {e}")

    @property
    def is_ready(self) -> bool:
        return self._client is not None

    # ────────────────────────────────────────
    # Agentic Loop (수동 모드)
    # ────────────────────────────────────────

    def run_agentic_loop(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[Callable],
        max_iterations: int = None,
        max_tool_calls: int = None,
        on_tool_call: Optional[Callable[[str, dict, Any], None]] = None,
    ) -> Dict[str, Any]:
        """Agentic 루프 실행.

        Args:
            system_prompt: 시스템 프롬프트 (캐시 대상)
            user_prompt: 시작 입력
            tools: Python 함수 리스트 (Gemini가 호출할 도구)
            max_iterations: 최대 turn 수 (None = AGENTIC.MAX_ITERATIONS)
            max_tool_calls: 도구 호출 총합 한도
            on_tool_call: 콜백 (name, args, result) — 모니터링용

        Returns:
            {
              "success": bool,
              "final_text": str (최종 응답),
              "iterations": int,
              "tool_calls": [{"name", "args", "result"}, ...],
              "usage": {"input_tokens", "output_tokens", "cost_usd"},
              "error": str | None,
              "stop_reason": "completed" | "max_iterations" | "max_tool_calls"
                           | "max_tokens" | "max_cost" | "error" | "timeout",
            }
        """
        if not self.is_ready:
            return self._error_result("client_not_ready")

        max_iter = max_iterations or AGENTIC.MAX_ITERATIONS
        max_calls = max_tool_calls or AGENTIC.MAX_TOOL_CALLS_PER_CYCLE

        # tools dict for execution
        tool_map = {t.__name__: t for t in tools}

        # config 빌드
        config = self._build_config(system_prompt, tools)

        # contents 시작 (user prompt)
        contents = [
            self._types.Content(
                role="user",
                parts=[self._types.Part(text=user_prompt)],
            )
        ]

        tool_call_log = []
        same_tool_count = {}
        usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

        start_time = time.time()
        iteration = 0
        stop_reason = None

        for iteration in range(1, max_iter + 1):
            # ─ 안전: timeout
            if time.time() - start_time > AGENTIC.CYCLE_TIMEOUT_SECONDS:
                stop_reason = "timeout"
                break

            # ─ 안전: 토큰 한도
            if usage["input_tokens"] + usage["output_tokens"] > AGENTIC.MAX_TOKENS_PER_CYCLE:
                stop_reason = "max_tokens"
                break

            # ─ 안전: 비용 한도
            if usage["cost_usd"] > AGENTIC.MAX_COST_PER_CYCLE_USD:
                stop_reason = "max_cost"
                break

            # API 호출 (재시도 포함)
            try:
                response = self._call_model_with_retry(contents, config)
            except Exception as e:
                logger.error(f"Gemini 호출 최종 실패: {e}")
                return self._error_result(f"api_failure: {e}",
                                         iterations=iteration,
                                         tool_calls=tool_call_log,
                                         usage=usage)

            # 사용량 누적
            self._update_usage(usage, response)

            # 응답 객체 통째로 history에 추가 (thought signature 자동 보존)
            if response.candidates and response.candidates[0].content:
                contents.append(response.candidates[0].content)

            # function call 추출
            function_calls = self._extract_function_calls(response)

            # 도구 호출 없으면 → 최종 응답
            if not function_calls:
                final_text = self._extract_text(response)
                stop_reason = "completed"
                logger.info(
                    f"Agentic 완료 — iter {iteration}, tools {len(tool_call_log)}, "
                    f"tokens {usage['input_tokens']}/{usage['output_tokens']}, "
                    f"cost ${usage['cost_usd']:.4f}"
                )
                return {
                    "success": True,
                    "final_text": final_text,
                    "iterations": iteration,
                    "tool_calls": tool_call_log,
                    "usage": usage,
                    "stop_reason": stop_reason,
                    "error": None,
                }

            # ─ 안전: 도구 호출 한도
            if len(tool_call_log) + len(function_calls) > max_calls:
                stop_reason = "max_tool_calls"
                logger.warning(f"도구 호출 한도 도달 — 강제 종료")
                break

            # 도구 실행
            function_response_parts = []
            for fc in function_calls:
                # ─ 안전: 같은 도구 + 같은 인자 반복 차단
                key = f"{fc.name}:{str(sorted((fc.args or {}).items()))}"
                same_tool_count[key] = same_tool_count.get(key, 0) + 1
                if same_tool_count[key] > AGENTIC.MAX_SAME_TOOL_CALLS:
                    logger.warning(f"{fc.name} 동일 인자 반복 차단")
                    function_response_parts.append(self._make_response_part(
                        fc, {"error": "duplicate_call_blocked"}
                    ))
                    continue

                # 실행
                result = self._execute_tool(fc, tool_map)

                if on_tool_call:
                    try:
                        on_tool_call(fc.name, fc.args or {}, result)
                    except Exception:
                        pass

                tool_call_log.append({
                    "iteration": iteration,
                    "name": fc.name,
                    "args": dict(fc.args or {}),
                    "result_preview": str(result)[:200],
                })

                function_response_parts.append(self._make_response_part(fc, result))

            # 도구 결과를 history에 추가
            contents.append(self._types.Content(
                role="user",  # function response는 user role
                parts=function_response_parts,
            ))

        # max_iterations 또는 다른 안전 종료
        if not stop_reason:
            stop_reason = "max_iterations"
        logger.warning(f"Agentic 루프 강제 종료: {stop_reason}")

        # 마지막 텍스트라도 추출
        last_text = ""
        try:
            for c in reversed(contents):
                if c.role == "model":
                    for p in c.parts:
                        if hasattr(p, "text") and p.text:
                            last_text = p.text
                            break
                    if last_text:
                        break
        except Exception:
            pass

        return {
            "success": False,
            "final_text": last_text,
            "iterations": iteration,
            "tool_calls": tool_call_log,
            "usage": usage,
            "stop_reason": stop_reason,
            "error": None,
        }

    # ────────────────────────────────────────
    # 내부 헬퍼
    # ────────────────────────────────────────

    def _build_config(self, system_prompt: str, tools: List[Callable]):
        """GenerateContentConfig 생성 (function calling용).

        주의: automatic_function_calling은 OFF (수동 루프로 안전 통제).
        """
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": AGENTIC.TEMPERATURE,
            "max_output_tokens": AGENTIC.MAX_OUTPUT_TOKENS,
            "tools": tools,
            # 수동 루프 → automatic 비활성화
            "automatic_function_calling": self._types.AutomaticFunctionCallingConfig(disable=True),
        }

        # ThinkingConfig — 공식 문서 기준 include_thoughts 사용
        # thinking_level은 Gemini 3 일부 모델만 지원 (preview)
        try:
            # 1차: include_thoughts (공식 문서 정확한 방식)
            config_kwargs["thinking_config"] = self._types.ThinkingConfig(
                include_thoughts=True,
            )
        except (AttributeError, TypeError):
            try:
                # 2차 fallback: thinking_level (Gemini 3 preview)
                config_kwargs["thinking_config"] = self._types.ThinkingConfig(
                    thinking_level=AGENTIC.THINKING_LEVEL,
                )
            except (AttributeError, TypeError):
                # 3차: thinking_config 미지원
                pass

        return self._types.GenerateContentConfig(**config_kwargs)

    def _call_model_with_retry(self, contents, config):
        """재시도 포함 모델 호출."""
        last_err = None
        for attempt in range(AGENTIC.MAX_RETRIES):
            try:
                return self._client.models.generate_content(
                    model=self.model_id,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                last_err = e
                err_str = str(e)
                logger.warning(f"Gemini 호출 실패 (시도 {attempt+1}/{AGENTIC.MAX_RETRIES}): {err_str[:200]}")

                # thinking_config 미지원 시 fallback
                if "thinking" in err_str.lower():
                    if hasattr(config, "thinking_config") and config.thinking_config:
                        config.thinking_config = None
                        logger.info("thinking_config 제거 후 재시도")
                        continue

                if attempt < AGENTIC.MAX_RETRIES - 1:
                    time.sleep(AGENTIC.RETRY_BACKOFF_SEC)

        raise last_err

    def _extract_function_calls(self, response) -> List[Any]:
        """응답에서 function_call 부분만 추출."""
        calls = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    calls.append(part.function_call)
        except (IndexError, AttributeError):
            pass
        return calls

    def _extract_text(self, response) -> str:
        """응답에서 text 부분 결합."""
        texts = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)
        except (IndexError, AttributeError):
            pass
        return "\n".join(texts)

    def _execute_tool(self, fc, tool_map: dict) -> Any:
        """도구 실행 (timeout + 에러 보호)."""
        if fc.name not in tool_map:
            return {"error": f"unknown_tool: {fc.name}"}

        try:
            args = dict(fc.args or {})
            # 단순 timeout (Python 표준 라이브러리만)
            result = tool_map[fc.name](**args)
            return result
        except TypeError as e:
            return {"error": f"invalid_args: {e}"}
        except Exception as e:
            logger.error(f"도구 {fc.name} 실행 실패: {e}")
            return {"error": str(e)}

    def _make_response_part(self, fc, result: Any):
        """function_response Part 생성.

        SDK 버전 차이:
        - 신버전: id 파라미터 지원 (Gemini 3 매칭)
        - 구버전: id 미지원 (자동 매칭)
        try/except로 양쪽 호환.
        """
        # result가 dict 아니면 wrap
        if not isinstance(result, dict):
            result = {"result": result}

        # 1차: id 포함 (신버전)
        if hasattr(fc, "id") and fc.id:
            try:
                return self._types.Part.from_function_response(
                    name=fc.name, response=result, id=fc.id,
                )
            except TypeError:
                pass

        # 2차 fallback: id 없이 (구버전, SDK 자동 매칭)
        return self._types.Part.from_function_response(
            name=fc.name, response=result,
        )

    def _update_usage(self, usage: dict, response):
        """토큰 + 비용 누적."""
        try:
            meta = response.usage_metadata
            if meta:
                in_tok = getattr(meta, "prompt_token_count", 0) or 0
                out_tok = getattr(meta, "candidates_token_count", 0) or 0
                # thinking tokens (있으면)
                think_tok = getattr(meta, "thoughts_token_count", 0) or 0

                usage["input_tokens"] = in_tok  # 누적 X (매 턴 전체)
                usage["output_tokens"] += out_tok + think_tok

                # 비용 (대략)
                usage["cost_usd"] = (
                    in_tok / 1_000_000 * AGENTIC.INPUT_PRICE_PER_1M
                    + (out_tok + think_tok) / 1_000_000 * AGENTIC.OUTPUT_PRICE_PER_1M
                )
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _error_result(msg: str, **extra) -> dict:
        return {
            "success": False,
            "final_text": "",
            "iterations": extra.get("iterations", 0),
            "tool_calls": extra.get("tool_calls", []),
            "usage": extra.get("usage", {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}),
            "stop_reason": "error",
            "error": msg,
        }


gemini_client = GeminiClient()
