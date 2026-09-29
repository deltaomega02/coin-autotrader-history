# config/settings.py
# "OMNI Trading System 설정 - V14: 2-Target Scaling Out Strategy"

import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # =========================================================================
    # 🔑 API KEYS
    # =========================================================================
    UPBIT_ACCESS_KEY = os.getenv('UPBIT_ACCESS_KEY')
    UPBIT_SECRET_KEY = os.getenv('UPBIT_SECRET_KEY') 
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    
    # =========================================================================
    # 🤖 AI MODEL SETTINGS
    # =========================================================================
    # GPT-5 설정
    GPT_MODEL = 'gpt-5'
    GPT_TEMPERATURE = 0.3  # 자율 전략용 창의성
    
    # Gemini 2.5 Pro 설정
    GEMINI_MODEL = 'gemini-2.5-pro'
    GEMINI_TEMPERATURE = 0.3
    
    # =========================================================================
    # 📊 MARKET ANALYSIS (Phase 1)
    # =========================================================================
    # 분석 대상 코인 수
    TOP_COINS_COUNT = 20  # 상위 20개 코인만 분석
    
    # [제거됨] MIN_SIGNAL_SCORE - Gemini가 자율 판단
    # 이제 점수 기준 없이 AI가 순수 데이터로 판단합니다
    
    # 대기 시간 설정
    WAIT_TIME_SHORT = 30   # 30분 (활발한 시장)
    WAIT_TIME_MEDIUM = 60  # 60분 (일반)
    WAIT_TIME_LONG = 120   # 120분 (조용한 시장)
    
    # =========================================================================
    # 💰 GPT-5 AUTONOMOUS POSITION SIZING (Phase 3)
    # =========================================================================
    # GPT-5가 자율적으로 결정하는 포지션 범위
    MIN_POSITION_SIZE_PERCENT = 20  # 최소 20%
    MAX_POSITION_SIZE_PERCENT = 97  # 최대 97%
    
    # 변동성별 권장 포지션 (GPT-5 참고용)
    VOLATILITY_LOW_POSITION = 70    # 낮은 변동성: 70%
    VOLATILITY_MEDIUM_POSITION = 50 # 중간 변동성: 50%
    VOLATILITY_HIGH_POSITION = 30   # 높은 변동성: 30%
    VOLATILITY_EXTREME_POSITION = 20 # 극한 변동성: 20%
    
    # =========================================================================
    # 🎯 V14: 2-TARGET SCALING OUT STRATEGY
    # =========================================================================
    # 분할 익절 비율
    TARGET_SPLIT_RATIO = 0.7  # 1차 목표에서 70% 청산
    
    # Target 2 계산 배수 (GPT-5 참고용)
    TARGET_2_ATR_MULTIPLIER = 2.5  # T2 = Entry + (2.5 × ATR)
    
    # 최소 목표 간격
    MIN_TARGET_GAP_PERCENT = 2.0  # T2는 T1보다 최소 2% 높아야 함
    
    # =========================================================================
    # 🎯 TRADING PARAMETERS
    # =========================================================================
    # 진입 대기
    ENTRY_WAIT_TIMEOUT_HOURS = 1.0  # 1시간 타임아웃
    
    # 시스템 딜레이 고려
    SYSTEM_DELAY_SECONDS = 5  # 5-10초 딜레이
    ENTRY_PRICE_ADJUSTMENT = 0.002  # 0.2% 조정
    
    # =========================================================================
    # 📈 RISK MANAGEMENT
    # =========================================================================
    # 리스크/리워드 비율
    MIN_RISK_REWARD_RATIO = 1.5  # 최소 1:1.5
    
    # 손절 기준 (GPT-5 참고용)
    MAX_STOP_LOSS_PERCENT = 5.0  # 최대 -5%
    MIN_STOP_LOSS_PERCENT = 1.0  # 최소 -1%
    
    # V14: 본절(Breakeven) 보호
    BREAKEVEN_AFTER_TARGET_1 = True  # T1 도달 시 손절가를 진입가로 이동
    
    # =========================================================================
    # 💼 V14: PARTIAL SELL SETTINGS
    # =========================================================================
    # 업비트 최소 주문 금액
    MIN_ORDER_AMOUNT_KRW = 5000  # 5,000원 (업비트 제약)
    
    # 부분 매도 시 최소 금액 미달 처리
    AUTO_FULL_SELL_IF_BELOW_MIN = True  # 최소 금액 미달 시 전량 매도로 전환
    
    # =========================================================================
    # 📊 API RATE LIMITS
    # =========================================================================
    # Upbit API
    UPBIT_REQUESTS_PER_MINUTE = 90
    UPBIT_REQUESTS_PER_SECOND = 8
    
    # Gemini API
    GEMINI_REQUESTS_PER_MINUTE = 60
    
    # =========================================================================
    # 💾 DATA STORAGE
    # =========================================================================
    DB_PATH = 'logs/trade_history.db'
    
    # =========================================================================
    # 📊 LOGGING
    # =========================================================================
    DEBUG_MODE = False
    LOG_LEVEL = 'INFO'
    POSITION_SIZE_LOGGING = True
    
    # V14: 분할 익절 로깅
    LOG_TARGET_1_DETAILS = True  # T1 청산 상세 로그
    LOG_TARGET_2_DETAILS = True  # T2 청산 상세 로그
    LOG_BREAKEVEN_MOVE = True    # 본절 이동 로그
    
    # =========================================================================
    # ⚙️ SYSTEM BEHAVIOR
    # =========================================================================
    AUTO_RECOVER_ON_RESTART = True  # 재시작시 거래 복구
    
    # V14: Stage 복구 (재시작 시)
    RECOVER_PARTIAL_POSITIONS = True  # T1 후 재시작해도 T2 추격 계속

settings = Settings()