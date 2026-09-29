# ATHENA Architecture

## 시스템 개요

```
┌─────────────────────────────────────────────────────────────┐
│                    ATHENA Main Loop (4H)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐                                          │
│  │  [Observe]   │  Data Collector (병렬 수집)               │
│  │              │  ├─ Bybit (가격/펀딩/OI/포지션)          │
│  │              │  ├─ Coinalyze (다중거래소 청산)          │
│  │              │  ├─ Alternative.me (F&G)                 │
│  │              │  ├─ yfinance (DXY/SPX)                   │
│  │              │  ├─ Farside (BTC ETF 흐름)               │
│  │              │  ├─ cryptocurrency.cv (뉴스)             │
│  │              │  ├─ Reddit (r/Bitcoin sentiment)         │
│  │              │  └─ kimpga (김프)                        │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  [Orient]    │  Analyst Agent (Gemini 3.1 Pro)         │
│  │              │  Input:  모든 데이터 + 차트 컨텍스트     │
│  │              │  Output: 시장 상태 평가 (JSON)           │
│  │              │  "현재 BTC 4H 약세 전환, 김프 +0.3%..."  │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  [Decide]    │  Risk Agent (Gemini 3.1 Pro)            │
│  │              │  Input:  분석 + 현재 포지션              │
│  │              │  Output: 리스크 점수 0-10                │
│  │              │                                          │
│  │              │  Manager Agent (Gemini 3.1 Pro)         │
│  │              │  Input:  분석 + 리스크 + 현 포트폴리오   │
│  │              │  Output: 목표 비중 + 리밸런싱 결정       │
│  │              │  "BTC 50% → 35%, USDT 15% → 30%..."     │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  [Safety]    │  Safety Layer (코드)                     │
│  │              │  ├─ JSON schema 검증                     │
│  │              │  ├─ 단일 자산 80% 한도                   │
│  │              │  ├─ USDT 5% 최소                         │
│  │              │  ├─ 신뢰도 6/10 컷오프                   │
│  │              │  ├─ 동일 결정 3회 = 경고                 │
│  │              │  └─ DD -15% 셧다운                       │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  [Act]       │  Order Executor (코드)                   │
│  │              │  ├─ 현 비중 vs 목표 비중 계산            │
│  │              │  ├─ 매도 주문 (감소 자산)                │
│  │              │  ├─ 매수 주문 (증가 자산)                │
│  │              │  ├─ Bybit Spot API                       │
│  │              │  └─ 텔레그램 알림                        │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  [Record]    │  DB 기록                                  │
│  │              │  ├─ 결정 (시점, 입력, 출력)              │
│  │              │  ├─ 실행 (체결가, 수수료)                │
│  │              │  └─ 결과 (다음 호출에서 PnL 추적)        │
│  └──────┬───────┘                                          │
│         │                                                  │
│         ▼                                                  │
│  ┌──────────────┐                                          │
│  │  [Learn]     │  주 1회 (일요일 09:00 KST)              │
│  │              │  ├─ 지난 1주 결정 + 결과 분석            │
│  │              │  ├─ AI에게 회고 요청                     │
│  │              │  └─ lessons.md 업데이트                  │
│  └──────────────┘                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘

다음 4H 호출 시 lessons.md를 컨텍스트로 제공 (Implicit Caching 적용)
```

---

## 데이터 흐름 상세

### 1. Observe (1-2분)

병렬 수집 (모든 어댑터 동시 호출):

```python
data = await asyncio.gather(
    bybit.get_ohlcv("BTCUSDT", "4H", 200),
    bybit.get_ohlcv("ETHUSDT", "4H", 200),
    bybit.get_funding_rate(["BTCUSDT", "ETHUSDT"]),
    bybit.get_open_interest(),
    bybit.get_account_positions(),
    coinalyze.get_aggregated_funding(),
    coinalyze.get_liquidations_24h(),
    fear_greed.get_current(),
    yfinance.get_ticker(["DX-Y.NYB", "^GSPC", "GC=F"]),
    farside.scrape_btc_etf_flows(),
    cryptocurrency_cv.get_recent_news(hours=6),
    reddit.get_top_posts("bitcoin", limit=25),
    kimpga.get_premium("BTC", "ETH"),
)
```

### 2. Orient → Decide (Multi-Agent, 5-10초)

**프롬프트 구조** (Caching 최적화):

```
[CACHED: 시스템 프롬프트 + lessons.md + 최근 1주 결정 이력]
  ↓
[FRESH: 현재 데이터 + 현재 포지션]
```

→ 캐시 부분 90% 할인 적용

