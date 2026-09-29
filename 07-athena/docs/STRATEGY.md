# ATHENA 전략 명세

## 핵심 원칙

> **AI는 자금 매니저, 코드는 실행자.**
> AI는 "BTC 비중 늘려라/줄여라" 큰 결정.
> 코드는 정확한 가격/수량/주문 처리.

---

## 1. AI 의사결정 모델

### Multi-Agent 구조

| Agent | 역할 | 입력 | 출력 |
|---|---|---|---|
| **Analyst** | 시장 평가 | 모든 데이터 | `market_view`, `regime`, `key_signals`, `confidence` |
| **Risk Manager** | 위험 평가 | Analyst + 현 포지션 | `risk_score (0-10)`, `concerns`, `position_health` |
| **Portfolio Manager** | 비중 결정 | Analyst + Risk + 현 포트폴리오 + lessons | `target_weights`, `rebalance_actions`, `confidence`, `reasoning` |

### 같은 모델, 다른 프롬프트
- 모두 Gemini 3.1 Pro
- 시스템 프롬프트만 다름 → Caching 효율 ↑
- 호출 순서: Analyst → Risk → Manager (각각의 출력이 다음의 입력)

---

## 2. 포트폴리오 비중 결정 (AI 자율)

### 가능한 자산 (Bybit Spot)
```
BTC   (Bitcoin)            — 모든 포트폴리오 핵심
ETH   (Ethereum)           — 두 번째 핵심
SOL   (Solana)             — 알트 (선택적)
USDT  (Tether)             — 안전 자산 (캐시)
```

향후 추가 검토:
- BNB, XRP, AVAX, LINK 등 (검증 후)

### Safety Constraints (Manager가 따라야 할 룰)

```python
constraints = {
    "max_single_asset": 0.80,    # 단일 자산 최대 80%
    "min_usdt": 0.05,            # USDT 최소 5%
    "min_action_size": 0.005,    # 0.5% 미만 변동은 무시 (수수료)
    "max_total_change": 0.40,    # 4H 한 번에 40% 이상 변경 금지
    "allowed_assets": ["BTC", "ETH", "SOL", "USDT"],
}
```

### Manager 출력 예시

```json
{
  "market_summary": "BTC 4H 약세 전환 신호. ETF 자금 -$200M (어제). DXY 상승. 김프 +0.2% 안정. F&G 35 (공포). 단 SPX 강세 유지.",
  
  "risk_assessment": "현 포지션 BTC 60%로 노출도 높음. 하락 시 영향 큼. 리스크 점수 7/10.",
  
  "current_weights": {
    "BTC": 0.60,
    "ETH": 0.20,
    "USDT": 0.20
  },
  
  "target_weights": {
    "BTC": 0.40,
    "ETH": 0.20,
    "USDT": 0.40
  },
  
  "rebalance_actions": [
    {"asset": "BTC", "action": "REDUCE", "amount_pct": 0.20, "reason": "약세 전환 + ETF 유출"},
    {"asset": "USDT", "action": "INCREASE", "amount_pct": 0.20, "reason": "캐시 비중 늘려 매수 기회 대기"}
  ],
  
  "confidence": 7,
  "reasoning": "ETF 자금 유출 + DXY 상승은 단기 약세 신호. BTC 비중 줄이고 USDT 확보. ETH는 상대적 강세 유지하므로 그대로.",
  
  "next_check_hours": 4,
  "lessons_applied": ["FOMC 12h 전 진입 자제 (lesson #5)"]
}
```

### Manager가 안 하는 것
- 진입 가격 결정 → 코드가 시장가 또는 호가 활용
- SL/TP 설정 → 현물이라 SL X, TP는 다음 호출에서 결정
- 레버리지 → 현물이라 항상 1x

---

## 3. 리밸런싱 실행

### 알고리즘

```python
def execute_rebalance(target_weights, current_weights, total_value):
    deltas = {}
    for asset in ALLOWED_ASSETS:
        target_value = total_value * target_weights[asset]
        current_value = current_weights[asset] * total_value
        delta_value = target_value - current_value
        delta_pct = abs(delta_value) / total_value
        
        if delta_pct < 0.005:  # 0.5% 미만 무시 (수수료 비효율)
            continue
        
        deltas[asset] = delta_value
    
    # 매도 먼저 (USDT 확보), 매수 나중 (USDT 사용)
    sells = {a: v for a, v in deltas.items() if v < 0}
    buys = {a: v for a, v in deltas.items() if v > 0}
    
    for asset, value in sells.items():
        sell_market(asset, abs(value))
    
    for asset, value in buys.items():
        buy_market(asset, value)
```

