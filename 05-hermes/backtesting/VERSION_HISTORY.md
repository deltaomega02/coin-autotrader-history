# HERMES 버전 히스토리

**기간**: 2026-04-11 ~ 2026-04-14
**목적**: HERMES 자동매매 시스템의 주요 업그레이드 타임라인 기록

---

## 타임라인 요약

| 버전 | 날짜 | 주요 변경 | 효과 (4년 백테스트) |
|---|---|---|---|
| **v3** | 04-11 | 트레일링 스탑 도입 (1.5/0.3) | 기준점 설정 |
| **v4** | 04-12 | Shared-balance 엔진, 쿨다운 제거 | $17k → $36k (2배) |
| **v5** | 04-14 오전 | 트레일링 재최적화 (1.2/0.1) | $36k → $37k (+슬리피지 내성) |
| **v6** | 04-14 오후 | XRP+3pos+lev7+TP6+ADX30 | $37k → $468k (12.4배) |

---

## v3 — Trailing Stop 도입 (2026-04-11)

### 변경
- v2의 1위 파라미터에 트레일링 스탑 추가
- 그리드 서치로 최적 activation/distance 탐색

### 그리드
```
activations: [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
distances:   [0.3, 0.5, 0.8, 1.0, 1.5, 2.0]
```

### 결과
- **1위: activation 1.5%, distance 0.3%**
- 4년 +1913.7% / DD 26.9%

### 한계
- **그리드가 불완전**: 0.3 미만 distance, 1.5 미만 activation 미탐색
- **독립 백테스트**: 3코인을 독립적으로 시뮬레이션 → 실제 shared wallet 구조 반영 못함

### 파일
- `HERMES/backtest/v3_engine.py`
- `HERMES/backtest/v3_comprehensive.py`
- `v3/v3_results.json`

---

## v4 — Shared-Balance 엔진 + 시드 분석 (2026-04-12)

### 엔진 재작성
사용자 지적: "실제 HERMES는 공유 wallet인데 v3는 독립 백테스트"

새 엔진 `v4_shared_engine.py`:
- 3코인 공유 잔고
- MAX_SIMULTANEOUS=2 전역
- 단일 타임라인
- 일일 서버비 ₩1,150 차감

### 시드 분석 (수동 감독 시나리오)
| 시드 | 4년 결과 | DD |
|---|---|---|
| $100 | **파산** (2022-07) | 86% |
| $200 | **파산** (2024-01) | 95% |
| $300 | 생존 (위험) | 44.3% |
| $500 | 안정 | 26.8% |
| **$600** | **수렴점** | **26.8%** |
| $1000 | 동일 | 26.8% |
| $2000 | 동일 | 26.8% |

**결론**: $500부터 DD 수렴. 현재 잔고로 충분, 추가 입금 효과 없음.

### 쿨다운 제거
v3까지 2연패 → 60분 쿨다운 / 3연패 → 당일 중단 있었음.

백테스트:
- 쿨다운 있음: $16,429 / DD 28.0%
- **쿨다운 없음: $36,017 / DD 26.8%** (수익 2.2배, DD 개선!)

추세 풀백 전략에서 SL 직후 반등이 많은데 쿨다운이 이를 차단 → 수익 대거 상실.

### 변경 파일 (GCP 배포)
- `config/settings.py` (쿨다운 관련 제거)
- `core/risk_manager.py` (쿨다운 로직 제거)

### 일일 수동 감독 역할 확정
매일 텔레그램 거래 기록 공유 → 운영자가 저변동/연패 감지 → 수동 중단 권고.
2023년 같은 저변동 구간 수동 스킵 전제로 시나리오 B 표준화.

---

## v5 — Trailing Stop 재최적화 + 슬리피지 (2026-04-14 오전)

### 발단
실전 BTC SHORT 거래에서 평가익 +1.38%에 트레일링 미활성화 관찰:
- 진입 $71,383
- 저점 $70,400 (-1.38%)
- 트레일링 activation 1.5%에 **0.12%p 미달**
- 반등에 SL 히트 → 원금 손실

