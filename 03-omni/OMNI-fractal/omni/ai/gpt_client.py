# ai/gpt_client.py
# OpenAI GPT-5 API를 활용한 트레이딩 AI 클라이언트 - 메모리 관리 최적화 및 다단계 분석을 수행하는 파일

import openai
import json
import gc 
from typing import Dict, Any, Optional, List, Tuple
from config.settings import settings
import os
import time
import re
from datetime import datetime, timedelta

_gpt_client_instance = None
_instance_call_count = 0  

# "GPTClient 싱글톤 인스턴스를 반환하는 메서드" (인자: 없음)
def get_gpt_client():
    global _gpt_client_instance
    if _gpt_client_instance is None:
        _gpt_client_instance = GPTClient()
    return _gpt_client_instance

# "GPT 클라이언트를 완전히 재생성하는 메서드" (인자: 없음)
def reset_gpt_client():
    """GPT 클라이언트 완전 재생성"""
    global _gpt_client_instance
    if _gpt_client_instance:
        _gpt_client_instance.cleanup()
    _gpt_client_instance = None
    gc.collect()
    print("🔄 GPT 클라이언트 인스턴스 재생성")
    return get_gpt_client()

class GPTClient:
    # "GPT 클라이언트 초기화 메서드" (인자: self)
    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.model = "gpt-5"
        
        self.response_cache = {}
        self.cache_timestamps = {}
        self.cache_contexts = {}
        
        self.current_session_id = None
        
        self.cache_ttl_minutes = 30
        self.enable_cross_phase_cache = True
        
    # "메모리를 명시적으로 정리하는 메서드" (인자: self)
    def cleanup(self):
        self.response_cache.clear()
        self.cache_timestamps.clear()
        self.cache_contexts.clear()
        self.current_session_id = None
        self.api_call_count = 0
        gc.collect()
        
    # "새로운 거래 세션을 시작하고 인스턴스를 재생성하는 메서드" (인자: self)
    def _start_new_session(self) -> str:
        from ai.gpt_client import reset_gpt_client
        new_instance = reset_gpt_client()
        
        self.__dict__ = new_instance.__dict__
        
        session_id = f"SESSION_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_session_id = session_id
        
        print(f"🔄 새 거래 세션 시작 (인스턴스 재생성): {session_id}")
        return session_id
    
    # "만료된 캐시를 삭제하여 메모리 누수를 방지하는 메서드" (인자: self)
    def _clear_old_cache(self):
        current_time = datetime.now()
        phases_to_delete = []
        
        for phase in list(self.cache_timestamps.keys()):
            cache_time = self.cache_timestamps[phase]
            if isinstance(cache_time, datetime):
                age_minutes = (current_time - cache_time).total_seconds() / 60
                if age_minutes > self.cache_ttl_minutes:
                    phases_to_delete.append(phase)
                    print(f"🗑️ 오래된 캐시 삭제: {phase} ({age_minutes:.1f}분 경과)")
        
        for phase in phases_to_delete:
            self.response_cache.pop(phase, None)
            self.cache_timestamps.pop(phase, None)
            self.cache_contexts.pop(phase, None)
    
    # "현재 Phase에 최적화된 이전 response ID를 선택하는 메서드" (인자: self, current_phase)
    def _get_best_previous_response(self, current_phase: str) -> Tuple[Optional[str], str]:
        reuse_strategy = {
            'phase1': None, 
            'phase2': ['phase1'], 
            'phase3': ['phase2', 'phase1'],
            'phase5': ['phase3', 'phase2'],
        }
        
        preferred_phases = reuse_strategy.get(current_phase, [])
        if not preferred_phases:
            return None, ""
        
        for phase in preferred_phases:
            response_id = self.response_cache.get(phase)
            if response_id and phase in self.cache_timestamps:
                cache_time = self.cache_timestamps[phase]
                age_minutes = (datetime.now() - cache_time).total_seconds() / 60
                
                if age_minutes <= self.cache_ttl_minutes:
                    return response_id, phase
        
        return None, ""
    
    # "Phase별 response 캐시를 저장하는 메서드" (인자: self, phase, response_id, context_summary)
    def _save_response_cache(self, phase: str, response_id: str, context_summary: str = ""):
        self.response_cache[phase] = response_id
        self.cache_timestamps[phase] = datetime.now()
        if context_summary:
            self.cache_contexts[phase] = context_summary[:100]
        print(f"💾 {phase.upper()} response 캐시 저장: {response_id[:8]}...")
        
    # "GPT 응답의 모든 신뢰도 점수를 0-100으로 정규화하는 메서드" (인자: self, gpt_response)
    def _normalize_confidence_scores(self, gpt_response):
        """GPT 응답의 모든 신뢰도 점수를 0-100 스케일로 정규화"""
        
        def normalize_score(score):
            if isinstance(score, (int, float)):
                # 0-1 스케일을 0-100으로 변환
                if 0 <= score <= 1:
                    return int(score * 100)
                # 1-10 스케일을 0-100으로 변환 (소수점 있는 경우)
                elif 0 < score <= 10 and score != int(score):
                    return int(score * 10)
                # 이미 0-100 스케일이면 정수로 변환
                elif 0 <= score <= 100:
                    return int(score)
                # 100 초과시 100으로 제한
                elif score > 100:
                    return 100
                # 음수는 0으로
                else:
                    return max(0, int(score))
            return score
            
        def process_nested_dict(obj, score_keys):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    # 점수 관련 키인 경우
                    if any(keyword in key.lower() for keyword in ['score', 'confidence', 'level', 'strength', 'probability']):
                        obj[key] = normalize_score(value)
                    # 특정 키 리스트에 있는 경우
                    elif key in score_keys:
                        obj[key] = normalize_score(value)
                    # 재귀적으로 처리
                    elif isinstance(value, dict):
                        process_nested_dict(value, score_keys)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                process_nested_dict(item, score_keys)
        
        # 정규화할 신뢰도 관련 키들
        score_keys = {
            'confidence_score', 'confidence_level', 'trust_level',
            'success_probability', 'independence_score', 'overall_score',
            'persona_weighted_score', 'btc_decoupling_score', 'technical_score',
            'persona_appeal', 'conservative', 'technical', 'risk_management',
            'value', 'momentum', 'individual_analysis_accuracy', 
            'independence_execution', 'altcoin_risk_control',
            'momentum_score', 'risk_reward_score', 'timing_score', 'total_score',
            'altcoin_strength', 'accuracy_score', 'execution_score', 'risk_control_score'
        }
        
        try:
            process_nested_dict(gpt_response, score_keys)
            return gpt_response
            
        except Exception as e:
            print(f"⚠️ 신뢰도 정규화 실패: {e}")
            return gpt_response

    # "깨진 JSON 문자열을 복구 시도하는 메서드" (인자: self, json_str)
    def _fix_json_string(self, json_str):
        try:
            json_str = json_str.replace('\n', '\\n').replace('\r', '\\r')

            json_str = json_str.replace('\t', '\\t')
            
            json_str = re.sub(r'(?<!\\)"(?=[^"]*"[^"]*:)', r'\"', json_str)

            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)

            open_braces = json_str.count('{') - json_str.count('}')
            open_brackets = json_str.count('[') - json_str.count(']')

            json_str += '}' * open_braces
            json_str += ']' * open_brackets
            
            return json_str
        except Exception as e:
            print(f"   JSON 복구 실패: {e}")
            return json_str

    # "응답에서 핵심 컨텍스트를 추출하는 메서드" (인자: self, result, phase)
    def _extract_context_summary(self, result: Dict[str, Any], phase: str) -> str:
        try:
            if phase == 'phase1':
                top3 = result.get('final_decision', {}).get('top_3_tickers', [])
                action = result.get('action', '')
                return f"TOP3: {', '.join(top3[:3])}, Action: {action}"[:100]
            
            elif phase == 'phase2':
                selected = result.get('final_selection', {}).get('selected_coin', '')
                confidence = result.get('final_selection', {}).get('confidence_score', 0)
                return f"Selected: {selected}, Confidence: {confidence}%"[:100]
            
            elif phase == 'phase3':
                params = result.get('trading_parameters', {})
                ticker = params.get('coin_ticker', '')
                entry = params.get('entry_price', 0)
                return f"Strategy: {ticker}, Entry: {entry}"[:100]
            
            elif phase == 'phase5':
                lesson = result.get('lessons_learned', {}).get('primary_lesson', '')
                return f"Lesson: {lesson[:50]}..."[:100]
            
            return ""
            
        except Exception as e:
            print(f"⚠️ 컨텍스트 추출 실패: {e}")
            return ""
    
    # "GPT-5 Responses API를 호출하는 핵심 메서드" (인자: self, prompt, response_format, reasoning_effort, text_verbosity, phase, force_new, retry_count)
    def _call_gpt5(self,
                    prompt: str,
                    response_format: Dict,
                    reasoning_effort: str = "high",
                    text_verbosity: str = "high",
                    phase: str = None,
                    force_new: bool = False,
                    retry_count: int = 0) -> Dict[str, Any]:
        
        MAX_RETRIES = 3
        self.last_response_was_recovered = False
        
        try:
            # 토큰 제한 설정 (재시도마다 증가)
            token_limits = [70000, 75000, 80000, 85000]
            
            params = {
                "model": self.model,
                "input": prompt,
                "reasoning": {
                    "effort": reasoning_effort
                },
                "text": {
                    "verbosity": text_verbosity,
                    "format": response_format
                },
                "max_output_tokens": token_limits[min(retry_count, 3)],
                "timeout": 600 
            }

            if retry_count == 0 and not force_new and phase and self.enable_cross_phase_cache:
                previous_id, source_phase = self._get_best_previous_response(phase)
                if previous_id:
                    params["previous_response_id"] = previous_id
                    context_hint = self.cache_contexts.get(source_phase, "")
                    print(f"♻️ {source_phase.upper()}의 추론 재사용 → {phase.upper()}")
                    if context_hint:
                        print(f"   📝 컨텍스트: {context_hint[:50]}...")

            retry_msg = f" (재시도 {retry_count}/{MAX_RETRIES})" if retry_count > 0 else ""
            print(f"🤖 [최신 API] GPT-5 호출{retry_msg} (추론: {reasoning_effort}, 상세도: {text_verbosity})")
            
            if retry_count > 0:
                print(f"   📈 토큰 제한: {params['max_output_tokens']:,}")
            
            start_time = time.time()

            try:
                response = openai.responses.create(**params)
            except Exception as timeout_error:
                if "timeout" in str(timeout_error).lower():
                    print(f"⏰ GPT-5 타임아웃 (5분 초과)")
                    return {"error": "GPT-5 응답 시간 초과 (5분)"}
                raise timeout_error
                
            elapsed = time.time() - start_time
            print(f"✅ GPT-5 응답 완료 ({elapsed:.1f}초)")

            raw_output = None

            if not hasattr(self, '_response_structure_logged'):
                print(f"📝 Response 타입: {type(response)}")
                print(f"📝 Response 속성들: {[attr for attr in dir(response) if not attr.startswith('_')][:10]}...")
                self._response_structure_logged = True

            if hasattr(response, 'output_text'):
                output_text_value = response.output_text
                
                if isinstance(output_text_value, str):
                    raw_output = output_text_value
                    print("✅ output_text에서 결과 추출 (문자열)")
                elif output_text_value:
                    for attr in ['text', 'content', 'value', 'data']:
                        if hasattr(output_text_value, attr):
                            raw_output = getattr(output_text_value, attr)
                            print(f"✅ output_text.{attr}에서 결과 추출")
                            break
                    
                    if not raw_output:
                        try:
                            raw_output = str(output_text_value)
                            if raw_output and len(raw_output) > 100 and raw_output.startswith('{'):
                                print("✅ output_text 문자열 변환 성공")
                            else:
                                raw_output = None
                        except:
                            raw_output = None

            if not raw_output:
                for attr_name in ['content', 'text', 'output']:
                    if hasattr(response, attr_name):
                        attr_value = getattr(response, attr_name)
                        if isinstance(attr_value, str):
                            raw_output = attr_value
                            print(f"✅ {attr_name}에서 결과 추출")
                            break
                        elif attr_value:
                            for sub_attr in ['text', 'content', 'value']:
                                if hasattr(attr_value, sub_attr):
                                    raw_output = getattr(attr_value, sub_attr)
                                    print(f"✅ {attr_name}.{sub_attr}에서 결과 추출")
                                    break
                            if raw_output:
                                break

            if not raw_output and hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                    raw_output = choice.message.content
                    print("✅ choices[0].message.content에서 결과 추출")
                elif hasattr(choice, 'text'):
                    raw_output = choice.text
                    print("✅ choices[0].text에서 결과 추출")

            if not raw_output:
                if hasattr(response, 'to_dict'):
                    try:
                        response_dict = response.to_dict()
                        for key in ['output_text', 'content', 'text', 'output']:
                            if key in response_dict:
                                value = response_dict[key]
                                if isinstance(value, str):
                                    raw_output = value
                                    print(f"✅ to_dict()['{key}']에서 결과 추출")
                                    break
                    except:
                        pass
                
                if not raw_output and hasattr(response, 'model_dump'):
                    try:
                        response_dump = response.model_dump()
                        if 'output_text' in response_dump:
                            raw_output = response_dump['output_text']
                            if isinstance(raw_output, dict) and 'text' in raw_output:
                                raw_output = raw_output['text']
                            print("✅ model_dump()에서 결과 추출")
                    except:
                        pass

            if not raw_output:
                try:
                    raw_output = str(response)
                    if raw_output and len(raw_output) > 100 and ('{' in raw_output):
                        print("⚠️ 직접 문자열 변환으로 결과 추출")
                    else:
                        raw_output = None
                except:
                    pass

            if not raw_output:
                print(f"❌ 응답에서 텍스트를 찾을 수 없음")
                if retry_count < MAX_RETRIES:
                    print(f"🔄 GPT-5 재호출 시도...")
                    time.sleep(2 * (retry_count + 1)) 
                    return self._call_gpt5(
                        prompt=prompt,
                        response_format=response_format,
                        reasoning_effort=reasoning_effort,
                        text_verbosity=text_verbosity,
                        phase=phase,
                        force_new=force_new,
                        retry_count=retry_count + 1
                    )
                return {"error": "GPT-5 응답에서 결과를 찾을 수 없습니다"}

            if raw_output and not isinstance(raw_output, (str, bytes, bytearray)):
                try:
                    raw_output = str(raw_output)
                    print("✅ 최종 문자열 변환 성공")
                except Exception as e:
                    print(f"❌ 최종 문자열 변환 실패: {e}")
                    if retry_count < MAX_RETRIES:
                        print(f"🔄 문자열 변환 실패 - 재호출...")
                        return self._call_gpt5(
                            prompt=prompt,
                            response_format=response_format,
                            reasoning_effort=reasoning_effort,
                            text_verbosity=text_verbosity,
                            phase=phase,
                            force_new=force_new,
                            retry_count=retry_count + 1
                        )
                    return {"error": f"응답 텍스트 변환 실패: {type(raw_output)}"}

            if not raw_output:
                return {"error": "추출된 텍스트가 비어있음"}
            
            print(f"📝 추출된 텍스트 길이: {len(raw_output)}자")
            result = None

            try:
                result = json.loads(raw_output)
                print(f"✅ JSON 파싱 성공")
                
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 파싱 실패: {e}")

                error_position = e.pos if hasattr(e, 'pos') else len(raw_output)
                print(f"   오류 위치: {error_position}/{len(raw_output)}")

                if error_position >= len(raw_output) - 100:
                    print(f"   📊 JSON이 잘린 것으로 추정")
                    
                    if retry_count < MAX_RETRIES:
                        print(f"🔄 더 큰 토큰 제한으로 GPT-5 재호출...")
                        time.sleep(3 * (retry_count + 1))
                        return self._call_gpt5(
                            prompt=prompt,
                            response_format=response_format,
                            reasoning_effort=reasoning_effort,
                            text_verbosity=text_verbosity,
                            phase=phase,
                            force_new=True,
                            retry_count=retry_count + 1
                        )
                    else:
                        print("😭 재시도 한계 도달 - JSON 파싱 포기")
                        return self._get_default_error_response(phase)
                else:
                    print(f"   📊 JSON 구조 오류")
                    
                    if retry_count < MAX_RETRIES:
                        print(f"🔄 GPT-5 재호출 시도...")
                        time.sleep(2 * (retry_count + 1))
                        return self._call_gpt5(
                            prompt=prompt,
                            response_format=response_format,
                            reasoning_effort=reasoning_effort,
                            text_verbosity=text_verbosity,
                            phase=phase,
                            force_new=force_new,
                            retry_count=retry_count + 1
                        )
                    else:
                        print("😭 재시도 한계 도달 - JSON 파싱 포기")
                        return self._get_default_error_response(phase)

            if hasattr(response, 'id') and phase and result and not result.get('error'):
                context_summary = self._extract_context_summary(result, phase)
                self._save_response_cache(phase, response.id, context_summary)

            if result and isinstance(result, dict) and not result.get('error'):
                if phase == "phase1" and 'final_decision' in result:
                    decision = result['final_decision']
                    print(f"   Action: {result.get('action', 'N/A')}")
                    print(f"   TOP 3: {decision.get('top_3_tickers', [])}")
                    print(f"   신뢰도: {decision.get('confidence_level', 0)}%")
                    
                elif phase == "phase2" and 'final_selection' in result:
                    selection = result['final_selection']
                    print(f"   Action: {result.get('action', 'N/A')}")
                    print(f"   선정: {selection.get('selected_coin', 'None')}")
                    print(f"   신뢰도: {selection.get('confidence_score', 0)}/100")
                    
                elif phase == "phase3" and 'trading_parameters' in result:
                    params = result['trading_parameters']
                    print(f"   Ticker: {params.get('coin_ticker')}")
                    print(f"   Entry: {params.get('entry_price')}, Target: {params.get('target_price')}")
                    
                elif phase is None and 'principles_document' in result:
                    print(f"   원칙 문서 크기: {len(result.get('principles_document', ''))}자")
                    print(f"   신뢰도: {result.get('confidence_level', 0)}%")
                
                result = self._normalize_confidence_scores(result)
                print(f"✅ GPT-5 응답 처리 완료")
                return result
            
            return result if result else {"error": "GPT-5 응답 처리 실패"}

        except openai.BadRequestError as e:
            print(f"❌ 잘못된 요청: {e}")
            if retry_count < MAX_RETRIES and "token" in str(e).lower():
                print(f"🔄 토큰 제한 문제로 추정 - 재시도...")
                time.sleep(5)
                return self._call_gpt5(
                    prompt=prompt,
                    response_format=response_format,
                    reasoning_effort=reasoning_effort,
                    text_verbosity=text_verbosity,
                    phase=phase,
                    force_new=force_new,
                    retry_count=retry_count + 1
                )
            return {"error": f"잘못된 요청: {str(e)}"}
            
        except openai.APIError as e:
            print(f"❌ OpenAI API 오류: {e}")
            if retry_count < MAX_RETRIES:
                wait_time = 5 * (retry_count + 1)
                print(f"🔄 API 오류 - {wait_time}초 후 재시도...")
                time.sleep(wait_time)
                return self._call_gpt5(
                    prompt=prompt,
                    response_format=response_format,
                    reasoning_effort=reasoning_effort,
                    text_verbosity=text_verbosity,
                    phase=phase,
                    force_new=force_new,
                    retry_count=retry_count + 1
                )
            return {"error": f"OpenAI API 오류: {str(e)}"}
            
        except Exception as e:
            print(f"❌ 알 수 없는 GPT-5 호출 오류: {e}")
            import traceback
            traceback.print_exc()
            if retry_count < MAX_RETRIES:
                print(f"🔄 예외 발생 - 재시도...")
                time.sleep(3 * (retry_count + 1))
                return self._call_gpt5(
                    prompt=prompt,
                    response_format=response_format,
                    reasoning_effort=reasoning_effort,
                    text_verbosity=text_verbosity,
                    phase=phase,
                    force_new=True,
                    retry_count=retry_count + 1
                )
            return {"error": f"GPT-5 호출 실패: {str(e)}"}

    # "Phase별 기본 오류 응답을 반환하는 메서드" (인자: self, phase)
    def _get_default_error_response(self, phase: str) -> Dict:
        """Phase별 기본 오류 응답"""
        if phase == "phase1":
            return {
                "action": "wait",
                "market_assessment": {"market_regime": "unknown"},
                "final_decision": {
                    "top_3_tickers": [],
                    "confidence_level": 0,
                    "wait_minutes": 60,
                    "wait_reason": "GPT-5 응답 처리 실패"
                },
                "error": "GPT-5 응답 처리 실패"
            }
        elif phase == "phase2":
            return {
                "action": "wait",
                "final_selection": {
                    "selected_coin": "",
                    "confidence_score": 0,
                    "wait_reason": "GPT-5 응답 처리 실패"
                },
                "error": "GPT-5 응답 처리 실패"
            }
        elif phase == "phase3":
            return {
                "error": "GPT-5 응답 처리 실패 - 전략 수립 불가",
                "trading_parameters": {
                    "coin_ticker": "",
                    "entry_price": 0,
                    "target_price": 0,
                    "stop_loss_price": 0
                }
            }
        elif phase is None: 
            return {
                "error": "원칙 생성 실패",
                "principles_document": "",
                "confidence_level": 0
            }
        else:
            return {"error": f"Phase {phase} 처리 실패"}

    # "Phase 1 시장 진단 및 후보 선정을 수행하는 메서드" (인자: self, market_data, coins_data, memory)
    def analyze_market_phase1(self, 
                            market_data: Dict[str, Any], 
                            coins_data: Dict[str, Any], 
                            memory: Dict[str, str] = None) -> Dict[str, Any]:

        self._start_new_session()

        # ========== memory 관련 부분 주석처리 시작 ==========
        # memory_context = ""
        # if memory and (memory.get('long_term', '').strip() or memory.get('short_term', '').strip()):
        #     memory_context = f"""
        # <memory_context>
        # Long-term principles:
        # {memory.get('long_term', 'None')}
        # 
        # Recent experiences:
        # {memory.get('short_term', 'None')}
        # </memory_context>"""
        # ========== memory 관련 부분 주석처리 끝 ==========

        # memory_context 변수를 빈 문자열로 설정
        memory_context = ""

        prompt = f"""<role>
You are a Master Trading Strategist. Your expertise lies in synthesizing pre-analyzed, complex market data to form a coherent market thesis. You excel at interpreting fractal analysis data to select the single most effective trading strategy and pinpoint the assets that best align with it.
</role>

<context_awareness>
A significant upgrade has been implemented. Your data now includes a powerful `historical_structure_summary` object for each timeframe. This object contains pre-analyzed data, freeing you to focus on high-level strategy.

Key fields you MUST utilize:
-   `support_resistance`: Provides multi-layered, algorithmically identified key price levels.
-   `fractal_info`:
    -   `hurst_exponent`: A critical value. < 0.5 indicates a "Mean-reverting" market (good for Range Trading, Mean Reversion). > 0.5 indicates a "Trending" market (good for Breakouts, Momentum). ~0.5 suggests a "Random Walk".
    -   `market_type`: A direct interpretation of the Hurst Exponent.
-   `pattern_similarity`:
    -   `similarity_score`: A 0-1 score of how closely the current pattern matches a significant historical pattern. A score > 0.75 is considered high.
    -   `pattern_outcome`: The historical outcome of that similar pattern (e.g., "bullish", "bearish").

Your primary task is no longer to find the fractal, but to **interpret the fractal analysis that has already been done for you.**
</context_awareness>

<market_data>
{json.dumps({'btc_data': market_data.get('btc_data', {}), 'timestamp': market_data.get('timestamp')}, ensure_ascii=False)}
</market_data>

<altcoin_screener_data>
{json.dumps(coins_data, ensure_ascii=False)}
</altcoin_screener_data>

<strategy_playbook>
You have six core strategies. Choose ONE that best fits the current market regime as defined by the provided `fractal_info` and `pattern_similarity` data.

1.  **Strategy A: Momentum Breakout (모멘텀 돌파)**
    -   **Best Used When:** BTC's `market_type` is clearly "Trending", and multiple altcoins show high `similarity_score` (>0.75) with a "bullish" `pattern_outcome`.
    -   **Signals:** Coins already breaking out with massive volume, confirming the pre-analyzed pattern.

2.  **Strategy B: Pre-Breakout Condensation (폭발 직전 포착)**
    -   **Best Used When:** BTC's `market_type` is transitioning from "Mean-reverting" to "Trending". The key signal is an altcoin with a very high `similarity_score` (>0.8) to a historical consolidation pattern that had a strong "bullish" outcome.
    -   **Signals:** Rising OBV, Bollinger Band Squeeze, as secondary confirmation.

3.  **Strategy C: Blue-Chip Reversal (대장주 반등 매매)**
    -   **Best Used When:** BTC's `market_type` is "Mean-reverting" after a drop. Look for major altcoins bouncing from a `major_supports` level with a confirmed reversal `pattern_similarity`.
    -   **Signals:** Relative strength, volume confirmation at a key support level.

4.  **Strategy D: Mean Reversion ('고무줄' 전략)**
    -   **Best Used When:** A specific coin's `market_type` is strongly "Mean-reverting" (Hurst < 0.4), and it's trading far from its mean, often near a `major_supports` level.
    -   **Signals:** Deeply oversold RSI, touching lower Bollinger Bands.

5.  **Strategy E: Range Trading ('박스권' 매매)**
    -   **Best Used When:** BTC's `market_type` is "Mean-reverting" or "Random walk", and the `dominant_pattern` description indicates a sideways market.
    -   **Signals:** A clear horizontal range defined by the `support_resistance` data.

6.  **Strategy F: Narrative Momentum ('주도 테마' 추종)**
    -   **Best Used When:** A specific theme is dominating AND the `pattern_similarity` scores for coins in that theme are consistently high and bullish, indicating a coordinated structural move.
    -   **Signals:** Multiple coins from the same category are top gainers.
</strategy_playbook>

<primary_objective>
1.  First, analyze BTC's `historical_structure_summary` across all timeframes, especially the `fractal_info`, to determine the definitive **Market Regime** (Trending, Mean-reverting, or Random Walk).
2.  Second, based on this regime, select the **single most appropriate strategy** (A-F) from the `<strategy_playbook>`.
3.  Third, screen the `<altcoin_screener_data>`. Identify the **TOP 3 candidates** whose `historical_structure_summary` (especially `pattern_similarity.similarity_score` and `pattern_similarity.pattern_outcome`) perfectly aligns with your chosen strategy.
4.  In your `final_decision`, the `reasoning` text MUST start by stating the Market Regime based on the Hurst Exponent. Then, explain your strategy choice and justify your candidate selection by explicitly referencing values from their `historical_structure_summary`.
</primary_objective>

<final_decision_rule>
- **PROCEED:** If you have identified a clear Market Regime and found at least one candidate with a strong `similarity_score` (>0.75) that fits your chosen strategy.
- **WAIT:** If the Market Regime is unclear (e.g., Hurst Exponent is ~0.5 across all timeframes), or if no candidates show a compelling `similarity_score`. When you WAIT, you MUST provide a specific `wait_minutes` value and justify it.
</final_decision_rule>
"""

        response_format = {
            "type": "json_schema",
            "name": "market_screening",
            "schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["proceed", "wait"]
                    },
                    "market_assessment": {
                        "type": "object",
                        "properties": {
                            "btc_trend": {"type": "string"},
                            "altcoin_strength": {"type": "number", "minimum": 0, "maximum": 100},
                            "opportunity_count": {"type": "integer"},
                            "market_regime": {"type": "string"}
                        },
                        "required": ["btc_trend", "altcoin_strength", "opportunity_count", "market_regime"],
                        "additionalProperties": False
                    },
                    "candidates_evaluation": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "momentum_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "independence_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "technical_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "risk_reward_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "timing_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "total_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "key_strength": {"type": "string"}
                            },
                            "required": ["momentum_score", "independence_score", "technical_score", "risk_reward_score", "timing_score", "total_score", "key_strength"],
                            "additionalProperties": False
                        }
                    },
                    "final_decision": {
                        "type": "object",
                        "properties": {
                            "top_3_tickers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 3
                            },
                            "reasoning": {"type": "string"},
                            "confidence_level": {"type": "number", "minimum": 0, "maximum": 100},
                            "expected_profit_range": {"type": "string"},
                            "memory_influence": {"type": "string"},
                            "wait_minutes": {
                                "type": "integer",
                                "minimum": 15,
                                "maximum": 240,
                                "default": 60
                            },
                            "wait_reason": {
                                "type": "string",
                                "default": ""
                            }
                        },
                        "required": [
                            "top_3_tickers", 
                            "reasoning", 
                            "confidence_level", 
                            "expected_profit_range", 
                            "memory_influence",
                            "wait_minutes",
                            "wait_reason"
                        ],
                        "additionalProperties": False
                    }
                },
                "required": ["action", "market_assessment", "final_decision"],
                "additionalProperties": False
            }
        }

        result = self._call_gpt5(
            prompt=prompt,
            response_format=response_format,
            reasoning_effort="high",
            text_verbosity="medium",
            phase="phase1",
            force_new=True
        )
        
        if result and not result.get('error'):
            result = self._normalize_confidence_scores(result)
        
        return result

    # "Phase 2 통합 심층 분석을 수행하는 메서드" (인자: self, candidates_data, memory)
    def analyze_deep_phase2_unified(self, 
                                   candidates_data: Dict[str, Any],
                                   memory: Dict[str, str] = None) -> Dict[str, Any]:
        
        # ========== memory 관련 부분 주석처리 시작 ==========
        # memory_context = ""
        # if memory and (memory.get('long_term', '').strip() or memory.get('short_term', '').strip()):
        #     memory_context = f"""
        # <learned_wisdom>
        # {memory.get('long_term', 'No established principles yet')}
        # {memory.get('short_term', 'No recent trades')}
        # </learned_wisdom>"""
        # ========== memory 관련 부분 주석처리 끝 ==========
        
        # memory_context 변수를 빈 문자열로 설정
        memory_context = ""

        context_hint = ""
        if 'phase1' in self.cache_contexts:
            context_hint = f"""
<previous_context>
Phase 1 Analysis: {self.cache_contexts['phase1']}
</previous_context>"""

        prompt = f"""<role>
You are a Specialist Trading Analyst. Your expertise is in quantitative validation. You take a high-level strategic thesis from the Master Strategist and meticulously score candidates based on pre-analyzed data to find the single best fit.
</role>

<context_awareness>
Your role has been upgraded. You no longer need to visually confirm patterns. Instead, you will work with the rich `historical_structure_summary` object provided for each candidate. Your mission is to **quantitatively score how well a candidate's data aligns with the strategic thesis** set in Phase 1.

Key data points for your analysis:
-   `hurst_exponent` & `market_type`
-   `pattern_similarity.similarity_score` & `pattern_similarity.pattern_outcome`
-   `support_resistance` levels

Your primary task is to use the data to validate the thesis, not to form a new one.
</context_awareness>

<!-- Contains the "selected_strategy" and the key analytical reasoning (e.g., target market_type, required pattern_outcome) from Phase 1 -->
{context_hint} 

<candidates_data>
{json.dumps(candidates_data, ensure_ascii=False)}
</candidates_data>

<analytical_frameworks_by_strategy>
You MUST use the specific data-driven framework that matches the strategy chosen in Phase 1. The `Thesis_Alignment_Score` is the most critical metric.

IF Strategy was "Momentum Breakout":
-   **Thesis_Alignment_Score (1-10):** Based on `pattern_similarity`. Is the `similarity_score` > 0.75 AND the `pattern_outcome` "bullish"? (10 for score > 0.85).
-   **Market_Regime_Fit (1-10):** Based on `fractal_info`. Is the `market_type` "Trending"? (10 for Hurst > 0.6).
-   **Volume_Confirmation (1-10):** Is the `volume_structure.trend` "increasing"?
-   **Relative_Strength (1-10):** Is it a market leader? (Score based on relative performance).

IF Strategy was "Pre-Breakout Condensation":
-   **Thesis_Alignment_Score (1-10):** Based on `pattern_similarity`. Is the `similarity_score` > 0.8 AND `pattern_outcome` "bullish"? (10 for score > 0.9).
-   **Market_Regime_Fit (1-10):** Based on `fractal_info`. Is the `market_type` transitioning from "Mean-reverting" to "Trending"?
-   **Volume_Confirmation (1-10):** Is the `volume_structure.obv_trend` "accumulation"?
-   **Imminence (1-10):** Is the current price near the top of the range defined in `support_resistance`?

IF Strategy was "Blue-Chip Reversal":
-   **Thesis_Alignment_Score (1-10):** Based on `pattern_similarity`. Is the `similarity_score` > 0.75 AND `pattern_outcome` "bullish"?
-   **Structural_Support (1-10):** Is the current price bouncing directly off a `major_supports` level?
-   **Market_Regime_Fit (1-10):** Based on `fractal_info`. Is the `market_type` "Mean-reverting"? (10 for Hurst < 0.45).
-   **Volume_Confirmation (1-10):** Is the `volume_structure.trend` "increasing" on the bounce?

IF Strategy was "Mean Reversion":
-   **Thesis_Alignment_Score (1-10):** How strongly "Mean-reverting" is the `market_type`? (10 for Hurst < 0.4).
-   **Price_Extremity (1-10):** How close is the price to a `major_supports` level and how oversold is the RSI?
-   **Reversal_Signal_Clarity (1-10):** Does the `pattern_similarity` show a bullish reversal pattern, even with a moderate score?
-   **Catalyst_Absence (1-10):** Was there any negative news? No news is good news here.

IF Strategy was "Range Trading":
-   **Thesis_Alignment_Score (1-10):** How strongly "Mean-reverting" or "Random walk" is the `market_type`? (10 for Hurst between 0.4 and 0.55).
-   **Range_Clarity (1-10):** Does the `dominant_pattern` description confirm a sideways market? Are `major_supports` and `major_resistances` well-defined?
-   **Risk_Reward (1-10):** Is the range between support and resistance wide enough?
-   **Entry_Location (1-10):** Is the current price near the bottom of the defined range?

IF Strategy was "Narrative Momentum":
-   **Thesis_Alignment_Score (1-10):** Based on `pattern_similarity`. Is the `similarity_score` > 0.75 AND `pattern_outcome` "bullish"?
-   **Narrative_Confirmation (1-10):** Is this coin part of the dominant theme identified in Phase 1?
-   **Leader_Status (1-10):** Is this the clear leader of the theme?
-   **Volume_Confirmation (1-10):** Is the `volume_structure.trend` strongly "increasing"?
</analytical_frameworks_by_strategy>

<primary_objective>
1.  First, extract the `<selected_strategy>` and its core requirements from the context.
2.  Second, for each candidate, meticulously apply the corresponding analytical framework, scoring each dimension based on the provided `historical_structure_summary`.
3.  Third, select the single candidate with the highest overall score, giving special weight to the **Thesis_Alignment_Score**. A low Thesis_Alignment_Score disqualifies a candidate.
4.  Fourth, in your `final_decision`'s `reasoning`, you MUST justify your choice by referencing the specific data points (e.g., `similarity_score: 0.82`, `hurst_exponent: 0.65`) from the chosen candidate's summary.
5.  If no candidate achieves a high Thesis_Alignment_Score (e.g., all scores below 7), your action MUST be "wait".
6.  CRITICAL (When you WAIT): You MUST provide a `wait_minutes` value and a `wait_reason` explaining what specific data change you are waiting for (e.g., "waiting for a candidate's similarity_score to cross 0.75").
</primary_objective>
"""

        response_format = {
            "type": "json_schema",
            "name": "unified_deep_analysis",
            "schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["proceed", "wait"]
                    },
                    "multi_perspective_analysis": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "perspectives": {
                                    "type": "object",
                                    "properties": {
                                        "conservative": {"type": "number", "minimum": 0, "maximum": 100},
                                        "technical": {"type": "number", "minimum": 0, "maximum": 100},
                                        "risk_management": {"type": "number", "minimum": 0, "maximum": 100},
                                        "value": {"type": "number", "minimum": 0, "maximum": 100},
                                        "momentum": {"type": "number", "minimum": 0, "maximum": 100}
                                    },
                                    "required": ["conservative", "technical", "risk_management", "value", "momentum"],
                                    "additionalProperties": False
                                },
                                "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
                                "strengths": {"type": "array", "items": {"type": "string"}},
                                "weaknesses": {"type": "array", "items": {"type": "string"}},
                                "key_insight": {"type": "string"}
                            },
                            "required": ["perspectives", "overall_score", "strengths", "weaknesses", "key_insight"],
                            "additionalProperties": False
                        }
                    },
                    "perspective_consensus": {
                        "type": "object",
                        "properties": {
                            "aligned_perspectives": {"type": "array", "items": {"type": "string"}},
                            "conflicting_perspectives": {"type": "array", "items": {"type": "string"}},
                            "dominant_view": {"type": "string"}
                        },
                        "required": ["aligned_perspectives", "conflicting_perspectives", "dominant_view"],
                        "additionalProperties": False
                    },
                    "final_selection": {
                        "type": "object",
                        "properties": {
                            "selected_coin": {"type": ["string", "null"]},
                            "confidence_score": {"type": "number", "minimum": 0, "maximum": 100},
                            "selection_rationale": {"type": "string"},
                            "expected_return": {"type": "string"},
                            "risk_factors": {"type": "array", "items": {"type": "string"}},
                            "wait_minutes": {
                                "type": "integer",
                                "minimum": 15,
                                "maximum": 240,
                                "default": 30
                            },
                            "wait_reason": {
                                "type": "string",
                                "default": "Candidates do not meet minimum quality threshold"
                            },
                            "memory_influence": {"type": "string"}
                        },
                        "required": [
                            "selected_coin", 
                            "confidence_score", 
                            "selection_rationale", 
                            "expected_return", 
                            "risk_factors", 
                            "wait_minutes",
                            "wait_reason", 
                            "memory_influence"
                        ],
                        "additionalProperties": False
                    }
                },
                "required": ["action", "perspective_consensus", "final_selection"],
                "additionalProperties": False
            }
        }

        result = self._call_gpt5(
            prompt=prompt,
            response_format=response_format,
            reasoning_effort="high",
            text_verbosity="low",
            phase="phase2",
            force_new=False
        )
        
        if result and not result.get('error'):
            result = self._normalize_confidence_scores(result)
        
        return result

    # "Phase 3 거래 전략을 수립하는 메서드" (인자: self, coin_data, selected_coin, deep_analysis, memory)
    def create_strategy_phase3(self, 
                              coin_data: Dict[str, Any], 
                              selected_coin: str, 
                              deep_analysis: Dict[str, Any] = None,
                              memory: Dict[str, str] = None) -> Dict[str, Any]:
        
        # ========== memory 관련 부분 주석처리 시작 ==========
        # memory_context = ""
        # if memory and (memory.get('long_term', '').strip() or memory.get('short_term', '').strip()):
        #     memory_context = f"""
        # <trading_wisdom>
        # {memory.get('long_term', '')}
        # {memory.get('short_term', '')}
        # </trading_wisdom>"""
        # ========== memory 관련 부분 주석처리 끝 ==========
        
        # memory_context 변수를 빈 문자열로 설정
        memory_context = ""

        analysis_context = ""
        if deep_analysis:
            selection = deep_analysis.get('final_selection', {})
            analysis_context = f"""
<previous_analysis>
Selected: {selection.get('selected_coin', selected_coin)}
Confidence: {selection.get('confidence_score', 0)}/100
Rationale: {selection.get('selection_rationale', 'N/A')}
</previous_analysis>"""

        context_hints = []
        for phase in ['phase1', 'phase2']:
            if phase in self.cache_contexts:
                context_hints.append(f"{phase.upper()}: {self.cache_contexts[phase]}")
        
        context_hint_str = ""
        if context_hints:
            context_hint_str = f"""
<analysis_chain>
{chr(10).join(context_hints)}
</analysis_chain>"""

        atr_info = coin_data.get('atr_analysis', {})
        current_price = coin_data.get('current_price', 0)

        prompt = f"""<role>
You are an Elite Trade Execution Tactician for the Korean Upbit market, operating as a fully autonomous decision-maker. Your specialty is translating a data-rich strategic thesis into a precise, executable trade plan with zero ambiguity.
</role>

<mission>
Your sole mission is to design a high-probability swing trade that captures the **'Most Probable Move' (MPM)**.

The MPM is defined by the key price levels within the validated candidate's `historical_structure_summary`. This mission prioritizes **certainty and flawless execution based on pre-analyzed data.** We are not interpreting charts; we are calculating an optimal trade based on the provided structural data.
</mission>

<context_awareness>
You are receiving the single, fully-vetted candidate from Phase 2. The `historical_structure_summary` for this candidate is not just context; it is your primary source for all price calculations.

Your critical data points are inside the `support_resistance` object:
-   `major_resistances`: [R1, R2, R3]
-   `major_supports`: [S1, S2, S3]
-   `pivot_level`: The central pivot.
-   `vwap`: The volume-weighted average price.

Your task is to use these specific price levels to construct the final trade plan.
</context_awareness>

<context_data>

{analysis_context}
<!-- This context contains the 'selected_strategy' and the candidate's complete data, including the 'historical_structure_summary' -->
{context_hint_str}
- Market Data: {json.dumps(coin_data, ensure_ascii=False)}
- Volatility Intel: {json.dumps({'current_price': current_price, **atr_info}, ensure_ascii=False)}
</context_data>

<tactical_framework_by_strategy>
You MUST define your entry, target, and stop-loss levels by referencing the explicit price levels from the candidate's `historical_structure_summary.support_resistance` object.

IF Strategy was "Momentum Breakout":
-   Entry: An aggressive limit order just above the first major resistance (`major_resistances[0]`).
-   Stop-loss: Placed structurally below the breakout level, using the `pivot_level` as a guide.
-   Target: The next major resistance level (`major_resistances[1]`).

IF Strategy was "Pre-Breakout Condensation":
-   Entry: A patient limit order in the upper part of the range, e.g., (`pivot_level` + `major_resistances[0]`) / 2.
-   Stop-loss: Placed clearly below the lowest major support (`major_supports[0]`).
-   Target: A measured move, calculated as: `major_resistances[0]` + (`major_resistances[0]` - `major_supports[0]`).

IF Strategy was "Blue-Chip Reversal":
-   Entry: A limit order at the first major support level (`major_supports[0]`).
-   Stop-loss: Placed structurally below the second major support level (`major_supports[1]`).
-   Target: The `pivot_level` or the `vwap`, whichever is more conservative.

IF Strategy was "Mean Reversion":
-   Entry: A contrarian limit order at the first major support (`major_supports[0]`).
-   Stop-loss: A tight stop placed below the second major support (`major_supports[1]`).
-   Primary Target: The `vwap`, representing a return to the mean.

IF Strategy was "Range Trading":
-   Entry: A limit order at the first major support level (`major_supports[0]`).
-   Stop-loss: A tight stop placed just below the same support level (`major_supports[0]`).
-   Target: A limit sell order placed at the first major resistance level (`major_resistances[0]`).

IF Strategy was "Narrative Momentum":
-   Entry: An aggressive market order. The exact entry price will be the current market price upon execution.
-   Stop-loss: Based on volatility, set at `current_price - (1.5 * atr)`.
-   Target: The second major resistance level (`major_resistances[1]`) to capture a larger part of the move.
</tactical_framework_by_strategy>

<execution_rules>
CRITICAL: These rules are non-negotiable and MUST be applied to the prices derived from the tactical framework.

1.  **Front-Run Entries**: After calculating your entry price from the tactics, adjust it by setting the final limit order ~0.3% **ABOVE** that calculated price.
2.  **Front-Run Exits**: After calculating your target price, adjust it by setting the final take-profit order ~0.5% **BELOW** that calculated price.
3.  **Thesis-Based Stop-Loss**: The stop-loss MUST be placed at a price that structurally invalidates the thesis, as defined in the tactical framework. Adjust for volatility.
4.  **All-In Costs**: All final price levels must account for a 0.1% round-trip fee and potential slippage.
5.  **Momentum Exception**: Market orders are authorized ONLY when the tactical framework explicitly calls for it.
</execution_rules>

<task>
Generate a complete trading strategy in the required JSON format. Your reasoning for entry, target, and stop-loss MUST explicitly reference the specific price levels (e.g., `major_supports[0]: 2,750,000`) from the `historical_structure_summary` to justify your calculations.
</task>
"""


        response_format = {
            "type": "json_schema",
            "name": "trading_strategy",
            "schema": {
                "type": "object",
                "properties": {
                    "market_analysis": {
                        "type": "object",
                        "properties": {
                            "current_structure": {"type": "string"},
                            "key_levels": {"type": "string"},
                            "entry_timing": {"type": "string"}
                        },
                        "required": ["current_structure", "key_levels", "entry_timing"],
                        "additionalProperties": False
                    },
                    "trading_parameters": {
                        "type": "object",
                        "properties": {
                            "coin_ticker": {"type": "string"},
                            "current_price": {"type": "number"},
                            "entry_price": {"type": "number", "minimum": 0},
                            "target_price": {"type": "number", "minimum": 0},
                            "stop_loss_price": {"type": "number", "minimum": 0},
                            "entry_reason": {"type": "string"},
                            "target_reason": {"type": "string"},
                            "stop_loss_reason": {"type": "string"},
                            "expected_duration_hours": {"type": "number", "minimum": 6, "maximum": 48}
                        },
                        "required": ["coin_ticker", "current_price", "entry_price", "target_price", "stop_loss_price", "entry_reason", "target_reason", "stop_loss_reason", "expected_duration_hours"],
                        "additionalProperties": False
                    },
                    "risk_assessment": {
                        "type": "object",
                        "properties": {
                            "risk_reward_ratio": {"type": "number"},
                            "position_size_suggestion": {"type": "string"},
                            "key_risks": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["risk_reward_ratio", "position_size_suggestion", "key_risks"],
                        "additionalProperties": False
                    },
                    "execution_plan": {
                        "type": "object",
                        "properties": {
                            "entry_method": {"type": "string"},
                            "profit_taking_plan": {"type": "string"},
                            "contingency_plan": {"type": "string"}
                        },
                        "required": ["entry_method", "profit_taking_plan", "contingency_plan"],
                        "additionalProperties": False
                    }
                },
                "required": ["market_analysis", "trading_parameters", "risk_assessment", "execution_plan"],
                "additionalProperties": False
            }
        }

        result = self._call_gpt5(
            prompt=prompt,
            response_format=response_format,
            reasoning_effort="high",
            text_verbosity="medium",
            phase="phase3",
            force_new=False
        )
        
        if result and not result.get('error'):
            result = self._normalize_confidence_scores(result)

            if 'trading_parameters' in result:
                result['altcoin_execution_plan'] = {
                    'btc_dependency_level': 'LOW',
                    'individual_catalyst': result.get('execution_plan', {}).get('entry_method', ''),
                    'independent_profit_driver': 'Technical setup',
                    'success_probability': 75,
                    'memory_applied': memory_context[:100] if memory_context else 'None'
                }
                
                result['altcoin_risk_matrix'] = {
                    'individual_coin_risk': 50,
                    'altcoin_timing_risk': 30,
                    'independent_liquidity_risk': 20,
                    'unique_altcoin_risk': 25,
                    'btc_independence_score': 70
                }
                
                result['altcoin_timeframe_analysis'] = {
                    'm5_individual_signals': 'Analyzed',
                    'h1_independent_direction': 'Analyzed',
                    'h4_unique_trend': 'Analyzed',
                    'daily_individual_structure': 'Analyzed'
                }
        
        return result

    # "거래 후 원칙을 업데이트하는 메서드" (인자: self, trade_result, phase_cache, existing_principles)
    def generate_updated_principles_after_trade(self, 
                                        trade_result: Dict,
                                        phase_cache: Dict,
                                        existing_principles: str = "") -> Optional[str]:

        # ========== 원칙 업데이트 기능 임시 비활성화 ==========
        print("⚠️ 원칙 업데이트 기능이 임시 비활성화되었습니다")
        return existing_principles

#         profit_percent = trade_result.get('profit_rate_percent', 0)
#         is_profit = profit_percent > 0
        
#         prompt = f"""<role>
# You are an OMNI Trading System AI, managing the "Evolve" phase. Your sole mission is to update the DYNAMIC SECTION based on a single trade result to improve long-term profitability and risk management. Your analysis must be concise, strategic, and token-efficient.
# </role>

# <current_principles>
# {existing_principles}
# </current_principles>

# <trade_result>
# Symbol: {trade_result.get('symbol')}
# Entry: {trade_result.get('entry_price')}
# Exit: {trade_result.get('exit_price')}
# P&L: {profit_percent:.2f}%
# Duration: {trade_result.get('holding_period')}
# Exit Type: {trade_result.get('exit_type', 'UNKNOWN')}
# </trade_result>

# <update_rules>
# 1.  **Strategic Focus:** Based on the trade result, identify **ONE** most critical insight.
#     * If profitable, identify the key factor for success (e.g., specific entry volume, retest timing).
#     * If a loss, identify the primary reason for failure (e.g., BTC correlation breakdown, lack of momentum).
# 2.  **Principle Refinement:** Apply the identified insight to update **only one** relevant section (DOs, DON'Ts, Exit Rules, or Checklist).
# 3.  **Simplicity First:** The goal is to make the system **better, not bigger**. Do not add redundant or overly specific rules. If an insight is already covered, do nothing. If it's a new, vital insight, merge it with an existing rule to keep the total rule count minimal.
# 4.  **Token Efficiency:** Each updated rule must be a single, concise sentence. No more than 2 lines per rule. Use specific numbers only when they are the core of the insight.
# 5.  **Maintain Structure:** Keep the exact section headers and rule count.
# 6.  **DO NOT MODIFY THE FIXED SECTION.**
# </update_rules>

# <section_structure>
# MAINTAIN EXACTLY these sections in DYNAMIC SECTION (no additions):
# - Market State Analysis
# - Position Sizing
# - Core Strategy: DOs & DON'Ts
# - Exit Rules
# - Quick Decision Checklist

# DO NOT ADD new categories, subsections, additional headers, or any other sections.
# </section_structure>

# <output_requirements>
# Return the COMPLETE principles document with:
# - FIXED SECTION unchanged (copy exactly as is)
# - DYNAMIC SECTION updated based on this trade, applying the "Strategic Focus" and "Simplicity First" rules.
# </output_requirements>"""

#         response_format = {
#             "type": "json_schema",
#             "name": "principles_update",
#             "schema": {
#                 "type": "object",
#                 "properties": {
#                     "pattern_analysis": {
#                         "type": "object",
#                         "properties": {
#                             "success_patterns": {"type": "array", "items": {"type": "string"}},
#                             "failure_patterns": {"type": "array", "items": {"type": "string"}},
#                             "emerging_patterns": {"type": "array", "items": {"type": "string"}}
#                         },
#                         "required": ["success_patterns", "failure_patterns", "emerging_patterns"],
#                         "additionalProperties": False
#                     },
#                     "principles_document": {
#                         "type": "string",
#                         "description": "Complete updated principles in Markdown"
#                     },
#                     "key_changes": {
#                         "type": "array",
#                         "items": {"type": "string"}
#                     },
#                     "confidence_level": {
#                         "type": "number",
#                         "minimum": 0,
#                         "maximum": 100
#                     }
#                 },
#                 "required": ["pattern_analysis", "principles_document", "key_changes", "confidence_level"],
#                 "additionalProperties": False
#             }
#         }
            
#         try:
#             result = self._call_gpt5(
#                 prompt=prompt,
#                 response_format=response_format,
#                 reasoning_effort="high",
#                 text_verbosity="medium",
#                 phase=None,
#                 force_new=True
#             )

#             if result and not result.get('error'):
#                 confidence = result.get('confidence_level', 0)
#                 print(f"📊 원칙 업데이트 신뢰도: {confidence}/100")
                
#                 principles_doc = result.get('principles_document')
#                 if principles_doc and len(principles_doc) > 100:
#                     self._clear_session_cache()
#                     print("🧹 Phase 캐시 클리어 완료")
#                     return principles_doc
#                 else:
#                     print("⚠️ 원칙 문서가 비어있음 - 기존 원칙 유지")
#                     return existing_principles
                    
#             else:
#                 error_msg = result.get('error', 'Unknown error') if result else 'JSON parsing failed'
#                 print(f"⚠️ 원칙 생성 실패: {error_msg} - 기존 원칙 유지")
#                 return existing_principles
                
#         except json.JSONDecodeError as e:
#             print(f"❌ JSON 파싱 오류: {e} - 기존 원칙 유지")
#             return existing_principles
            
#         except Exception as e:
#             print(f"⚠️ 원칙 업데이트 예외: {e} - 기존 원칙 유지")
#             return existing_principles

    # "하위 호환성을 위한 Phase 2 래퍼 메서드" (인자: self, candidates_data, memory)
    def analyze_deep_phase2(self, candidates_data: Dict[str, Any], memory: Dict[str, str] = None) -> Dict[str, Any]:
        return self.analyze_deep_phase2_unified(candidates_data, memory)
    
    # "페르소나 기반 분석 래퍼 메서드" (인자: self, candidates_data, persona, memory)
    def analyze_deep_phase2_with_persona(self, candidates_data: Dict[str, Any], persona: Dict[str, str], memory: Dict[str, str] = None) -> Dict[str, Any]:
        print(f"⚠️ 페르소나 '{persona.get('name', '')}' 무시 - GPT-5 통합 분석 사용")
        return self.analyze_deep_phase2_unified(candidates_data, memory)

    # "현재 세션의 캐시를 정리하는 메서드" (인자: self)
    def _clear_session_cache(self):
        print(f"🧹 세션 캐시 정리: {self.current_session_id}")
        self.response_cache.clear()
        self.cache_timestamps.clear()
        self.cache_contexts.clear()
        gc.collect()

    # "현재 캐시 상태를 조회하는 메서드" (인자: self)
    def get_cache_status(self) -> Dict[str, Any]:
        status = {
            "session_id": self.current_session_id,
            "cached_phases": [],
            "cache_age": {},
            "api_calls": self.api_call_count
        }
        
        current_time = datetime.now()
        
        for phase in ['phase1', 'phase2', 'phase3', 'phase5']:
            if phase in self.response_cache:
                status["cached_phases"].append(phase)
                
                if phase in self.cache_timestamps:
                    cache_time = self.cache_timestamps[phase]
                    age_minutes = (current_time - cache_time).total_seconds() / 60
                    status["cache_age"][phase] = f"{age_minutes:.1f} minutes"
        
        return status
    
    # "모든 캐시를 강제로 정리하는 메서드" (인자: self)
    def clear_all_cache(self):
        print("🧹 모든 캐시 정리")
        self.cleanup()
    
    # "캐시 유효 시간을 설정하는 메서드" (인자: self, minutes)
    def set_cache_ttl(self, minutes: int):
        self.cache_ttl_minutes = minutes
        print(f"⏱️ 캐시 TTL 설정: {minutes}분")

    # "거래 복구 시 GPT 컨텍스트를 복원하는 메서드" (인자: self, saved_context)
    def restore_context_for_recovery(self, saved_context: Dict[str, Any]):
        try:
            if not saved_context:
                print("⚠️ 복원할 컨텍스트가 없습니다")
                return
            
            print(f"🔄 GPT 컨텍스트 복원 시작...")

            if 'timestamp' in saved_context:
                recovery_session_id = f"RECOVERY_{saved_context['timestamp'].replace(':', '').replace('-', '')[:15]}"
            else:
                recovery_session_id = f"RECOVERY_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            self.current_session_id = recovery_session_id
            print(f"   세션 ID: {recovery_session_id}")

            phase_contexts = saved_context.get('phase_contexts', {})
            
            for phase, context_str in phase_contexts.items():
                if context_str:
                    self.cache_contexts[phase] = context_str[:100]
                    self.response_cache[phase] = f"recovered_{phase}_{recovery_session_id}"
                    self.cache_timestamps[phase] = datetime.now()
                    print(f"   ✅ {phase} 컨텍스트 복원: {context_str[:50]}...")

            if 'deep_analysis_summary' in saved_context:
                summary = saved_context['deep_analysis_summary']
                if 'phase2' not in phase_contexts:
                    selected = summary.get('selected_coin', '')
                    confidence = summary.get('confidence_score', 0)
                    self.cache_contexts['phase2'] = f"Selected: {selected}, Confidence: {confidence}%"[:100]
                    print(f"   ✅ phase2 컨텍스트 재구성: {selected}")

            if 'strategy_summary' in saved_context:
                summary = saved_context['strategy_summary']
                if 'phase3' not in phase_contexts:
                    ticker = summary.get('coin_ticker', '')
                    entry = summary.get('entry_price', 0)
                    self.cache_contexts['phase3'] = f"Strategy: {ticker}, Entry: {entry}"[:100]
                    print(f"   ✅ phase3 컨텍스트 재구성: {ticker}")
            
            print(f"✅ GPT 컨텍스트 복원 완료 (복원된 Phase: {len(self.cache_contexts)}개)")
            
        except Exception as e:
            print(f"❌ GPT 컨텍스트 복원 오류: {e}")
            import traceback
            traceback.print_exc()

    # "Phase간 캐시 공유를 활성화/비활성화하는 메서드" (인자: self, enabled)
    def enable_cache_sharing(self, enabled: bool):
        self.enable_cross_phase_cache = enabled
        status = "활성화" if enabled else "비활성화"
        print(f"🔄 Phase간 캐시 공유: {status}")
    
    # "하위 호환성을 위한 GPT 호출 래퍼 메서드" (인자: self, prompt, response_format)
    def _call_gpt(self, prompt: str, response_format: Dict) -> Dict[str, Any]:
        return self._call_gpt5(
            prompt, 
            response_format, 
            reasoning_effort="medium", 
            text_verbosity="medium",
            phase=None,
            force_new=False
        )
    
    # "캐시 사용 통계를 출력하는 디버깅 메서드" (인자: self)
    def debug_cache_usage(self):
        print("\n" + "="*50)
        print("📊 Response 캐시 사용 통계")
        print("="*50)
        
        status = self.get_cache_status()
        print(f"📍 현재 세션: {status['session_id']}")
        print(f"📞 API 호출 횟수: {status['api_calls']}/{self.max_calls_per_session}")
        print(f"💾 캐시된 Phase: {', '.join(status['cached_phases']) if status['cached_phases'] else 'None'}")
        
        if status['cache_age']:
            print("⏱️ 캐시 나이:")
            for phase, age in status['cache_age'].items():
                print(f"   • {phase}: {age}")
        
        if self.cache_contexts:
            print("📝 저장된 컨텍스트:")
            for phase, context in self.cache_contexts.items():
                print(f"   • {phase}: {context[:50]}...")
        
        print("="*50 + "\n")