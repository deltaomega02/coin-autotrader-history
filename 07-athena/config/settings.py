"""ATHENA 설정.

운영자 운영 원칙:
- 손실 기반 시스템적 차단 X (단 DD -15% 셧다운은 안전)
- v# 변경 금지 (50거래까지 동결)
- 단순화 우선 (단 Agentic이라 도구는 풍부)
"""

import os
from dataclasses import dataclass, field
from typing import Tuple, Dict
from dotenv import load_dotenv

load_dotenv()

_USE_TESTNET = os.getenv("BYBIT_USE_TESTNET", "true").lower() == "true"
_PAPER_MODE = os.getenv("PAPER_MODE", "true").lower() == "true"


@dataclass(frozen=True)
class BybitConfig:
    """Bybit Spot REST + WebSocket."""
    API_KEY: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    SECRET: str = field(default_factory=lambda: os.getenv("BYBIT_SECRET", ""))
    USE_TESTNET: bool = _USE_TESTNET
    BASE_URL: str = "https://api-testnet.bybit.com" if _USE_TESTNET else "https://api.bybit.com"
    CATEGORY: str = "spot"


@dataclass(frozen=True)
class AthenaConfig:
    """ATHENA 운영 설정."""
    PAPER_MODE: bool = _PAPER_MODE

    # 자산 화이트리스트 (Manager가 결정 가능한 자산)
    ALLOWED_ASSETS: Tuple[str, ...] = ("BTC", "ETH", "SOL", "USDT")

    QUOTE_CURRENCY: str = "USDT"
    SYMBOLS: Dict[str, str] = None
    MIN_ORDER_QTYS: Dict[str, float] = None
    QTY_PRECISIONS: Dict[str, int] = None

    def __post_init__(self):
        object.__setattr__(self, 'SYMBOLS', {
            "BTC": "BTCUSDT",
            "ETH": "ETHUSDT",
            "SOL": "SOLUSDT",
        })
        object.__setattr__(self, 'MIN_ORDER_QTYS', {
            "BTC": 0.000048,
            "ETH": 0.0015,
            "SOL": 0.05,
        })
        object.__setattr__(self, 'QTY_PRECISIONS', {
            "BTC": 6,
            "ETH": 5,
            "SOL": 2,
        })


@dataclass(frozen=True)
class AgenticConfig:
    """Agentic AI 설정 (Gemini 3.1 Pro Function Calling).

    공식 문서 기준:
    - temperature 1.0 (기본, 변경 시 루핑 위험)
    - thinking_level "medium" (Pro 기본 high이지만 비용 절감)
    - automatic_function_calling 사용 (또는 manual loop)
    """
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))

    # Gemini 3.1 Pro (최신 플래그십)
    # 옵션: gemini-3.1-pro-preview-customtools (custom tool 우선)
    MODEL_ID: str = "gemini-3.1-pro-preview"

    # 추론 깊이
    THINKING_LEVEL: str = "medium"  # minimal/low/medium/high

    # 온도 (공식 권장: 1.0 유지)
    TEMPERATURE: float = 1.0

    # 출력 한도 (안전장치 + 비용 통제)
    MAX_OUTPUT_TOKENS: int = 4096

    # ────────────────────────────────────
    # Agentic Safety (무한 루프 방지)
    # ────────────────────────────────────

    # 최대 사이클당 turn 수 (모델 ↔ 도구 왕복)
    MAX_ITERATIONS: int = 8

    # 사이클당 도구 호출 총합
    MAX_TOOL_CALLS_PER_CYCLE: int = 18

    # 같은 도구 동일 인자 반복 차단
    MAX_SAME_TOOL_CALLS: int = 2

    # 사이클당 비용 한도 (USD)
    MAX_COST_PER_CYCLE_USD: float = 0.50

    # 사이클당 토큰 한도 (안전망)
    MAX_TOKENS_PER_CYCLE: int = 60_000

    # 사이클 timeout (초)
    CYCLE_TIMEOUT_SECONDS: int = 180

    # 도구 실행 timeout (초)
    TOOL_TIMEOUT_SECONDS: int = 20

    # API 재시도
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_SEC: int = 30

    # 결정 출력 검증
    MIN_CONFIDENCE_TO_ACT: int = 6

    # Gemini 가격 (검증된 2026-04 기준)
    INPUT_PRICE_PER_1M: float = 2.0      # $2 per 1M (≤200K context)
    OUTPUT_PRICE_PER_1M: float = 12.0    # $12 per 1M


@dataclass(frozen=True)
class TelegramConfig:
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    CHAT_ID: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))


@dataclass(frozen=True)
class SafetyConfig:
    """포트폴리오 Safety Layer (HERMES 학습 기반)."""

    # 비중 제약
    MAX_SINGLE_ASSET_WEIGHT: float = 0.80
    MIN_USDT_WEIGHT: float = 0.05
    MIN_REBALANCE_THRESHOLD: float = 0.005   # 0.5% 미만 무시
    MAX_TOTAL_CHANGE_PER_CYCLE: float = 0.40

    # 거래 한도
    MAX_TRADES_PER_DAY: int = 12

    # DD 셧다운
    MAX_DRAWDOWN_PCT: float = 0.15

    # 결정 안티패턴
    MAX_CONSECUTIVE_SAME_DECISION: int = 3

    # API 에러
    MAX_API_ERRORS_BEFORE_BACKOFF: int = 3
    BACKOFF_MINUTES: int = 60


@dataclass(frozen=True)
class DataSourcesConfig:
    """무료 데이터 소스."""

    COINALYZE_API_KEY: str = field(default_factory=lambda: os.getenv("COINALYZE_API_KEY", ""))
    COINALYZE_BASE: str = "https://api.coinalyze.net/v1"

    FG_API: str = "https://api.alternative.me/fng/"
    REDDIT_BASE: str = "https://www.reddit.com"
    DEFILLAMA_BASE: str = "https://api.llama.fi"
    BITBO_ETF_URL: str = "https://bitbo.io/treasuries/etf-flows/"

    # 거시 (yfinance Ticker IDs)
    DXY_TICKER: str = "DX-Y.NYB"
    SPX_TICKER: str = "^GSPC"
    GOLD_TICKER: str = "GC=F"


@dataclass(frozen=True)
class SchedulerConfig:
    """루프 주기."""
    OODA_INTERVAL_HOURS: int = 6   # 6시간 (Pro 비용 부담 ↓)

    LEARNING_INTERVAL_DAYS: int = 7
    LEARNING_DAY: str = "sunday"
    LEARNING_HOUR: int = 9

    DATA_FETCH_TIMEOUT_SEC: int = 30


# 모듈 로드 시 인스턴스
BYBIT = BybitConfig()
ATHENA = AthenaConfig()
AGENTIC = AgenticConfig()
TELEGRAM = TelegramConfig()
SAFETY = SafetyConfig()
DATA_SOURCES = DataSourcesConfig()
SCHEDULER = SchedulerConfig()
