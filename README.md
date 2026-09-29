# coin-autotrader-history

2024년 12월부터 개인 프로젝트로 만들어 온 코인 자동매매 시스템 7세대의 변화 과정을 기록한 저장소입니다.

## 세대별 흐름

| 세대 | 이름 | 기간 | 거래소 / 시장 | 판단 방식 | 폴더 |
|---|---|---|---|---|---|
| 1 | VALKYR | 2024-12 ~ | Upbit 원화 현물 / XRP | GPT-4o가 차트·지표·뉴스를 보고 매수·매도·관망 판단 | [`01-valkyr`](./01-valkyr) |
| 2 | ARGOS | 2025-04 이후 | Upbit 원화 현물 / XRP 중심 | GPT 판단 + 코드의 목표가·손절가 실시간 감시 | [`02-argos`](./02-argos) |
| 3 | OMNI | 2025-07 ~ 2025-10 이후 | Upbit 원화 현물 | OODA-R → 다단계 AI 분석 파이프라인 | [`03-omni`](./03-omni) |
| 4 | METIS | 2026-01 이후 | Bybit USDT 무기한 선물 중심 | AI 필터·AI 판단 실험 → AI 제거 → AI+코드 리스크 엔진 → 규칙 기반 | [`04-metis`](./04-metis) |
| 5 | HERMES | 2026-04 | Bybit USDT 무기한 선물 | 백테스트로 정한 규칙 기반 추세 전략 | [`05-hermes`](./05-hermes) |
| 6 | KAIROS | 2026-04 | Bybit USDT 무기한 선물 / BTC | HERMES 신호 엔진을 BTC 한 종목·레버리지 3배로 축소한 규칙 기반 구조 | [`06-kairos`](./06-kairos) |
| 7 | ATHENA | 2026-04 이후 | Bybit 현물 / BTC·ETH·SOL | Smart DCA + Gemini Guardian | [`07-athena`](./07-athena) |

2026년 9월 말 매매를 중지했습니다.

## 세대별로 만든 것

- **VALKYR**: GPT-4o가 차트 이미지, 기술 지표, 뉴스, 공포·탐욕 지수를 보고 `buy / sell / hold`를 결정
- **ARGOS**: AI가 만든 진입가·목표가·손절가를 코드가 실시간으로 감시하도록 판단과 실행을 분리
- **OMNI**: XRP 전용 OODA-R 구조에서 여러 코인을 단계별로 분석하는 파이프라인으로 확장, GPT-5와 Gemini 조합
- **METIS**: 코드가 만든 신호를 AI가 거르는 구조, AI가 방향을 정하는 구조, 코드의 리스크 엔진이 AI 결정을 거부할 수 있는 구조, 규칙 기반 구조를 차례로 구현
- **HERMES**: 지표와 조건을 코드에 명시한 규칙 기반 추세 전략과 백테스트 스크립트
- **KAIROS**: HERMES 신호 엔진을 BTC 한 종목과 레버리지 3배로 줄인 실행 경로, 변동성 돌파 모듈
- **ATHENA**: 매일 실행되는 DCA는 코드가 담당하고, Gemini는 매주 한 번 포트폴리오 상태를 점검하는 Guardian 역할

## 보존 방식

이 저장소는 각 시점의 전체 소스 코드를 모두 모아 둔 저장소가 아닙니다.

세대마다 변화의 흐름을 확인하는 데 필요한 대표 버전만 골랐습니다. 선택한 코드는 당시 모습을 가능한 한 그대로 남겼고, 공개 저장소에 올리기 위해 비밀값, 서버 경로, 개인 금액처럼 공개하기 어려운 부분만 자리표시자로 바꿨습니다.

중간 버전이 빠져 있더라도 README에서 없는 코드를 현재 구조에 맞춰 다시 만들거나 정리하지 않았습니다. 문서와 실제 코드가 다른 경우에는 당시 실행 코드의 동작을 기준으로 설명했습니다.

## 관련 저장소

METIS의 일부 버전은 별도 저장소에 정리해 공개했습니다.

- [metis-ai-trader](https://github.com/deltaomega02/metis-ai-trader) — METIS의 AI 기반 매매 시스템 정리본
- [metis-rule-trader](https://github.com/deltaomega02/metis-rule-trader) — METIS의 규칙 기반 매매 시스템 정리본
