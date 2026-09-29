# 운영자 자동매매 3년 진화 (ATHENA 탄생 배경)

ATHENA는 0에서 시작한 게 아니다. 3년간 7세대 진화의 정점.

---

## 세대별 정리

| 세대 | 프로젝트 | 시기 | 거래소 | AI | 코인 | 핵심 패턴 | 결과 |
|---|---|---|---|---|---|---|---|
| 1 | VALKYR | 2025-02~03 | Upbit | ? | 단일 | 단일 파일 60-100K, v3→v10 | 드랍 |
| 2 | ARGOS | 2025-04~06 | Upbit | GPT | BTC/ETH | CoT, short, v1→v10 | 드랍 |
| 3 | OMNI | 2025-07~10 | Upbit | Gemini 2.5 + GPT-5 듀얼 | XRP/멀티 | OODA, lessons.md, 5시간대 | 드랍 |
| 4 | METIS | 2025-11~2026-01 | Upbit | Gemini 3.0 Pro Vision | BTC/ETH/SOL/XRP | 4 Phase, "Strategist" 정체성 | 드랍 |
| 5 | METIS-F | 2026-01~03 | Bybit Futures | Gemini 3.0 Pro | BTC | AI 거부권만 | 드랍 |
| 6 | HERMES | 2026-03~04 | Bybit Futures | 없음 | BTC/ETH/SOL/XRP | 순수 알고리즘 | -9% / 17일 |
| 7 | **ATHENA** | 2026-04~ | **Bybit Spot** | **Gemini 3.1 Pro Multi-Agent** | **AI 결정** | **포트폴리오 매니저** | 진행 중 |

---

## 각 세대 핵심 학습

### VALKYR (1세대)
- **Ver_10 Concept.txt**에 사실상 ATHENA 컨셉 그려짐:
  - 매시간 GPT 판단
  - 다단계 목표가 (1차/2차/3차 + 매도 비율)
  - 이전 1시간 거래 회고
- **학습**: "AI가 큰 그림 결정 + 코드가 실행" 컨셉 (1년 전 시도)
- **실패 원인**: 단일 파일 + v# 폭발 + 검증 부족

### ARGOS (2세대)
- Chain of Thought 도입 (argos_8_CoT.py)
- BTC/ETH 분리 시도
- SHORT 추가
- **학습**: AI에게 "왜 그런지" 추론 시키기 = 의미 있음
- **실패 원인**: 여전히 v# 폭발 (v1~v10), 복잡도

### OMNI (3세대) — 가장 정교
- **듀얼 AI** (Gemini 2.5 Pro + GPT-5)
- **OODA 루프** (Observe-Orient-Decide-Act)
- **lessons.md 회고 시스템** (자체 학습)
- 5개 시간대 동시 분석 (5분~일봉)
- 50+ 기술 지표
- 운영비 투명 공개 (Google Sheet)
- **학습**: 멀티 AI는 비싸지지만 회고 시스템은 강력
- **실패 원인**: 비용 폭증 + 복잡도, gpt_client v2~v10_5 (안티패턴)

### METIS (4세대)
- **Gemini 3.0 Pro Vision** 단일 (듀얼 폐기)
- **4 Phase 구조** (Data → Direction → Strategy → Execution)
- "Elite Crypto Swing Trader / Strategist" 정체성
- 모듈화 잘됨
- **학습**: 단일 AI가 더 일관됨. 차트 Vision 의미 있음
- **실패 원인**: AI 의존 여전, 비용

### METIS-F (5세대)
- Bybit Futures로 이동
- AI = "거부권만 (PASS/REJECT)"
- **학습**: AI에게 모든 결정 시키면 안 됨. 코드 우선
- **실패 원인**: 너무 좁은 AI 역할

