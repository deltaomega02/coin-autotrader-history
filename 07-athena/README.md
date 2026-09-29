# ATHENA

선물 중심의 단기 매매에서 벗어나, 현물 DCA를 코드가 실행하고 AI는 주기적으로 포트폴리오를 점검하도록 만든 일곱 번째 세대입니다.

## 핵심 아이디어

ATHENA의 최종 코드는 **Smart DCA + 단일 AI Guardian** 구조입니다.

매일 정해진 시각에 BTC·ETH·SOL을 DCA로 매수하는 기본 동작은 AI를 호출하지 않고 코드가 실행합니다. Gemini는 매주 한 번 포트폴리오 상태를 점검하고, 필요한 경우 DCA 배수나 포트폴리오 비중 조정 방향을 제안합니다. 별도로 15분마다 위기 조건을 확인해 필요한 경우 Guardian을 호출합니다.

AI가 직접 주문 수량을 마음대로 결정하는 구조는 아닙니다. 포트폴리오 조정에 필요한 실제 주문량은 코드가 계산하며, 자산 비중과 거래량, 드로다운 등에 대한 안전 제한도 코드에 들어 있습니다.

## 폴더별 버전 흐름

ATHENA는 한 벌의 최종 코드만 보존했습니다.

- 루트에는 실행 코드와 `athena.service`, 헬스체크·CSV 내보내기 스크립트가 있습니다.
- `docs/ARCHITECTURE.md`, `docs/STRATEGY.md`, `docs/EVOLUTION.md`에는 초기 설계와 세대 변화 기록이 남아 있습니다.
- `ai/`에는 Gemini Guardian과 Function Calling 도구가 있습니다.
- `data_sources/`에는 시장 데이터와 외부 지표를 읽기 위한 어댑터가 있습니다.

문서에는 Analyst → Risk → Manager로 이어지는 3개의 AI 에이전트와 4시간 주기 구조가 적혀 있지만, 최종 실행 코드는 이 구조를 사용하지 않습니다.

실제 코드에서는 하나의 Guardian만 호출하며, 정기 AI 판단도 4시간마다가 아니라 주 1회입니다. DB 스키마에는 이전 멀티 에이전트 구조의 필드가 일부 남아 있습니다.

## 사용 기술

- Python
- Bybit Spot API
- Google Gemini / `gemini-3.1-pro-preview`
- `google-genai`
- Function Calling 기반 agentic loop
- SQLite
- systemd
- GCP
- 외부 데이터 어댑터
  - Bybit 시장 데이터
  - Coinalyze
  - 사이클 지표
  - DefiLlama
  - ETF 흐름
  - Fear & Greed
  - 뉴스
  - Reddit
  - yfinance

## 핵심 구조

기본 거래 대상은 BTC·ETH·SOL이며 USDT를 현금성 자산으로 둡니다. 레버리지는 사용하지 않습니다.

DCA의 기본 비중과 매수량은 코드에 정의돼 있고, Guardian은 DCA 배수와 포트폴리오 상태를 `HOLD`, `DEFENSIVE`, `AGGRESSIVE` 중 하나로 판단합니다.

코드에는 단일 자산 비중, 최소 USDT 보유량, 한 사이클의 최대 변경 폭, 일일 거래 횟수, 드로다운 등에 대한 제한이 있습니다.

Gemini 호출에는 반복 횟수, 도구 호출 횟수, 비용과 실행 시간에 대한 상한도 설정돼 있습니다.

## 이전 세대에서 바뀐 점

앞선 HERMES 계열에서는 AI를 매매 판단에서 제거하고 규칙 기반 선물 전략을 운용했습니다. ATHENA에서는 시장 자체를 Bybit 선물에서 Bybit 현물로 바꾸고, AI의 역할도 개별 트레이드 결정자가 아니라 포트폴리오를 주기적으로 점검하는 Guardian으로 옮겼습니다.

KAIROS에서 정립한 전략 단순화와 버전 동결 같은 운영 원칙도 이어받았습니다.

## 한계

ATHENA의 성과를 확인할 백테스트 결과나 실전·페이퍼 성과 기록은 남아 있지 않습니다. 설계 문서에서는 AI 판단의 비결정성 때문에 전통적인 백테스트가 어렵다고 보고 forward test를 사용하도록 했습니다.

초기 설계 문서와 최종 실행 코드 사이에도 차이가 큽니다. 문서의 3-Agent 구조와 4시간 주기는 최종 코드에서 사용되지 않으며, 실제 구조는 단일 Guardian과 주간 점검입니다.

중단 이유를 직접 설명한 기록도 없습니다. 기존 README에는 운영 중지 상태라는 내용만 있고, 설계 문서에 적힌 폐기 조건 가운데 실제로 어떤 조건 때문에 멈췄는지는 확인할 수 없습니다.

세대의 시작 시점은 문서에서 2026년 4월 이후로 기록돼 있습니다.