"1.5%는 너무 높지 않나?" 검증 필요.

### v5-1: 전수 그리드 서치
- Activations: 0.3~5.0 (14종)
- Distances: 0.1~2.0 (11종)
- **126개 유효 조합 전수 테스트**

**결과**: **1.5/0.3은 75/83위 중위권 하위**. 상위는 Act 0.5~1.2 / Dist 0.1~0.15 plateau.

### v5-2: Walk-Forward 검증
Train/Test 분리:
- 22-23 train vs 24-26 test
- 22-24 train vs 25-26 test

결과: 상위 10개 조합이 train/test 모두 상위 유지 → **과적합 아님 입증**.

### v5-3: 슬리피지 민감도 테스트 (핵심)
사용자 지적: "실전은 슬리피지 있는데 왜 0으로 돌리나?"

엔진에 `slippage_pct` 추가, 후보 조합들을 0~0.15% 슬리피지에서 테스트.

**슬리피지 레벨별 1위 변화**
| 슬리피지 | 1위 | 순이익 |
|---|---|---|
| 0% | 0.8/0.1 | $900k |
| 0.02% | 0.9/0.1 | $313k |
| **0.05% (현실)** | **1.2/0.1** | **$40k** |
| 0.08% | 1.2/0.1 | $3.7k |
| 0.10% | 1.2/0.1 | $195 |

**핵심**: 슬리피지 따라 최적점이 이동. 0.05% 현실 기준 **1.2/0.1이 1위 + 가장 강건**.

### v5-4: 최종 결정 — **1.5/0.3 → 1.2/0.1**
- 슬리피지 0.05% 기준 순이익 $452 → $39k (**87배**)
- DD 26.8% → 16.7% (10%p 개선) [0% 슬리피지 기준]
- 오늘 BTC SHORT 사건 재현 시 손실 → 수익 전환

### 변경 파일 (GCP 배포)
- `config/parameters.py` (ParamSpec 범위)
- `config/tunable_params.json` (운영값)

---

## v6 — 풀 패키지 (2026-04-14 오후)

### v6-1: 종합 파라미터 탐색
v5 트레일링 유지 상태에서 다른 파라미터들 전수 검증.

**단일 변경 효과 (3포지션 기준)**
| 변경 | 수익 개선 | DD 영향 |
|---|---|---|
| daily cap 5→10 | +109% | 0 |
| max_leverage 5→7 | +41% | +0.5%p |
| TP R:R 4.0→6.0 | +31% | 0 |
| ADX 35→30 | +42% | -0.6%p |
| risk 1.5→2.0% | +243% | +5.8%p |
| SL 1.5→1.75 | -42% | -6%p |

### v6-2: 일일 캡 과적합 검증 (사용자 지적)
사용자: "cap 변경은 4년 데이터 과적합 아닐까?"

검증:
1. XRP 단독에서는 cap 변경 효과 0 (cap 5 = cap 999 완전 동일)
2. Walk-forward에서 기간별 최적 캡 달라짐
   - WF-A 22-23 train: cap 5가 1위
   - WF-A 24-26 test: cap 10이 1위
   - **완벽한 regime dependence**
3. 연도별 분석: cap 10이 2022/2023은 오히려 손해, 2024+는 이득

**결론**: 사용자 직감 정답. cap 변경은 **BTC/ETH/SOL 특유 과적합**. **cap 5 유지**.

### v6-3: XRP Out-of-Sample 검증
XRP는 v3~v5 최적화에 사용 안 됨 → 완전 OOS.

**XRP 단독** (수동 감독):
- baseline: -$537 / DD 94.6%
- 안전 패키지: -$83 / DD 56.1%
- 공격 패키지 (risk 2%): +$1,460 / DD 36.1%

→ **XRP 단독은 지는 전략**

**역설적**: 하지만 포트폴리오 추가 시:
- 3코인 2pos 안전: $74,584
- 4코인 2pos 안전: $214,102 (+187%)
- **4코인 3pos 안전: $468,683 (+528%)** ← 최고

