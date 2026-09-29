# Gemini API 클라이언트 — AI 진입 필터

import gc
import json
import time
from typing import Dict, Any, Optional

from google import genai
from google.genai import types

from config import GEMINI, get_logger
from ai.prompts import create_entry_filter_prompt

logger = get_logger("gemini_client")


class GeminiClient:
    """Gemini API — 진입 필터 (PASS/REJECT)"""

    MAX_RETRIES = 3
    RETRY_DELAY = 5  # 초

    def __init__(self):
        self.client = genai.Client(api_key=GEMINI.API_KEY)
        self.model_id = GEMINI.MODEL_ID

        self.common_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 65536,
            "response_mime_type": "application/json",

            "thinking_config": {
                "include_thoughts": True,
                "thinking_level": "HIGH"
            },

            "safety_settings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        logger.info(f"Gemini 클라이언트 초기화: {self.model_id}, Thinking: HIGH")

    def _call_with_retry(self, prompt: str) -> Optional[Dict[str, Any]]:
        """재시도 포함 API 호출 → JSON dict 또는 None"""
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Gemini API 호출 시도 {attempt + 1}/{self.MAX_RETRIES}")

                # Content 구조
                contents = []
                parts = [types.Part.from_text(text=prompt)]
                contents.append(types.Content(role="user", parts=parts))

                # API 호출
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=contents,
                    config=self.common_config
                )

                if not response or not response.text:
                    logger.warning(f"빈 응답 수신 - 시도 {attempt + 1}")
                    time.sleep(2 ** attempt)
                    continue

                logger.debug("=" * 60)
                logger.debug("Gemini Raw Response:")
                logger.debug(response.text[:500] + "..." if len(response.text) > 500 else response.text)
                logger.debug("=" * 60)

                # 파싱
                parsed_result = self._parse_json_response(response.text)

                del contents
                del response
                gc.collect()

                if parsed_result:
                    return parsed_result
                else:
                    logger.warning(f"JSON 파싱 실패 - 시도 {attempt + 1}")
                    time.sleep(2 ** attempt)
                    continue

            except Exception as e:
                logger.error(f"Gemini API 오류 - 시도 {attempt + 1}: {e}")

                if 'contents' in locals():
                    del contents
                if 'response' in locals():
                    del response
                gc.collect()

                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None

        return None

    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """응답에서 JSON 추출 (Thinking Process 분리)"""
        try:
            cleaned_text = response_text.strip()

            # ```json 블록
            if "```json" in cleaned_text:
                parts = cleaned_text.split("```json")

                # Thought process 로깅
                if len(parts) > 1:
                    thought_process = parts[0].strip()
                    if thought_process:
                        logger.info("[AI Thought Process]")
                        logger.info(thought_process[:300] + "..." if len(thought_process) > 300 else thought_process)

                json_part = parts[-1].split("```")[0].strip()
                return json.loads(json_part)

            # ``` 블록
            elif "```" in cleaned_text:
                parts = cleaned_text.split("```")

                if len(parts) > 1:
                    thought_process = parts[0].strip()
                    if thought_process:
                        logger.info("[AI Thought Process]")
                        logger.info(thought_process[:300] + "..." if len(thought_process) > 300 else thought_process)

                # 역순 탐색
                for part in reversed(parts):
                    part = part.strip()
                    if part.startswith("{") and part.endswith("}"):
                        return json.loads(part)

            # 순수 JSON
            if cleaned_text.startswith("{") and cleaned_text.endswith("}"):
                return json.loads(cleaned_text)

            # 텍스트 중간 JSON
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}')

            if start_idx != -1 and end_idx != -1:
                if start_idx > 0:
                    thought = cleaned_text[:start_idx].strip()
                    if thought:
                        logger.info("[AI Thought Process - Mixed]")
                        logger.info(thought[:300] + "..." if len(thought) > 300 else thought)

                json_str = cleaned_text[start_idx:end_idx + 1]
                return json.loads(json_str)

            logger.warning("응답에서 유효한 JSON을 찾을 수 없음")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"JSON 디코드 오류: {e}")
            return None
        except Exception as e:
            logger.error(f"응답 파싱 오류: {e}")
            return None

    def filter_entry(
        self,
        market_data: Dict[str, Any],
        regime: str,
        direction: str,
        signal_reason: str,
        signal_score: int
    ) -> Dict[str, Any]:
        """AI 진입 필터 — PASS 또는 REJECT"""
        logger.info(f"AI 진입 필터: {regime} {direction} (점수={signal_score})")

        prompt = create_entry_filter_prompt(
            market_data, regime, direction, signal_reason, signal_score
        )
        result = self._call_with_retry(prompt)

        if not result:
            logger.warning("AI 필터 응답 실패 → 안전상 REJECT")
            return {
                "decision": "REJECT",
                "reason": "AI 응답 실패",
                "review": "AI 응답 실패로 안전상 거부",
                "risk_note": None
            }

        decision = result.get("decision", "REJECT")
        if decision not in ["PASS", "REJECT"]:
            logger.warning(f"AI 필터 비정상 응답: {decision} → REJECT")
            result["decision"] = "REJECT"

        logger.info(f"AI 필터 결과: {result.get('decision')} - {result.get('reason', '')}")
        return result


# 싱글톤 인스턴스
gemini_client = GeminiClient()
