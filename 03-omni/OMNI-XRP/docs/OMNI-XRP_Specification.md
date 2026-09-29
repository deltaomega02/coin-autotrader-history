## OMNI-XRP: A Specialized OODA-R Agent for Ripple

- **버전:** 1.1 (Brand Identity & Philosophy Alignment)
- **상태:** 개발 착수 준비 완료
- **핵심 사상:** **OMNI-XRP**는 **관찰(Observe) → 판단(Orient) → 결정(Decide) → 행동(Act) → 회고(Reflect)**의 5단계 순환 철학을 기반으로 동작합니다. 여기서 **'OMNI'**는 '모든 코인'이 아닌, **'단일 자산(XRP)에 대한 모든 관점의 데이터를 종합'**한다는 의미를 가집니다. 즉, 모든 시간 프레임, 모든 보조 지표, 그리고 과거의 모든 성공/실패 기록을 총체적으로 분석하여 의사결정을 내립니다.

---

### 최종 데이터베이스 설계 (PostgreSQL)

### **테이블 1: `trades` - 모든 거래의 기록**

이 테이블은 개별 거래의 '요람에서 무덤까지' 모든 것을 기록하는 핵심 테이블입니다. 

"얼마에 사서 얼마에 팔았는가"를 포함한 모든 질문에 완벽하게 답할 수 있습니다.

| 컬럼명 (Column Name) | 데이터 타입 (Data Type) | 설명 (Description) |
| --- | --- | --- |
| `trade_id` | `BIGSERIAL PRIMARY KEY` | 거래의 고유 식별자 (자동 증가) |
| `asset_ticker` | `VARCHAR(10)` | 자산 티커 (고정값: 'XRP') |
| `status` | `VARCHAR(20)` | 거래의 현재 상태 (`PLANNED`, `ACTIVE`, `COMPLETED`, `CANCELLED`) |
| `plan_timestamp` | `TIMESTAMPTZ` | **[계획]** 거래 계획이 수립된 시간 |
| `planned_entry_price` | `NUMERIC(20, 8)` | **[계획]** AI가 진입을 계획한 가격 |
| `planned_target_price` | `NUMERIC(20, 8)` | **[계획]** AI가 목표가로 계획한 가격 |
| `planned_stop_loss` | `NUMERIC(20, 8)` | **[계획]** AI가 최후의 보루로 설정한 손절 가격 |
| `entry_reason` | `TEXT` | **[계획]** 진입 가격 설정에 대한 AI의 상세 근거 |
| `target_reason` | `TEXT` | **[계획]** 목표 가격 설정에 대한 AI의 상세 근거 |
| `stop_loss_reason` | `TEXT` | **[계획]** 손절 가격 설정에 대한 AI의 상세 근거 |
| `position_size_xrp` | `NUMERIC(20, 8)` | **[실행]** 거래에 진입한 XRP 수량 |
| `entry_timestamp` | `TIMESTAMPTZ` | **[실행]** 실제 진입 주문이 체결된 시간 |
| **`actual_entry_price`** | `NUMERIC(20, 8)` | **[실행] "얼마에 샀는가?" - 실제 진입이 체결된 평균 가격** |
| `exit_timestamp` | `TIMESTAMPTZ` | **[결과]** 실제 청산 주문이 체결된 시간 |
| **`actual_exit_price`** | `NUMERIC(20, 8)` | **[결과] "얼마에 팔았는가?" - 실제 청산이 체결된 평균 가격** |
| `trade_result` | `VARCHAR(20)` | **[결과]** 거래 결과 (`PROFIT_TAKE`, `STOP_LOSS`, `MANUAL_EXIT`) |
| `commission_krw` | `NUMERIC(20, 2)` | **[결과]** 해당 거래에서 발생한 총 수수료 (KRW) |
| **`net_profit_krw`** | **`NUMERIC(20, 2)`** | **[결과] 수수료를 모두 제한 최종 순수익 (KRW)** |