XRP 기여분: $152,321 (전체 32.5%)

**메커니즘**: 시간 다변화. XRP가 다른 코인과 다른 타이밍에 시그널 → 빈 슬롯 활용 → 복리 가속.

### v6-4: XRP 방향 분석
SOL은 LONG 차단 중인데 XRP도 그래야 하나?

| 조건 | 양방향 | SHORT만 | LONG만 |
|---|---|---|---|
| 4코인 안전 2pos | **$214k** | $153k | $105k |
| 4코인 안전 3pos | **$468k** | $410k | $162k |

**모든 조건에서 양방향이 1위**. XRP LONG은 단독 -$1,100이지만 **포트폴리오에선 +$59k 기여**.

→ SOL과 달리 XRP는 **양방향 허용**.

### v6-5: 풀 패키지 최종 결정

**변경**:
1. `MAX_LEVERAGE`: 5 → **7**
2. `tp_rr_ratio`: 4.0 → **6.0**
3. `adx_enter_trending`: 35 → **30**
4. `SYMBOLS`: +XRPUSDT (4코인)
5. `MAX_SIMULTANEOUS_POSITIONS`: 2 → **3**

**유지**:
- trailing 1.2/0.1 (v5)
- 쿨다운 제거 (v4)
- risk 1.5%/거래
- 일일 캡 5
- SOL LONG 차단

### 최종 비교 (v5 현재 vs v6 풀 패키지)
| 지표 | v5 | v6 풀 | 차이 |
|---|---|---|---|
| 순이익 | $37,723 | **$468,683** | **12.4배** |
| 연평균 복리 | +167.3% | +380.9% | +213.6%p |
| DD | 27.8% | 28.9% | +1.1%p |
| 승률 | 56.67% | 57.37% | +0.70%p |
| 손실 월 | 22.0% | **12.2%** | **-9.8%p** |
| Calmar | 1,357 | 16,217 | **12배** |
| Profit Factor | 1.21 | 1.30 | +0.09 |

**실전 현실 보정**: 백테스트의 50~80% 기대 → **$230k~$350k** (현재 대비 6~9배).

### v6-6: 텔레그램 고도화 + 트레일링 라벨 수정

**버그 수정**: 트레일링 SL 히트 시 "손절"로 오표시됨
- 원인: 모든 SL 히트가 `STOP_LOSS` 사유로 처리
- 수정: `core/websocket_watcher.py`에서 트레일링 활성화 상태 체크
- 서버 체결(SERVER_TRIGGERED)도 트레일링 활성 시 변환

**텔레그램 전면 리팩토링**:
- 코인 이모지 (🅱 🅴 🆂 🆇)
- 레짐 이모지 (/ / ↔/ )
- 한국어 라벨 (TRENDING_UP → 강세추세)
- KRW 환산 병행
- **PnL 부호 기반 스마트 라벨**: "트레일링 익절" / "손절"

### v6-7: API 최적화 + 중복 주문 방지

관찰: "Too many visits" rate limit 에러 발생 → 다방면 검토

**발견 1**: wallet balance 중복 조회 (코인마다 재호출)
- 수정: `main.py` — 사이클당 1회 조회, 캐시 재사용
- 효과: API 콜 20 → 17 (15% 감소)

**발견 2**: `update_targets` 예외 전파
- 수정: `core/websocket_watcher.py` — try/except로 감싸기
- 로컬 상태는 유지, 서버 업데이트 실패해도 워처는 계속 감시

**발견 3**: orderLinkId 없음 (phantom success 중복 주문 위험)
- 수정: `exchange/bybit_client.py` — UUID 기반 orderLinkId 생성
- `_request`에서 duplicate 에러(110072) 감지 시 성공 처리
- 효과: Bybit 서버 측 중복 거절 메커니즘 활용