### HERMES (6세대) — 운영 중
- **AI 완전 제거**
- 순수 알고리즘 (4H 추세풀백 + EMA + RSI + ADX)
- 4코인 멀티 (BTC/ETH/SOL/XRP)
- **학습**: AI 빼도 한국 자동매매 1-3% 흑자율 통계는 못 깸
- **결과**: 17일 -9%, V11→V13.1 (5번 변경 = 안티패턴 발동)

### ATHENA (7세대) — 통합
- AI 다시 도입, **단 새 역할: 포트폴리오 매니저**
- Multi-Agent (Analyst + Risk + Manager) — OMNI 패턴 발전
- lessons.md 회고 — OMNI 부활
- 4 Phase OODA — METIS + OMNI 정제
- AI 거부권 일부 — METIS-F Safety
- HERMES 인프라 재활용 — Bybit + WebSocket + DB
- VALKYR Ver_10 다단계 목표 — 드디어 구현
- 단일 모델 (Gemini 3.1 Pro) — OMNI 듀얼의 비용 문제 회피
- Implicit Caching 90% — 2025 신기술 활용
- 무료 데이터 풀스택 — OMNI 비용 폭증 문제 회피

---

## 코드로 증명되는 안티패턴

### v# 폭발 (반복됨)
- VALKYR: v3.0.0 → v3.5 → ... → v10
- ARGOS: v1 → v2 → ... → v10
- OMNI gpt_client: v2 → v3 → v7 → v8 → v9 → v10 → v10_5
- HERMES: V11 → V12 → V13 → V14 → V13.1 (17일에 5번)

→ ATHENA는 50거래까지 동일 파라미터 동결

### AI 역할 진화
```
1-3세대: AI = 매매자 (buy/sell/hold)
4-5세대: AI = 검토자 (PASS/REJECT)
6세대:   AI = 없음 (순수 코드)
7세대:   AI = 포트폴리오 매니저 (비중 결정)  ← 새로움
```

### 거래소 진화
```
1-4세대: Upbit (한국 KRW)
5-6세대: Bybit Futures (글로벌 USDT, 레버리지)
7세대:   Bybit Spot (현물, 포트폴리오 자연스러움)
```

---

## 학술 / 산업 검증 (ATHENA 근거)

| 패턴 | 출처 | 검증 |
|---|---|---|
| **Multi-Agent LLM Portfolio** | arxiv 2501.00826 (2025) | BH + 단일 AI 능가 |
| **15% Threshold Rebalancing** | Shrimpy 백테스트 | HODL +77% |
| **Implicit Caching 90% 할인** | Google 공식 (2025) | 비용 90% ↓ |
| **현물 베이스 + 선물 헷지** | 헤지펀드 표준 | 자본 보존 |
| **OODA 루프** | 군사/금융 | 의사결정 표준 |
| **자체 학습 (lessons)** | OMNI 자체 + AI 회고 논문 | 일관성 ↑ |

---

## ATHENA가 "안 한 것"

3년에 다 시도했지만 **ATHENA에서 의도적으로 제외**:
- 듀얼 AI (OMNI 비용 문제)
- 5+ 시간대 동시 분석 (METIS 단순화)
- Vision 차트 분석 (텍스트 데이터로 충분, 비용 ↓)
- Streamlit 대시보드 (텔레그램으로 충분)
- 다단계 v# 변경 (안티패턴 차단)
- 50+ 지표 (단순화)
- Upbit (해킹 사고 + KRW 송금 1회만)

---

## 진화의 종착지인가?

**아니다.** ATHENA가 8세대를 부를 가능성:
- 본격 운영 후 **"AI도 BH 못 이긴다"** 입증되면 → 9세대 = "AI 없는 단순 BH"
- **"Multi-Agent도 한계"** 입증되면 → 9세대 = "단일 정제 AI"
- **"포트폴리오 매니저도 약하다"** 입증되면 → 9세대 = "AI 추천 + 인간 결정"

운영자 자동매매의 본질은 **"이게 진짜 의미 있나?"** 끊임없이 묻는 것.
ATHENA는 그 답이 아니라, 그 질문의 7번째 진화 형태.