**v1.3 대비 변경점:**

- **회고 컬럼 삭제:** `reflection_analysis`, `reflection_key_lesson`을 테이블에서 완전히 제거했습니다. 회고 내용은 거래 종료 시점에 이 테이블의 데이터를 조회하여 AI가 실시간으로 분석하고, 그 결과를 `Reflection.md`에 '기록'할 뿐, DB에 중복 저장하지 않습니다.
- **`commission_krw` 추가:** 수수료를 별도 컬럼으로 관리하여, 수익 계산의 투명성과 정확성을 높였습니다.
- **`trade_volume_xrp` -> `position_size_xrp`:** 보다 표준적인 용어로 변경했습니다.
- **데이터 타입 상세화:** `NUMERIC`의 정밀도를 명시하여 소수점 관리의 완벽성을 기했습니다.

### **워크플로우와 DB 연동 (재정의)**

1. **Phase 1 (전략 수립):** `trades` 테이블에 `status='PLANNED'`로 행을 `INSERT`합니다. `planned_*` 및 `_reason` 컬럼이 채워집니다.
2. **Phase 2 (거래 실행):**
    - 진입 체결 시: `trade_id`를 찾아 `status='ACTIVE'`, `position_size_xrp`, `actual_entry_price`, `entry_timestamp`를 `UPDATE` 합니다.
    - 청산 체결 시: `trade_id`를 찾아 `status='COMPLETED'`, `actual_exit_price`, `exit_timestamp`, `trade_result`를 `UPDATE` 합니다.
    - **순수익 계산 및 저장:** `(actual_exit_price - actual_entry_price) * position_size_xrp - commission_krw` 공식을 통해 `net_profit_krw`를 계산하고 `UPDATE` 합니다.
3. **Phase 3 (학습 순환):**
    - **Reflection.md 생성:** 거래가 `COMPLETED` 되면, 시스템은 해당 `trade_id`의 **모든 데이터를 DB에서 조회**합니다.
    - 조회된 데이터를 GPT 회고 프롬프트에 넣어 분석 결과와 핵심 교훈을 얻습니다.
    - 이 결과를 표준 템플릿에 맞춰 `Reflection.md` 파일 맨 아래에 **추가(Append)**합니다. **DB에는 어떠한 변경도 가하지 않습니다.**

---

### OMNI 철학과 워크플로우의 연결

단순화된 3단계 워크플로우는 OMNI의 5단계 철학을 다음과 같이 내포합니다.

1. **Phase 1: 전략 수립**
    - **관찰 (Observe):** XRP의 모든 상세 지표(OHLCV, RSI, BBands 등)와 과거 기억(`Principles.md`, `Reflection.md`)을 수집하고 관찰합니다.
    - **판단 (Orient) & 결정 (Decide):** 관찰된 모든 데이터를 바탕으로 AI가 리스크와 잠재 수익을 종합적으로 판단하여 최적의 진입/목표/손절가를 결정합니다.
2. **Phase 2: 거래 실행**
    - **행동 (Act):** 결정된 계획에 따라 실제 매매를 실행합니다.
3. **Phase 3: 학습 순환**
    - **회고 (Reflect):** 행동의 결과를 분석하고 교훈을 도출하여 다음 관찰과 판단의 질을 높이는 '기억'으로 자산화합니다.

---

### Phase 1: XRP 거래 전략 수립 (Observe, Orient, Decide)

**목표:** 현재 XRP의 모든 데이터를 **관찰(Observe)**하고, 과거의 경험을 바탕으로 **판단(Orient)**하여 구체적인 실행 계획을 **결정(Decide)**한 후 데이터베이스에 영구 기록합니다.

**실행 프로세스:**

