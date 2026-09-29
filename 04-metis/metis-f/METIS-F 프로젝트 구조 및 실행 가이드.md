# METIS-F 프로젝트 구조 및 실행 가이드

이 문서는 METIS-F 프로젝트의 폴더 구조와 실행/모니터링 명령어를 정리한 가이드입니다.

---

## 1. 디렉토리 구조 (Directory Structure)

```
~/metis-futures/
├── metis/                     # Python 가상환경 (Virtual Environment)
├── logs/                      # 로그 파일 저장소
│   ├── output.log             # 봇 실행 로그
│   └── dashboard.out          # 대시보드 실행 로그
├── .env                       # 환경 변수 및 API 키 설정 파일
├── requirements.txt           # 의존성 패키지 목록
├── main.py                    # 메인 실행 파일 (Entry Point)
├── dashboard_app.py           # Streamlit 대시보드 실행 파일
│
├── config/                    # 설정 관련 모듈
│   ├── __init__.py
│   ├── settings.py            # 일반 설정
│   └── logging_config.py      # 로깅 설정
│
├── core/                      # 핵심 로직 모듈
│   ├── __init__.py
│   ├── data_fetcher.py        # 데이터 수집
│   ├── technical_analysis.py  # 기술적 분석 (지표 계산)
│   ├── chart_generator.py     # 차트 생성
│   ├── leverage_calculator.py # 레버리지 계산 로직
│   ├── position_manager.py    # 포지션 진입/청산 관리
│   ├── websocket_watcher.py   # 실시간 데이터 감시
│   └── scheduler.py           # 주기적 작업 스케줄러
│
├── ai/                        # AI/LLM 관련 모듈
│   ├── __init__.py
│   ├── gemini_client.py       # Google Gemini API 클라이언트
│   └── prompts.py             # AI 프롬프트 템플릿
│
├── exchange/                  # 거래소 인터페이스
│   ├── __init__.py
│   ├── bybit_client.py        # Bybit API 클라이언트
│   └── bybit_websocket.py     # Bybit 웹소켓 연결
│
├── database/                  # 데이터베이스 관련
│   ├── __init__.py
│   ├── db_manager.py          # DB 연결 및 쿼리 관리
│   └── schema.sql             # DB 스키마 정의
│
└── utils/                     # 유틸리티
    ├── __init__.py
    └── telegram_bot.py        # 텔레그램 알림 봇
```

---

## 2. 실행 명령어 (Execution Commands)

터미널에서 아래 순서대로 명령어를 입력하여 봇과 대시보드를 실행합니다.

### 2-1. 프로젝트 이동 및 가상환경 활성화

```bash
# 프로젝트 폴더로 이동 후 가상환경 활성화
cd ~/metis-futures && source metis/bin/activate
```

### 2-2. 메인 봇 실행 (Background)

`nohup`을 사용하여 터미널이 종료되어도 백그라운드에서 계속 실행되도록 합니다.

```bash
# -u 옵션: Python 출력을 버퍼링 없이 즉시 기록하여 로그 실시간 확인 가능
cd ~/metis-futures && source metis/bin/activate
nohup streamlit run dashboard_app.py > ./logs/dashboard.out 2>&1 &
nohup python3 -u main.py > ./logs/output.log 2>&1 &
tail -f ./logs/output.log
```

### 2-3. 실행 상태 모니터링

로그 파일을 실시간으로 확인하여 정상 작동 여부를 체크합니다.

```bash
# 로그 실시간 확인 (모니터링 종료하려면 Ctrl+C)
tail -f ./logs/output.log
```

### 2-4. 대시보드 실행 (Streamlit)

대시보드 또한 백그라운드에서 실행하며 별도의 로그를 남깁니다.

```bash
nohup streamlit run dashboard_app.py > ./logs/dashboard.out 2>&1 &
```

---

## 3. 프로세스 관리

### 실행 중인 프로세스 확인

```bash
# python 및 streamlit 프로세스 확인
ps -ef | grep python
ps -ef | grep streamlit
```

### 프로세스 종료

```bash
# 봇 종료
pkill -f main.py

# 대시보드 종료
pkill -f streamlit
```

---

## 4. 빠른 참조 (Quick Reference)

| 작업 | 명령어 |
|------|--------|
| 가상환경 활성화 | `cd ~/metis-futures && source metis/bin/activate` |
| 봇 실행 | `nohup python3 -u main.py > ./logs/output.log 2>&1 &` |
| 봇 로그 확인 | `tail -f ./logs/output.log` |
| 대시보드 실행 | `nohup streamlit run dashboard_app.py > ./logs/dashboard.out 2>&1 &` |
| 봇 종료 | `pkill -f main.py` |
| 대시보드 종료 | `pkill -f streamlit` |