**Multi-Agent 호출 순서** (순차):
1. Analyst → 시장 평가 JSON
2. Risk → 평가 + 포지션 → 리스크 점수
3. Manager → 평가 + 리스크 + 포트폴리오 → 비중 결정

각 에이전트는 같은 Gemini 3.1 Pro, 다른 프롬프트.
Implicit Caching이 자동으로 공통 prefix 캐시.

### 3. Safety + Act (1-2초)

```python
decision = manager_agent.output  # JSON
if not validate_schema(decision): return
if not check_safety_rules(decision): return
if decision.confidence < 6: return

current = portfolio.get_current_weights()
target = decision.target_weights
deltas = compute_rebalancing(current, target)

for asset, delta in deltas.items():
    if abs(delta) > 0.005:  # 0.5% 이상만 리밸런싱
        execute_order(asset, delta)
```

### 4. Record (즉시)

DB 스키마:
- `decisions`: 시점, 입력 hash, AI 응답, 신뢰도
- `executions`: 결정 ID, 자산, 수량, 가격, 수수료
- `portfolio_snapshots`: 시점, 자산별 보유량 + USD 가치
- `lessons`: 회고 텍스트, 주차

### 5. Learn (주 1회)

```python
recent_decisions = db.get_decisions(days=7)
recent_pnl = portfolio.get_weekly_pnl()
prompt = f"""
지난 1주 결정 {len(recent_decisions)}개 + 결과:
{format(recent_decisions, recent_pnl)}

회고:
1. 가장 좋았던 결정 + 이유
2. 가장 나빴던 결정 + 이유
3. 패턴 발견 (예: "FOMC 직전 진입은 항상 손실")
4. 다음 주 적용할 교훈 (1-3개, 짧게)
"""
new_lesson = gemini.call(prompt)
lessons_file.append(new_lesson)
```

---

## 컴포넌트 책임 분담

| 컴포넌트 | 책임 | 변경 빈도 |
|---|---|---|
| `data_sources/*` | 외부 API 호출 + 정제 | API 변경 시만 |
| `core/data_collector.py` | 모든 데이터 통합 | 새 소스 추가 시 |
| `ai/prompts.py` | Multi-Agent 프롬프트 | **신중히** (안티패턴) |
| `ai/gemini_client.py` | API 호출 + 캐싱 | 거의 X |
| `core/portfolio_manager.py` | AI 결정 → 주문 변환 | 안전장치 추가 시 |
| `core/risk_manager.py` | Safety Layer | 신중 |
| `core/order_executor.py` | Bybit Spot 주문 | API 변경 시만 |
| `core/lessons_keeper.py` | 회고 + lessons.md | 자동 |
| `exchange/bybit_spot_client.py` | Bybit API | 거의 X |
| `database/db_manager.py` | DB CRUD | 스키마 변경 시 |
| `utils/telegram_bot.py` | 알림 | 정책 변경 시만 |

---

## 비용 예측 (4H 주기 기준)

```
호출/일:        6회
호출/월:        180회

토큰 (예상):
  시스템 프롬프트:    1,500 (캐시)
  lessons.md:           500 (캐시)
  최근 결정 이력:    1,000 (캐시)
  현재 데이터:       2,000 (fresh)
  현재 포지션:         500 (fresh)
  ─────────────────────────
  Input total:       5,500

  Output JSON:       1,000

월 비용 (Gemini 3.1 Pro + 캐싱):
  Cached input:   3,000 × 180 × $0.20/1M = $0.108
  Fresh input:    2,500 × 180 × $2.00/1M = $0.900
  Output:         1,000 × 180 × $12.0/1M = $2.160
  ─────────────────────────────────────
  Total:          $3.17/월 (약 ₩4,650)

Multi-Agent (3 호출):
  $3.17 × 3 = $9.51/월 (약 ₩14,000)

GCP e2-small:                    ₩35,000/월
ATHENA AI (Multi-Agent):         ₩14,000/월
모든 데이터 API:                 ₩0/월
─────────────────────────────────
총:                              ₩49,000/월

연 본전 필요:                     +33%/년
```

---

## Phase별 가동 모드

| Phase | 모드 | 설명 |
|---|---|---|
| 0 | `PAPER_MODE=true` + Testnet | 코드 검증, 실제 자금 X |
| 1 | `PAPER_MODE=true` + Mainnet | 실제 데이터, 가상 주문 |
| 2 | `PAPER_MODE=false` + 시드 10% | 소액 실전 |
| 3 | `PAPER_MODE=false` + 전체 시드 | 본격 운영 |

각 Phase 전환 = 운영 정책 승인 필수.