1. **데이터 수집 (Observe):** 리플(XRP)의 모든 상세 지표(5분/1시간/4시간/일봉의 OHLCV, RSI, 볼린저밴드, 이평선 등)와 과거의 기억(`Principles.md`, `Reflection.md`)을 수집합니다.
2. **GPT-4.1 호출 (Orient & Decide):** 수집된 모든 데이터를 전달하여 구체적인 거래 계획 수립을 요청합니다.
3. **DB 기록:** GPT로부터 받은 최종 거래 계획 JSON 전체를 **PostgreSQL DB의 `trade_log` 테이블에 저장(INSERT)**합니다.

**GPT 프롬프트 설계 (1차 - 전략 수립):**

> 너는 OMNI 철학에 따라 움직이는 XRP 전문 퀀트 분석가다. 너의 임무는 '현재 주어진 실시간 데이터'와 '과거의 모든 기억'을 총체적으로 분석하여 최적의 거래 계획을 수립하는 것이다.
> 
> 
> **[1. 분석 대상: 실시간 XRP 데이터 (Observe)]**`{현재 분석 대상인 XRP의 모든 실시간 상세 지표 데이터}`
> 
> **[2. 참고 자료: 과거의 기억 (Orient)](장기 기억: 핵심 거래 원칙)**
> 
> `{Principles.md 파일 내용 전체}`
> 
> **(단기 기억: 최근 거래 로그)**
> 
> `{Reflection.md 파일의 최근 3~5개 거래 내용}`
> 
> **[너의 임무 (Decide)]**
> 
> 1. *[1. 실시간 데이터]**를 먼저 분석하여 `entry_price`, `target_price`, `stop_loss_price`를 포함한 초기 거래 계획을 수립한다.
> 2. 너의 초기 계획이 **[2. 참고 자료]**의 내용, 특히 장기 원칙이나 최근 실패 사례와 상충되지는 않는지 교차 검증한다.
> 3. 만약 상충되는 점이 있다면 그 이유를 명시하고, 그럼에도 현재 판단이 더 합리적이라고 생각하는 근거를 제시하여 최종 결론을 도출한다.
> 
> > [매우 중요한 손절가 원칙]리플(XRP)은 예측 불가능한 급락 후 급반등하는 변동성이 극심한 자산이다. 따라서, stop_loss_price는 일반적인 기술적 분석에 기반한 타이트한 가격으로 설정해서는 안 된다. 이 가격이 터치된다면, 그것은 '단기적인 변동성'이 아니라 '장기적인 추세의 완전한 붕괴'를 의미하는, 절대적인 최후의 보루여야 한다. stop_loss_reason에는 왜 해당 가격이 단기적인 흔들림을 모두 버텨낼 수 있는 '의미있는 최저점' 또는 '구조적 붕괴 지점'인지를 명확히 설명해야 한다. 이 손절가는 사실상 '존재하지만 거의 실행되지 않아야 하는' 수준으로 설정되어야 한다.
> > 
> 1. 위 원칙들을 모두 반영한 최종 거래 계획을 아래 JSON 형식에 맞춰, 각 가격을 설정한 명확한 기술적 근거와 함께 반환해줘.

> JSON
> 
> 
> `{
>   "entry_price": 0.0,
>   "target_price": 0.0,
>   "stop_loss_price": 0.0,
>   "entry_reason": "...",
>   "target_reason": "...",
>   "stop_loss_reason": "..."
> }`
> 

**산출물:** DB에 저장된 고유 `trade_id`를 가진 상세 XRP 거래 계획 레코드.

---

### Phase 2: 거래 실행 및 경험 자산화 (Act & Reflect)

**목표:** 수립된 계획에 따라 거래를 **실행(Act)**하고, 거래가 종료되면 그 결과를 분석하여 경험을 데이터 자산으로 만들어 **회고(Reflect)**의 첫 단계를 시작합니다.

**실행 프로세스:**