### v6-8: 검증 (진행 중)
**Monte Carlo (log-return bootstrap)**:
- 이전 버전(v6_monte_carlo.py)은 OHLC 블록 부트스트랩으로 가격 점프 왜곡
- 수정판(v6_monte_carlo_fixed.py) — 수익률 기반 재샘플링으로 가격 연속성 유지
- N=300 실행 (~25분)

**스트레스 시나리오**:
- 9개 인공 시나리오 (저변동/크래시/하락/상승/휩쏘/변동성)
- 결과: 2/9 생존 (강한 휩쏘, 극한 변동성)
- 해석 주의: synthetic OHLC 구조 한계로 결과 왜곡 가능
- 의미: "강한 움직임"은 시스템 친구, "저변동"은 적

---

## 파일 구조

**코드** (`YOUR_HERMES_DIR/`)
- `main.py` — v6-7 wallet 캐싱 적용
- `config/settings.py` — v6 풀 패키지
- `config/tunable_params.json` — v5 트레일링 + v6 TP/ADX
- `config/parameters.py` — ParamSpec 범위 확장
- `core/websocket_watcher.py` — 트레일링 라벨 + try/except
- `core/risk_manager.py` — 쿨다운 제거 (v4)
- `exchange/bybit_client.py` — orderLinkId UUID
- `utils/telegram_bot.py` — 전면 리팩토링

**백테스트 스크립트** (`HERMES/backtest/`)
- v3: `v3_engine.py`, `v3_comprehensive.py`
- v4: `v4_shared_engine.py`, `v4_seed_sweep.py`, `v4_compound_viz.py`
- v5: `v5_trailing_exhaustive.py`, `v5_walkforward.py`, `v5_slippage_test.py`, `v5_final_optimization.py`, `v5_cooldown_compare.py`, `v5_vbounce_analysis.py`
- v6: `v6_comprehensive.py`, `v6_2pos_detailed.py`, `v6_xrp_validation.py`, `v6_xrp_direction_matrix.py`, `v6_final_comparison.py`, `v6_monte_carlo_fixed.py`, `v6_stress_scenarios.py`

**결과** (`HERMES_백테스팅/`)
- `v3/v3_results.json`
- `v4/v4_seed_sweep.json`, `v4_compound_viz.json`
- `v5/v5_trailing_exhaustive.json`, `v5_slippage_test.json`, `v5_walkforward.json`, `v5_final_optimization.json`, `v5_cooldown_compare.json`, `v5_vbounce_analysis.json`
- `v6/v6_comprehensive.json`, `v6_2pos_detailed.json`, `v6_xrp_validation.json`, `v6_xrp_direction_matrix.json`, `v6_final_comparison.json`, `v6_monte_carlo_fixed.json`, `v6_stress_scenarios.json`

**실전 기록** (`HERMES_실전기록/`)
- `실전거래기록.csv` — 2026-04-09부터

---

## 과거 기각된 제안들 (재제안 시 주의)

1. **Daily cap 10 이상** — 사용자가 과적합 지적, XRP OOS 검증으로 확인됨
2. **Risk per trade 2%+** — 저변동 구간 DD 75% 위험
3. **SL ATR 1.75+** — DD 개선되지만 수익 크게 감소
4. **5분봉 전환** — 수수료 구조상 불가능
5. **횡보 전략 재활성화** — 3년 백테스트 -93% 확인
6. **SOL LONG 허용** — 단독 + 포트폴리오 둘 다 마이너스

## 과거 채택된 변경

1. **쿨다운 완전 제거** (v4)
2. **트레일링 1.5/0.3 → 1.2/0.1** (v5)
3. **MAX_LEVERAGE 5 → 7** (v6)
4. **TP R:R 4.0 → 6.0** (v6)
5. **ADX 진입 35 → 30** (v6)
6. **XRP 추가 (4코인)** (v6)
7. **MAX_SIMULTANEOUS 2 → 3** (v6)
8. **텔레그램 리팩토링 + 트레일링 라벨 수정** (v6)
9. **Wallet 캐싱 + orderLinkId + update_targets try/except** (v6)

---

*Last updated: 2026-04-14*