### 수수료 고려
- Bybit Spot taker: 0.1%
- 4H마다 리밸런싱 = 일 6회 = 월 180회
- 평균 거래 시드 5% × 0.1% × 180 = **시드 9%/월 수수료** ← 위험!

→ **0.5% 임계값**으로 작은 변동 무시. 실제 거래 횟수는 20-40회/월 예상.

→ Bybit BBT 토큰 보유 또는 VIP 등급 시 수수료 ↓

---

## 4. 학습 시스템 (lessons.md)

### 형식

```markdown
# ATHENA Lessons (자동 갱신, 주 1회)

## 검증된 교훈 (확신도 ↑)

### Lesson #1 (2026-04-26 ~ 2026-05-26, 4주 검증)
**규칙**: BTC ETF 누적 자금 유입 -$500M 이상 (1주) → BTC 비중 -10%
**근거**: 4주간 5회 발생, 4회 단기 약세 ($200~$1,500 하락)
**적용**: Manager가 매 결정 시 ETF 흐름 확인

### Lesson #2 (2026-05-15 ~ 진행 중)
**규칙**: F&G < 25 + 김프 < 0% 동시 = 매수 기회 (USDT → BTC 5-10%)
**근거**: ...

## 시도 중 (검증 부족)

### Lesson Candidate (2026-06-01)
**규칙**: SPX -2% 이후 24시간 내 BTC 진입 금지
**상태**: 2회 관찰, 더 필요
```

### lessons 적용

매 4H 호출 시 Manager 프롬프트에 "검증된 교훈" 섹션이 포함:
```
[캐시 영역]
당신은 ATHENA Portfolio Manager입니다.
다음 검증된 교훈을 결정에 반영하세요:

{lessons.md 내용}

[fresh 영역]
현재 데이터: ...
```

---

## 5. 백테스트 가능성

### 어려움
- AI 결정은 비결정적 (같은 입력 → 다른 답)
- 과거 sentiment 데이터 부족 (Reddit, F&G는 OK, 일부 X)
- LLM 답변 시간 시뮬 불가

### 가능 부분
- **15% Threshold Rebalancing 단독** 백테스트 (HERMES 자산)
- 결정 로깅으로 forward test (페이퍼 모드 1-2주)
- HERMES와 같은 기간 비교

### Phase 0/1에서
- 페이퍼 모드 1-2주 = 사실상 forward test
- AI 결정 일관성 + PnL 추적
- BH 같은 기간과 비교

---

## 6. 성공 지표

### Phase 1 (페이퍼 1-2주)
- [ ] AI 결정 JSON schema 100% 준수
- [ ] 시스템 다운 0회
- [ ] AI 일관성 (같은 데이터 ±10% 이내 결정)
- [ ] 가상 PnL > BTC BH

### Phase 2 (소액 실전 1개월)
- [ ] 시드 -10% 미만 유지
- [ ] 거래 횟수 < 50회/월 (수수료 통제)
- [ ] AI 평균 신뢰도 > 6
- [ ] BTC BH 대비 +5%p 이상

### Phase 3 (본격 6개월)
- [ ] DD < 30% (BH 50%+ 보다 우월)
- [ ] CAGR > 20% (또는 BH 비슷)
- [ ] Sharpe > 1.0

---

## 7. 진짜 솔직 (학술 vs 실전)

### 학술적 지지
- Multi-Agent LLM Portfolio = BH 능가 가능 (arxiv 2501.00826)
- 15% Threshold = HODL +77% (Shrimpy)
- 리밸런싱 프리미엄 학계 검증

### 실전적 회의
- 한국 자동매매 1년 흑자율 1-3%
- AI 봇도 같은 통계
- HERMES 17일 -9%

### ATHENA 차별점
- 3년 학습 통합 (다른 봇이 안 가진 것)
- AI 새 역할 (포트폴리오 매니저)
- 비용 효율 (Caching 90%)
- 무료 데이터 풀스택

### 정직한 기댓값
- **연 +20-30%** (검증된 학술 수준)
- **DD -25-35%** (BH 50%+ 대비 우위)
- 안 되면 6개월 후 폐기 / 9세대 진화

---

## 8. 중단 트리거 (자동)

ATHENA 자동 정지:
- 시드 -15% (DD 셧다운)
- API 에러 5회 연속
- AI 응답 schema 깨짐 5회 연속
- 동일 결정 (REDUCE/INCREASE 없음) 6회 연속 (= 무가치)

수동 정지 (운영자 결정):
- 1주일 평가 후 -5% 이상
- 진입/청산 동기 불명확
- 비용 vs 수익 부정적