1. DB에 저장된 계획에 따라 실시간 감시 모듈로 거래를 실행합니다.
2. 거래가 목표가 도달(성공) 또는 손절가 도달(실패)로 종료되면, 그 결과를 가져옵니다.
3. 거래 계획, 결과, AI 분석을 종합하여 `Reflection.md`에 회고록을 추가(Append)합니다.

**`Reflection.md` 생성 로직:**

Markdown

- `--
Trade Log: {trade_id} | {Timestamp}
Coin: XRP
Strategy: {entry_reason}을 근거로 진입.
Plan: Entry({entry_price}), Target({target_price}), Stoploss({stop_loss_price})
Result: {SUCCESS/FAILURE} at {exit_price}
Analysis: {GPT 또는 로직 기반의 성공/실패 원인 분석}
Key Lesson: {다음 거래에 참고할 핵심 교훈 한 문장}
---`

**산출물:** 새로운 회고 내용이 추가된 `Reflection.md` 파일.

---

### Phase 3: 학습 순환 및 전략 진화 (Reflect)

**목표:** 과거의 모든 성공과 실패 경험에 대한 깊은 **회고(Reflect)**를 통해 '단기 기억(전술)'과 '장기 기억(전략)'을 생성 및 강화하고, 이를 다음 의사결정에 통합하여 시스템의 판단력을 지속적으로 향상시킵니다.

### 3.1. 거래 직후: 심층 회고 분석

거래가 종료되는 즉시(Phase 2 완료 후), GPT-4.1을 호출하여 해당 거래에 대한 심층 회고 분석을 수행하고, 그 결과를 `Reflection.md`에 기록하여 '단기 기억'을 생성합니다.

**회고 분석용 프롬프트:**

> 너는 트레이딩 성과 분석가다. 다음은 하나의 완료된 XRP 거래에 대한 계획과 실제 결과다.
> 
> 
> **[거래 계획]**`{DB에서 조회한 trade_plan 내용}`
> 
> **[실제 결과]**`{실제 거래 결과 내용}`
> 
> 위 내용을 바탕으로 다음 두 가지를 분석해줘:
> 
> 1. **성공/실패 핵심 요인 분석:** 이 거래의 성패를 가른 가장 결정적인 요인은 무엇인가?
> 2. **핵심 교훈 도출 (Key Lesson):** 이 경험을 통해 다음 거래에서 반드시 참고해야 할 교훈을 명료한 한 문장으로 정의해줘.

**산출물:** 분석과 교훈이 포함된, 구조화된 단일 거래 회고 로그 (`Reflection.md`에 추가됨).

### 3.2. [별도 프로세스] 주간 회고 및 원칙 재정립 (장기 기억 형성)

이것은 거래 루프와는 별개로, 시스템의 **'장기 기억'**인 `Principles.md`를 진화시키는 유지보수 작업입니다.

**실행 프로세스:**

1. **주기적 실행:** AWS EventBridge 등을 통해 매주 일요일 23:00 KST에 Lambda 함수를 실행합니다.
2. **규칙 추출:** Lambda 함수는 `Reflection.md`의 모든 내용을 읽어, **"실패/성공 패턴 기반의 실행 가능한 규칙"**을 추출하도록 설계된 GPT 프롬프트를 호출합니다.
3. **장기 기억 업데이트:** GPT가 생성한 새로운 '핵심 거래 원칙'들을 **`Principles.md`** 파일에 덮어씁니다.
4. **(권장) 아카이빙:** `Reflection.md`의 내용을 `Reflection_Archive_{YYYY-MM}.md`로 백업하고 원본은 비워, 다음 한 주간의 새로운 기록을 받을 준비를 합니다.

이러한 **OMNI-XRP** 시스템은 OMNI의 강력한 철학을 계승하여, XRP 시장에 대한 깊이 있는 이해를 바탕으로 끊임없이 학습하고 진화하는 전문 트레이딩 에이전트로 동작할 것입니다.