## =============================================================================
    # Part 1: 초기화 및 설정관리
## =============================================================================
import os
import json
import time
import logging
import sqlite3
import pandas as pd
import pandas_ta as ta
import numpy as np
import re
from datetime import datetime, timedelta
import schedule
import pyupbit
from openai import OpenAI
from dotenv import load_dotenv
from threading import Lock
from enum import Enum
import asyncio
from typing import Dict, List, Optional, Tuple, Any

# 환경 변수 로드
load_dotenv()

class SystemState(Enum):
    """시스템 상태 열거형"""
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    TRADING = "TRADING"
    DEFENDING = "DEFENDING"

class ConfigurationManager:
    """설정 파일 관리자 클래스"""
    
    def __init__(self, config_path: str = 'config.json'):
        """
        설정 관리자 초기화
        
        Args:
            config_path (str): 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_configuration()
        
    def _load_configuration(self) -> Dict[str, Any]:
        """
        설정 파일 로드 또는 기본값 생성
        
        Returns:
            Dict[str, Any]: 설정 딕셔너리
        """
        default_config = {
            "api": {
                "request_delay": 0.5,
                "rate_limit_per_minute": 100,
                "timeout_seconds": 30
            },
            "trading": {
                "price_alert_threshold": 0.007,
                "volume_spike_threshold": 2.0,
                "emergency_cooldown_seconds": 180,
                "analysis_interval_seconds": 1800,
                "min_investment_krw": 10000,
                "max_position_ratio": 0.90
            },
            "wick_defense": {
                "enabled": True,
                "grace_period_seconds": 60,
                "confirmation_timeframe_minutes": 15,
                "activation_threshold_pct": 0.5
            },
            "database": {
                "path": "omni_xrp_v8_trades.sqlite",
                "backup_enabled": True,
                "backup_interval_hours": 24
            },
            "logging": {
                "level": "INFO",
                "file_path": "omni_xrp_v8.log",
                "max_file_size_mb": 50,
                "backup_count": 5
            },
            "ai": {
                "model": "gpt-4.1",
                "max_tokens": 2500,
                "temperature": 0.1,
                "timeout_seconds": 60
            },
            "learning": {
                "reflections_dir": "v8_reflections",
                "lessons_file": "lessons/lessons.md",
                "max_active_lessons": 10,
                "lesson_weight_decay": 0.95
            }
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 기본값과 병합
                    return self._merge_configs(default_config, loaded_config)
            except Exception as e:
                logging.warning(f"설정 파일 로드 실패, 기본값 사용: {e}")
                return default_config
        else:
            # 기본 설정 파일 생성
            self._save_configuration(default_config)
            return default_config
    
    def _merge_configs(self, default: Dict, loaded: Dict) -> Dict:
        """
        기본 설정과 로드된 설정 병합
        
        Args:
            default (Dict): 기본 설정
            loaded (Dict): 로드된 설정
            
        Returns:
            Dict: 병합된 설정
        """
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def _save_configuration(self, config: Dict[str, Any]) -> None:
        """
        설정을 파일로 저장
        
        Args:
            config (Dict[str, Any]): 저장할 설정
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"설정 파일 저장 실패: {e}")
    
    def get(self, key_path: str, default=None):
        """
        점 표기법으로 설정값 조회
        
        Args:
            key_path (str): 설정 키 경로 (예: "trading.price_alert_threshold")
            default: 기본값
            
        Returns:
            설정값 또는 기본값
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def update(self, key_path: str, value: Any) -> None:
        """
        설정값 업데이트 및 저장
        
        Args:
            key_path (str): 설정 키 경로
            value (Any): 새로운 값
        """
        keys = key_path.split('.')
        config_ref = self.config
        
        for key in keys[:-1]:
            if key not in config_ref:
                config_ref[key] = {}
            config_ref = config_ref[key]
        
        config_ref[keys[-1]] = value
        self._save_configuration(self.config)

class EnhancedLogger:
    """강화된 로깅 시스템"""
    
    def __init__(self, config_manager: ConfigurationManager):
        """
        로거 초기화
        
        Args:
            config_manager (ConfigurationManager): 설정 관리자
        """
        self.config = config_manager
        self._setup_logging()
        self.logger = logging.getLogger(__name__)
        
    def _setup_logging(self) -> None:
        """로깅 시스템 설정"""
        log_level = getattr(logging, self.config.get('logging.level', 'INFO'))
        log_file = self.config.get('logging.file_path', 'omni_xrp_v8.log')
        
        # 로깅 포맷 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        
        # 파일 핸들러
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        
        # 로거 설정
        logger = logging.getLogger()
        logger.setLevel(log_level)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    def log_with_context(self, level: str, message: str, **context) -> None:
        """
        컨텍스트 정보를 포함한 로깅
        
        Args:
            level (str): 로그 레벨
            message (str): 로그 메시지
            **context: 추가 컨텍스트 정보
        """
        context_str = " | ".join([f"{k}:{v}" for k, v in context.items()])
        full_message = f"{message} | {context_str}" if context else message
        
        getattr(self.logger, level.lower())(full_message)

def convert_numpy_types(obj):
    """
    NumPy 타입을 Python 기본 타입으로 변환
    
    Args:
        obj: 변환할 객체
        
    Returns:
        변환된 객체
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    else:
        return obj

class GlobalStateManager:
    """전역 상태 관리자"""
    
    def __init__(self):
        """상태 관리자 초기화"""
        self._state = SystemState.IDLE
        self._lock = Lock()
        self._context = {}
        
    def set_state(self, new_state: SystemState, context: Optional[Dict] = None) -> bool:
        """
        시스템 상태 변경
        
        Args:
            new_state (SystemState): 새로운 상태
            context (Optional[Dict]): 상태 컨텍스트
            
        Returns:
            bool: 상태 변경 성공 여부
        """
        with self._lock:
            if self._state == SystemState.IDLE or new_state == SystemState.IDLE:
                old_state = self._state
                self._state = new_state
                self._context = context or {}
                
                logging.info(f"시스템 상태 변경: {old_state.value} → {new_state.value}")
                if context:
                    logging.info(f"상태 컨텍스트: {context}")
                return True
            else:
                logging.warning(f"상태 변경 실패: 현재 {self._state.value}, 요청 {new_state.value}")
                return False
    
    def get_state(self) -> Tuple[SystemState, Dict]:
        """
        현재 상태 조회
        
        Returns:
            Tuple[SystemState, Dict]: 현재 상태와 컨텍스트
        """
        with self._lock:
            return self._state, self._context.copy()
    
    def is_idle(self) -> bool:
        """
        시스템이 IDLE 상태인지 확인
        
        Returns:
            bool: IDLE 상태 여부
        """
        with self._lock:
            return self._state == SystemState.IDLE
    
    def wait_for_idle(self, timeout: float = 30.0) -> bool:
        """
        시스템이 IDLE 상태가 될 때까지 대기
        
        Args:
            timeout (float): 최대 대기 시간(초)
            
        Returns:
            bool: IDLE 상태 달성 여부
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_idle():
                return True
            time.sleep(0.1)
        return False

class OMNIXRPSystemV8:
    """OMNI-XRP v8.0: 고도화된 확률론적 자동매매 시스템"""
    
    def __init__(self):
        """v8.0 시스템 초기화"""
        # 설정 및 로깅 초기화
        self.config_manager = ConfigurationManager()
        self.logger = EnhancedLogger(self.config_manager)
        self.state_manager = GlobalStateManager()
        
        # API 클라이언트 초기화
        self._initialize_api_clients()
        
        # 시스템 변수 초기화
        self._initialize_system_variables()
        
        # 데이터베이스 초기화
        self._initialize_database()
        
        # 학습 시스템 초기화
        self._initialize_learning_system()
        
        self.logger.log_with_context(
            'info', 
            'OMNI-XRP v8.0 시스템 초기화 완료',
            version='8.0',
            features='확률론적접근+XRP전문가+학습시스템+API최적화+위꼬리방어고도화'
        )
    
    def _initialize_api_clients(self) -> None:
        """API 클라이언트 초기화"""
        try:
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.upbit_client = pyupbit.Upbit(
                os.getenv("UPBIT_ACCESS_KEY"), 
                os.getenv("UPBIT_SECRET_KEY")
            )
            
            # API 호출 제한 관리
            self.api_call_tracker = {
                'last_call_time': 0,
                'calls_per_minute': 0,
                'minute_start': time.time()
            }
            
            self.logger.log_with_context('info', 'API 클라이언트 초기화 완료')
            
        except Exception as e:
            self.logger.log_with_context('error', f'API 클라이언트 초기화 실패: {e}')
            raise
    
    def _initialize_system_variables(self) -> None:
        """시스템 변수 초기화"""
        # 기본 설정값들
        self.db_path = self.config_manager.get('database.path')
        self.current_active_plan_id = None
        
        # 급변동 감지 관련
        self.price_alert_threshold = self.config_manager.get('trading.price_alert_threshold')
        self.volume_spike_threshold = self.config_manager.get('trading.volume_spike_threshold')
        self.emergency_cooldown = self.config_manager.get('trading.emergency_cooldown_seconds')
        self.last_emergency_time = None
        
        # 동적 분석 주기 관련
        self.current_analysis_interval = self.config_manager.get('trading.analysis_interval_seconds') // 60
        self.last_regime_check = None
        self.regime_change_cooldown = 300
        self.last_interval_change = None
        
        # 위꼬리 방어 관련
        self.wick_defense_enabled = self.config_manager.get('wick_defense.enabled')
        self.wick_defense_grace_period = self.config_manager.get('wick_defense.grace_period_seconds')
        self.wick_defense_timeframe = self.config_manager.get('wick_defense.confirmation_timeframe_minutes')
        
        # v8.0 새로운 변수들
        self.last_data_cache = None
        self.cache_timestamp = None
        self.cache_validity_seconds = 30
        
        self.logger.log_with_context('info', '시스템 변수 초기화 완료')
    
    def _initialize_learning_system(self) -> None:
        """학습 시스템 초기화"""
        self.reflections_dir = self.config_manager.get('learning.reflections_dir')
        self.lessons_file = self.config_manager.get('learning.lessons_file')
        
        # 디렉토리 생성
        os.makedirs(self.reflections_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.lessons_file), exist_ok=True)
        
        # 기본 교훈 파일 생성 (없는 경우)
        if not os.path.exists(self.lessons_file):
            self._create_initial_lessons_file()
        
        self.logger.log_with_context('info', '학습 시스템 초기화 완료')

## =============================================================================
    # Part 2: 데이터베이스 및 API 최적화
## =============================================================================

    def _initialize_database(self) -> None:
            """데이터베이스 초기화"""
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # v8.0 확장된 trades 테이블 생성
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS trades (
                            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            asset_ticker TEXT NOT NULL DEFAULT 'XRP',
                            status TEXT NOT NULL CHECK (status IN ('PLANNED', 'ACTIVE', 'COMPLETED', 'CANCELLED', 'SUPERSEDED')),
                            
                            -- 계획 단계 데이터
                            plan_timestamp TEXT NOT NULL,
                            planned_entry_price REAL NOT NULL,
                            planned_target_price REAL NOT NULL,
                            planned_stop_loss REAL NOT NULL,
                            entry_reason TEXT NOT NULL,
                            target_reason TEXT NOT NULL,
                            stop_loss_reason TEXT NOT NULL,
                            
                            -- v8.0 확률론적 접근 필드들
                            checklist_score REAL DEFAULT 0.0,
                            checklist_breakdown TEXT DEFAULT '',
                            signal_confidence_multiplier REAL DEFAULT 1.0,
                            calculated_position_ratio REAL DEFAULT 0.0,
                            change_trigger TEXT DEFAULT 'NONE',
                            trigger_evidence TEXT DEFAULT '',
                            
                            -- v8.0 XRP 전문가 필드들
                            wick_defense_active BOOLEAN DEFAULT FALSE,
                            wick_defense_result TEXT DEFAULT 'NONE',
                            energy_compression_detected BOOLEAN DEFAULT FALSE,
                            xrp_pattern_type TEXT DEFAULT 'NONE',
                            
                            -- 실행 단계 데이터
                            position_size_xrp REAL,
                            entry_timestamp TEXT,
                            actual_entry_price REAL,
                            exit_timestamp TEXT,
                            actual_exit_price REAL,
                            
                            -- 결과 단계 데이터
                            trade_result TEXT CHECK (trade_result IN ('PROFIT_TAKE', 'STOP_LOSS', 'MANUAL_EXIT', 'WICK_DEFENSE_SAVE', 'GRACE_PERIOD_SAVE')),
                            commission_krw REAL DEFAULT 0.0,
                            net_profit_krw REAL,
                            profit_rate_pct REAL,
                            
                            -- v8.0 새로운 추적 필드들
                            api_calls_used INTEGER DEFAULT 0,
                            analysis_duration_seconds REAL DEFAULT 0.0,
                            system_state_log TEXT DEFAULT '',
                            lessons_applied TEXT DEFAULT ''
                        )
                    ''')
                    
                    # v8.0 성능 추적 테이블 생성
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS system_performance (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            operation_type TEXT NOT NULL,
                            duration_seconds REAL NOT NULL,
                            api_calls_count INTEGER DEFAULT 0,
                            memory_usage_mb REAL DEFAULT 0.0,
                            cpu_usage_pct REAL DEFAULT 0.0,
                            success BOOLEAN DEFAULT TRUE,
                            error_message TEXT DEFAULT '',
                            context_data TEXT DEFAULT ''
                        )
                    ''')
                    
                    # v8.0 학습 데이터 테이블 생성
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS learning_data (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            trade_id INTEGER,
                            lesson_type TEXT NOT NULL,
                            lesson_content TEXT NOT NULL,
                            confidence_score REAL DEFAULT 0.0,
                            application_count INTEGER DEFAULT 0,
                            last_applied TEXT,
                            effectiveness_rating REAL DEFAULT 0.0,
                            created_timestamp TEXT NOT NULL,
                            FOREIGN KEY (trade_id) REFERENCES trades (trade_id)
                        )
                    ''')
                    
                    # 인덱스 생성
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(plan_timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON system_performance(timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_learning_trade_id ON learning_data(trade_id)')
                    
                    conn.commit()
                    
                self.logger.log_with_context('info', 'v8.0 강화된 데이터베이스 초기화 완료')
                
            except Exception as e:
                self.logger.log_with_context('error', f'데이터베이스 초기화 실패: {e}')
                raise

    def _create_initial_lessons_file(self) -> None:
        """초기 교훈 파일 생성"""
        initial_lessons = """# OMNI-XRP v8.0 학습된 거래 교훈

## 시스템 철학
확률론적 접근을 통한 지속적 학습과 개선

## 핵심 원칙

### 1. 진입 원칙
- 체크리스트 2.5점 미만 시 절대 진입 금지
- 신호 품질에 비례한 포지션 사이징
- BTC 급락(-3% 이상) 시 진입 금지

### 2. 관리 원칙
- 위꼬리 방어 시스템 적극 활용
- 트리거 기반 관리 변경
- 감정적 판단 금지

### 3. 매도 원칙
- 목표가 도달 시 즉시 매도
- 손절가 도달 시 위꼬리 방어 확인
- 분할 매도 지양, 명확한 매도

### 4. 리스크 원칙
- 최대 투자 비중 90% 초과 금지
- 급변동 상황에서 보수적 접근
- API 요청 제한 준수

### 5. 학습 원칙
- 모든 거래에서 교훈 추출
- 반복되는 실패 패턴 제거
- 성공 패턴 강화 및 재현

## 적용된 교훈 내역
(이 섹션은 시스템이 자동으로 업데이트합니다)

"""
        
        with open(self.lessons_file, 'w', encoding='utf-8') as f:
            f.write(initial_lessons)

    def _rate_limit_check(self) -> bool:
        """
        API 호출 제한 확인
        
        Returns:
            bool: 호출 가능 여부
        """
        current_time = time.time()
        
        # 1분이 지났으면 카운터 리셋
        if current_time - self.api_call_tracker['minute_start'] >= 60:
            self.api_call_tracker['calls_per_minute'] = 0
            self.api_call_tracker['minute_start'] = current_time
        
        # 분당 호출 제한 확인
        max_calls = self.config_manager.get('api.rate_limit_per_minute')
        if self.api_call_tracker['calls_per_minute'] >= max_calls:
            self.logger.log_with_context(
                'warning', 
                f'API 호출 제한 도달: {self.api_call_tracker["calls_per_minute"]}/{max_calls}'
            )
            return False
        
        # 최소 간격 확인
        min_delay = self.config_manager.get('api.request_delay')
        if current_time - self.api_call_tracker['last_call_time'] < min_delay:
            time.sleep(min_delay - (current_time - self.api_call_tracker['last_call_time']))
        
        return True

    def _api_call_wrapper(self, api_func, *args, **kwargs):
        """
        API 호출 래퍼 - 제한 확인 및 추적
        
        Args:
            api_func: 호출할 API 함수
            *args: 함수 인자
            **kwargs: 함수 키워드 인자
            
        Returns:
            API 호출 결과
        """
        if not self._rate_limit_check():
            self.logger.log_with_context('warning', 'API 호출 제한으로 인한 대기')
            time.sleep(1)
            return None
        
        try:
            start_time = time.time()
            result = api_func(*args, **kwargs)
            
            # 호출 추적 업데이트
            self.api_call_tracker['last_call_time'] = time.time()
            self.api_call_tracker['calls_per_minute'] += 1
            
            duration = time.time() - start_time
            self.logger.log_with_context(
                'debug', 
                f'API 호출 성공: {api_func.__name__}',
                duration=f'{duration:.2f}s',
                calls_this_minute=self.api_call_tracker['calls_per_minute']
            )
            
            return result
            
        except Exception as e:
            self.logger.log_with_context(
                'error', 
                f'API 호출 실패: {api_func.__name__}: {e}'
            )
            return None

    def get_optimized_market_data(self) -> Optional[Dict]:
        """
        v8.0 API 최적화된 시장 데이터 수집
        리샘플링을 통해 API 호출 80% 감소
        
        Returns:
            Optional[Dict]: 시장 데이터 또는 None
        """
        # 🔧 수정: ANALYZING 상태에서도 데이터 수집 허용
        current_state, _ = self.state_manager.get_state()
        if current_state in [SystemState.TRADING, SystemState.DEFENDING]:
            # TRADING, DEFENDING 중에만 데이터 수집 스킵
            self.logger.log_with_context(
                'debug', 
                f'시장 데이터 수집 스킵: 시스템 상태 {current_state.value}'
            )
            return None
        
        # IDLE, ANALYZING 상태에서는 데이터 수집 허용
        
        # 캐시 확인
        if self._is_cache_valid():
            self.logger.log_with_context('debug', '캐시된 시장 데이터 사용')
            return self.last_data_cache
        
        try:
            start_time = time.time()
            
            # 현재 시간 및 가격
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 호가 정보 (실시간 가격)
            orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
            if not orderbook:
                return None
            
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 잔고 정보
            balances = self._api_call_wrapper(self.upbit_client.get_balances)
            if not balances:
                return None
            
            xrp_balance = 0.0
            krw_balance = 0.0
            xrp_avg_buy_price = 0.0
            
            for balance in balances:
                if balance['currency'] == "XRP":
                    xrp_balance = float(balance['balance'])
                    xrp_avg_buy_price = float(balance['avg_buy_price'])
                elif balance['currency'] == "KRW":
                    krw_balance = float(balance['balance'])
            
            # v8.0 핵심: 5분봉 데이터만 한 번 호출 (960개 = 약 4일치)
            df_5m = self._api_call_wrapper(
                pyupbit.get_ohlcv, 
                "KRW-XRP", 
                interval="minute5", 
                count=960
            )
            
            if df_5m is None or len(df_5m) == 0:
                self.logger.log_with_context('error', '5분봉 데이터 조회 실패')
                return None
            
            # 리샘플링을 통한 다중 시간대 데이터 생성
            resampled_data = self._resample_timeframes(df_5m)
            
            # 포지션 상태 확인 
            position_status = self._check_current_position_status(
                xrp_balance, xrp_avg_buy_price
            )
            
            # XRP 전문가 분석
            xrp_expert_analysis = self._analyze_xrp_expert_patterns_v8(
                resampled_data, current_price
            )
            
            # 기술적 지표 계산
            technical_indicators = self._calculate_comprehensive_indicators_v8(
                resampled_data
            )
            
            # 시장 데이터 구성
            market_data = {
                'current_time': current_time,
                'current_price': current_price,
                'xrp_balance': xrp_balance,
                'krw_balance': krw_balance,
                'xrp_avg_buy_price': xrp_avg_buy_price,
                'position_status': position_status,
                'technical_indicators': technical_indicators,
                'xrp_expert_analysis': xrp_expert_analysis,
                'api_calls_used': 3,  # orderbook, balances, ohlcv
                'data_collection_duration': time.time() - start_time
            }
            
            # 캐시 업데이트
            self._update_cache(market_data)
            
            self.logger.log_with_context(
                'info',
                'v8.0 최적화된 시장 데이터 수집 완료',
                api_calls=3,
                duration=f'{market_data["data_collection_duration"]:.2f}s',
                current_price=f'{current_price:,.0f}원',
                system_state=current_state.value  # 현재 상태도 로그에 포함
            )
            
            return market_data
            
        except Exception as e:
            self.logger.log_with_context('error', f'시장 데이터 수집 중 오류: {e}')
            return None

    def _is_cache_valid(self) -> bool:
        """
        캐시 유효성 확인
        
        Returns:
            bool: 캐시 유효 여부
        """
        if not self.last_data_cache or not self.cache_timestamp:
            return False
        
        return (time.time() - self.cache_timestamp) < self.cache_validity_seconds

    def _update_cache(self, data: Dict) -> None:
        """
        데이터 캐시 업데이트
        
        Args:
            data (Dict): 캐시할 데이터
        """
        self.last_data_cache = data.copy()
        self.cache_timestamp = time.time()

    def _resample_timeframes(self, df_5m: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        5분봉 데이터를 다중 시간대로 리샘플링
        
        Args:
            df_5m (pd.DataFrame): 5분봉 데이터
            
        Returns:
            Dict[str, pd.DataFrame]: 시간대별 데이터
        """
        try:
            # 인덱스가 datetime이 아닌 경우 변환
            if not isinstance(df_5m.index, pd.DatetimeIndex):
                df_5m.index = pd.to_datetime(df_5m.index)
            
            resampled = {'5m': df_5m}
            
            # 15분봉 생성 (5분봉 3개 그룹화)
            df_15m = df_5m.resample('15T').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['15m'] = df_15m
            
            # 1시간봉 생성 (5분봉 12개 그룹화)
            df_1h = df_5m.resample('1H').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['1h'] = df_1h
            
            # 4시간봉 생성 (5분봉 48개 그룹화)
            df_4h = df_5m.resample('4H').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['4h'] = df_4h
            
            # 일봉 생성 (5분봉 288개 그룹화)
            df_day = df_5m.resample('1D').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['day'] = df_day
            
            self.logger.log_with_context(
                'debug',
                'v8.0 리샘플링 완료',
                timeframes=list(resampled.keys()),
                original_5m_count=len(df_5m),
                resampled_counts={tf: len(df) for tf, df in resampled.items()}
            )
            
            return resampled
            
        except Exception as e:
            self.logger.log_with_context('error', f'리샘플링 중 오류: {e}')
            return {'5m': df_5m}  # 실패 시 최소한 5분봉은 반환

    def _check_current_position_status(self, xrp_balance: float, avg_buy_price: float) -> Dict:
        """
        현재 포지션 상태 확인
        
        Args:
            xrp_balance (float): XRP 잔고
            avg_buy_price (float): 평균 매수가
            
        Returns:
            Dict: 포지션 상태 정보
        """
        try:
            # 실제 잔고 확인 (매개변수가 0일 때만)
            if xrp_balance == 0 and avg_buy_price == 0:
                balances = self._api_call_wrapper(self.upbit_client.get_balances)
                if balances:
                    for balance in balances:
                        if balance['currency'] == "XRP":
                            xrp_balance = float(balance['balance'])
                            avg_buy_price = float(balance['avg_buy_price'])
                        # KRW는 건드리지 않음
            
            # 활성 거래 확인
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT trade_id, actual_entry_price, planned_target_price, planned_stop_loss,
                        checklist_score, change_trigger, signal_confidence_multiplier,
                        wick_defense_active, xrp_pattern_type
                    FROM trades 
                    WHERE status = 'ACTIVE'
                    ORDER BY entry_timestamp DESC
                    LIMIT 1
                ''')
                active_trade = cursor.fetchone()
            
            has_position = xrp_balance > 0.0001  # 최소 보유량 기준
            has_active_trade = active_trade is not None
            
            return {
                'has_position': has_position,
                'xrp_balance': xrp_balance,
                'avg_buy_price': avg_buy_price,
                'has_active_trade': has_active_trade,
                'active_trade_info': active_trade
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'포지션 상태 확인 중 오류: {e}')
            return {
                'has_position': False, 
                'xrp_balance': 0, 
                'avg_buy_price': 0,
                'has_active_trade': False, 
                'active_trade_info': None
            }

## =============================================================================
    # Part 3: XRP 전문가 분석 및 기술적 지표
## =============================================================================

    def _analyze_xrp_expert_patterns_v8(self, resampled_data: Dict[str, pd.DataFrame], current_price: float) -> Dict:
            """
            v8.0 XRP 전문가 패턴 분석 (리샘플링된 데이터 사용)
            
            Args:
                resampled_data (Dict[str, pd.DataFrame]): 리샘플링된 시간대별 데이터
                current_price (float): 현재 가격
                
            Returns:
                Dict: XRP 전문가 분석 결과
            """
            try:
                self.logger.log_with_context('debug', 'XRP 전문가 패턴 분석 시작')
                
                analysis = {
                    'energy_compression_detected': False,
                    'compression_strength': 0,
                    'wick_pattern_risk': 'low',
                    'breakout_probability': 0,
                    'dominant_pattern': 'NONE',
                    'expert_confidence': 0,
                    'volume_acceleration': 0,
                    'price_momentum_divergence': False
                }
                
                # 일봉 데이터로 에너지 응축 패턴 감지
                df_day = resampled_data.get('day')
                if df_day is not None and len(df_day) >= 20:
                    analysis.update(self._detect_energy_compression(df_day, current_price))
                
                # 다중 시간대 위꼬리 패턴 분석
                for timeframe in ['15m', '1h', '4h']:
                    df = resampled_data.get(timeframe)
                    if df is not None and len(df) >= 10:
                        wick_risk = self._analyze_wick_patterns(df, timeframe)
                        if wick_risk > analysis['wick_pattern_risk']:
                            analysis['wick_pattern_risk'] = wick_risk
                
                # 거래량 가속도 분석
                df_1h = resampled_data.get('1h')
                if df_1h is not None and len(df_1h) >= 24:
                    analysis['volume_acceleration'] = self._calculate_volume_acceleration(df_1h)
                
                # 가격-모멘텀 다이버전스 감지
                df_4h = resampled_data.get('4h')
                if df_4h is not None and len(df_4h) >= 20:
                    analysis['price_momentum_divergence'] = self._detect_price_momentum_divergence(df_4h)
                
                # 종합 신뢰도 계산
                analysis['expert_confidence'] = self._calculate_expert_confidence_v8(analysis)
                
                # 지배적 패턴 결정
                analysis['dominant_pattern'] = self._determine_dominant_pattern_v8(analysis)
                
                self.logger.log_with_context(
                    'info',
                    'XRP 전문가 분석 완료',
                    pattern=analysis['dominant_pattern'],
                    confidence=f"{analysis['expert_confidence']}/5",
                    energy_compression=analysis['energy_compression_detected']
                )
                
                return analysis
                
            except Exception as e:
                self.logger.log_with_context('error', f'XRP 전문가 분석 중 오류: {e}')
                return {
                    'energy_compression_detected': False,
                    'compression_strength': 0,
                    'wick_pattern_risk': 'unknown',
                    'breakout_probability': 0,
                    'dominant_pattern': 'ANALYSIS_FAILED',
                    'expert_confidence': 0
                }

    def _detect_energy_compression(self, df_day: pd.DataFrame, current_price: float) -> Dict:
        """
        에너지 응축 패턴 감지
        
        Args:
            df_day (pd.DataFrame): 일봉 데이터
            current_price (float): 현재 가격
            
        Returns:
            Dict: 에너지 응축 분석 결과
        """
        try:
            result = {
                'energy_compression_detected': False,
                'compression_strength': 0,
                'breakout_probability': 0
            }
            
            # 볼린저 밴드 폭 계산
            bbands = ta.bbands(df_day['close'], length=20, std=2)
            if bbands is None or len(bbands) < 20:
                return result
            
            current_width = (bbands['BBU_20_2.0'].iloc[-1] - bbands['BBL_20_2.0'].iloc[-1])
            historical_widths = bbands['BBU_20_2.0'] - bbands['BBL_20_2.0']
            avg_width = historical_widths.tail(50).mean()
            
            if avg_width <= 0:
                return result
            
            compression_ratio = current_width / avg_width
            compression_threshold = 0.7  # 설정값에서 가져올 수 있음
            
            if compression_ratio < compression_threshold:
                result['energy_compression_detected'] = True
                result['compression_strength'] = round(1 - compression_ratio, 3)
                
                # 거래량 확인으로 돌파 확률 계산
                volume_day = df_day['volume'].iloc[-1]
                volume_avg = df_day['volume'].tail(20).mean()
                volume_ratio = volume_day / volume_avg if volume_avg > 0 else 1
                
                # 돌파 확률 = 압축 강도 * 거래량 비율 * 조정 계수
                base_probability = (1 - compression_ratio) * min(volume_ratio, 3.0) * 0.3
                result['breakout_probability'] = min(0.95, base_probability)
                
                self.logger.log_with_context(
                    'info',
                    'v8.0 에너지 응축 감지',
                    compression_ratio=f'{compression_ratio:.3f}',
                    volume_ratio=f'{volume_ratio:.1f}',
                    breakout_prob=f'{result["breakout_probability"]:.2f}'
                )
            
            return result
            
        except Exception as e:
            self.logger.log_with_context('error', f'에너지 응축 감지 중 오류: {e}')
            return {'energy_compression_detected': False, 'compression_strength': 0, 'breakout_probability': 0}

    def _analyze_wick_patterns(self, df: pd.DataFrame, timeframe: str) -> str:
        """
        위꼬리/아래꼬리 패턴 위험도 분석
        
        Args:
            df (pd.DataFrame): 가격 데이터
            timeframe (str): 시간프레임
            
        Returns:
            str: 위험도 ('low', 'medium', 'high')
        """
        try:
            recent_candles = df.tail(10)
            wick_score = 0
            
            for _, candle in recent_candles.iterrows():
                body_size = abs(candle['close'] - candle['open'])
                upper_wick = candle['high'] - max(candle['close'], candle['open'])
                lower_wick = min(candle['close'], candle['open']) - candle['low']
                
                if body_size > 0:
                    upper_wick_ratio = upper_wick / body_size
                    lower_wick_ratio = lower_wick / body_size
                    
                    # 위꼬리/아래꼬리가 몸통의 2배 이상인 경우
                    if upper_wick_ratio > 2 or lower_wick_ratio > 2:
                        wick_score += 1
                    # 극단적인 위꼬리 (몸통의 5배 이상)
                    elif upper_wick_ratio > 5 or lower_wick_ratio > 5:
                        wick_score += 2
            
            if wick_score >= 5:
                risk_level = 'high'
            elif wick_score >= 2:
                risk_level = 'medium'
            else:
                risk_level = 'low'
            
            self.logger.log_with_context(
                'debug',
                f'{timeframe} 위꼬리 분석',
                wick_score=wick_score,
                risk_level=risk_level
            )
            
            return risk_level
            
        except Exception as e:
            self.logger.log_with_context('error', f'위꼬리 패턴 분석 중 오류: {e}')
            return 'unknown'

    def _calculate_volume_acceleration(self, df_1h: pd.DataFrame) -> float:
        """
        거래량 가속도 계산
        
        Args:
            df_1h (pd.DataFrame): 1시간봉 데이터
            
        Returns:
            float: 거래량 가속도
        """
        try:
            if len(df_1h) < 24:
                return 0.0
            
            # 최근 6시간 vs 이전 18시간 평균 거래량 비교
            recent_6h_volume = df_1h['volume'].tail(6).mean()
            previous_18h_volume = df_1h['volume'].tail(24).head(18).mean()
            
            if previous_18h_volume > 0:
                acceleration = (recent_6h_volume / previous_18h_volume) - 1
                return round(acceleration, 3)
            
            return 0.0
            
        except Exception as e:
            self.logger.log_with_context('error', f'거래량 가속도 계산 중 오류: {e}')
            return 0.0

    def _detect_price_momentum_divergence(self, df_4h: pd.DataFrame) -> bool:
        """
        가격-모멘텀 다이버전스 감지
        
        Args:
            df_4h (pd.DataFrame): 4시간봉 데이터
            
        Returns:
            bool: 다이버전스 존재 여부
        """
        try:
            if len(df_4h) < 20:
                return False
            
            # RSI 계산
            rsi = ta.rsi(df_4h['close'], length=14)
            if rsi is None or len(rsi) < 10:
                return False
            
            # 최근 10개 봉에서 다이버전스 확인
            recent_prices = df_4h['close'].tail(10)
            recent_rsi = rsi.tail(10)
            
            # 가격 추세와 RSI 추세 비교
            price_trend = recent_prices.iloc[-1] - recent_prices.iloc[0]
            rsi_trend = recent_rsi.iloc[-1] - recent_rsi.iloc[0]
            
            # 반대 방향이면 다이버전스
            divergence_detected = (price_trend > 0 and rsi_trend < -5) or (price_trend < 0 and rsi_trend > 5)
            
            if divergence_detected:
                self.logger.log_with_context(
                    'info',
                    'v8.0 가격-모멘텀 다이버전스 감지',
                    price_trend=f'{price_trend:+.0f}',
                    rsi_trend=f'{rsi_trend:+.1f}'
                )
            
            return divergence_detected
            
        except Exception as e:
            self.logger.log_with_context('error', f'다이버전스 감지 중 오류: {e}')
            return False

    def _calculate_expert_confidence_v8(self, analysis: Dict) -> int:
        """
        v8.0 XRP 전문가 종합 신뢰도 계산
        
        Args:
            analysis (Dict): 분석 결과
            
        Returns:
            int: 신뢰도 (0-5)
        """
        try:
            confidence_score = 0
            
            # 에너지 응축 가점
            if analysis['energy_compression_detected']:
                confidence_score += 2
                if analysis['breakout_probability'] > 0.7:
                    confidence_score += 1
            
            # 위꼬리 위험도 반영
            wick_risk = analysis['wick_pattern_risk']
            if wick_risk == 'low':
                confidence_score += 1
            elif wick_risk == 'high':
                confidence_score -= 1
            
            # 거래량 가속도 반영
            volume_accel = analysis['volume_acceleration']
            if volume_accel > 0.5:  # 50% 이상 거래량 증가
                confidence_score += 1
            elif volume_accel < -0.3:  # 30% 이상 거래량 감소
                confidence_score -= 1
            
            # 다이버전스 반영
            if analysis['price_momentum_divergence']:
                confidence_score -= 1  # 다이버전스는 주의 신호
            
            return max(0, min(5, confidence_score))
            
        except Exception as e:
            self.logger.log_with_context('error', f'전문가 신뢰도 계산 중 오류: {e}')
            return 0

    def _determine_dominant_pattern_v8(self, analysis: Dict) -> str:
        """
        v8.0 지배적 패턴 결정
        
        Args:
            analysis (Dict): 분석 결과
            
        Returns:
            str: 지배적 패턴
        """
        try:
            if analysis['energy_compression_detected'] and analysis['breakout_probability'] > 0.8:
                return 'ENERGY_COMPRESSION_BREAKOUT_IMMINENT'
            elif analysis['energy_compression_detected']:
                return 'ENERGY_COMPRESSION_ACCUMULATION'
            elif analysis['wick_pattern_risk'] == 'high':
                return 'HIGH_VOLATILITY_WICK_PATTERN'
            elif analysis['volume_acceleration'] > 1.0:
                return 'VOLUME_ACCELERATION_PATTERN'
            elif analysis['price_momentum_divergence']:
                return 'MOMENTUM_DIVERGENCE_WARNING'
            elif analysis['expert_confidence'] >= 3:
                return 'MODERATE_BULLISH_PATTERN'
            else:
                return 'NEUTRAL_OBSERVATION'
                
        except Exception as e:
            self.logger.log_with_context('error', f'지배적 패턴 결정 중 오류: {e}')
            return 'PATTERN_ANALYSIS_ERROR'

    def _calculate_comprehensive_indicators_v8(self, resampled_data: Dict[str, pd.DataFrame]) -> Dict:
        """
        v8.0 포괄적 기술적 지표 계산 (리샘플링된 데이터 사용)
        
        Args:
            resampled_data (Dict[str, pd.DataFrame]): 리샘플링된 데이터
            
        Returns:
            Dict: 시간대별 기술적 지표
        """
        indicators = {}
        timeframes = ['5m', '15m', '1h', '4h', 'day']
        
        for tf in timeframes:
            df = resampled_data.get(tf)
            if df is None or len(df) < 60:  # 최소 60개 데이터 포인트 필요
                continue
                
            try:
                current_price = float(df['close'].iloc[-1])
                
                # A. 추세 지표군
                trend_indicators = self._calculate_trend_indicators(df, current_price)
                
                # B. 모멘텀 지표군
                momentum_indicators = self._calculate_momentum_indicators(df)
                
                # C. 변동성 지표군
                volatility_indicators = self._calculate_volatility_indicators(df, current_price)
                
                # D. 거래량 지표군
                volume_indicators = self._calculate_volume_indicators(df)
                
                # E. OHLC 데이터
                ohlc_data = {
                    'open': float(df['open'].iloc[-1]),
                    'high': float(df['high'].iloc[-1]),
                    'low': float(df['low'].iloc[-1]),
                    'close': current_price
                }
                
                indicators[tf] = {
                    'trend': trend_indicators,
                    'momentum': momentum_indicators,
                    'volatility': volatility_indicators,
                    'volume': volume_indicators,
                    'ohlc': ohlc_data
                }
                
            except Exception as e:
                self.logger.log_with_context('warning', f'{tf} 지표 계산 중 오류: {e}')
                # 실패 시 기본값 제공
                indicators[tf] = self._get_fallback_indicators_v8(current_price)
        
        return indicators

    def _calculate_trend_indicators(self, df: pd.DataFrame, current_price: float) -> Dict:
        """
        추세 지표군 계산
        
        Args:
            df (pd.DataFrame): 가격 데이터
            current_price (float): 현재 가격
            
        Returns:
            Dict: 추세 지표들
        """
        try:
            # 이동평균선들
            sma_20 = ta.sma(df['close'], length=20)
            sma_60 = ta.sma(df['close'], length=60)
            ema_12 = ta.ema(df['close'], length=12)
            ema_26 = ta.ema(df['close'], length=26)
            ema_60 = ta.ema(df['close'], length=60)
            
            # MACD
            macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
            
            # 추세 강도 계산
            trend_strength = self._calculate_trend_strength(
                current_price, sma_20, sma_60
            )
            
            # 골든크로스/데스크로스
            golden_cross, death_cross = self._detect_ma_crosses(sma_20, sma_60)
            
            return {
                'sma_20': self._safe_float(sma_20.iloc[-1], current_price),
                'sma_60': self._safe_float(sma_60.iloc[-1], current_price),
                'ema_12': self._safe_float(ema_12.iloc[-1], current_price),
                'ema_26': self._safe_float(ema_26.iloc[-1], current_price),
                'ema_60': self._safe_float(ema_60.iloc[-1], current_price),
                'trend_strength': int(trend_strength),
                'golden_cross': bool(golden_cross),
                'death_cross': bool(death_cross),
                'macd_line': self._safe_float(macd['MACD_12_26_9'].iloc[-1] if macd is not None else 0, 0),
                'macd_signal': self._safe_float(macd['MACDs_12_26_9'].iloc[-1] if macd is not None else 0, 0),
                'macd_histogram': self._safe_float(macd['MACDh_12_26_9'].iloc[-1] if macd is not None else 0, 0)
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'추세 지표 계산 중 오류: {e}')
            return self._get_default_trend_indicators(current_price)

    def _calculate_momentum_indicators(self, df: pd.DataFrame) -> Dict:
        """
        모멘텀 지표군 계산
        
        Args:
            df (pd.DataFrame): 가격 데이터
            
        Returns:
            Dict: 모멘텀 지표들
        """
        try:
            # RSI
            rsi_14 = ta.rsi(df['close'], length=14)
            
            # Stochastic
            stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3)
            
            # Williams %R
            willr = ta.willr(df['high'], df['low'], df['close'], length=14)
            
            # RSI 다이버전스
            rsi_divergence = self._detect_rsi_divergence_v8(df['close'], rsi_14)
            
            # CCI (Commodity Channel Index)
            cci = ta.cci(df['high'], df['low'], df['close'], length=20)
            
            return {
                'rsi': self._safe_float(rsi_14.iloc[-1], 50),
                'rsi_oversold': bool(self._safe_float(rsi_14.iloc[-1], 50) < 30),
                'rsi_overbought': bool(self._safe_float(rsi_14.iloc[-1], 50) > 70),
                'rsi_divergence': rsi_divergence,
                'stoch_k': self._safe_float(stoch['STOCHk_14_3_3'].iloc[-1] if stoch is not None else 50, 50),
                'stoch_d': self._safe_float(stoch['STOCHd_14_3_3'].iloc[-1] if stoch is not None else 50, 50),
                'willr': self._safe_float(willr.iloc[-1], -50),
                'cci': self._safe_float(cci.iloc[-1], 0)
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'모멘텀 지표 계산 중 오류: {e}')
            return self._get_default_momentum_indicators()

    def _calculate_volatility_indicators(self, df: pd.DataFrame, current_price: float) -> Dict:
            """
            변동성 지표군 계산
            
            Args:
                df (pd.DataFrame): 가격 데이터
                current_price (float): 현재 가격
                
            Returns:
                Dict: 변동성 지표들
            """
            try:
                # 볼린저 밴드
                bbands = ta.bbands(df['close'], length=20, std=2)
                
                # ATR (Average True Range)
                atr = ta.atr(df['high'], df['low'], df['close'], length=14)
                
                # 변동성 관련 계산
                bb_squeeze = self._detect_bb_squeeze_v8(bbands)
                bb_position = self._calculate_bb_position_v8(current_price, bbands)
                
                # Keltner Channels
                kc = ta.kc(df['high'], df['low'], df['close'], length=20)
                
                # Donchian Channels
                donchian = ta.donchian(df['high'], df['low'], length=20)
                
                return {
                    'bb_upper': self._safe_float(bbands['BBU_20_2.0'].iloc[-1] if bbands is not None else current_price * 1.02, current_price * 1.02),
                    'bb_middle': self._safe_float(bbands['BBM_20_2.0'].iloc[-1] if bbands is not None else current_price, current_price),
                    'bb_lower': self._safe_float(bbands['BBL_20_2.0'].iloc[-1] if bbands is not None else current_price * 0.98, current_price * 0.98),
                    'bb_position': float(bb_position),
                    'bb_squeeze': bool(bb_squeeze),
                    'atr': self._safe_float(atr.iloc[-1], 0),
                    'atr_ratio': float(self._safe_float(atr.iloc[-1], 0) / current_price * 100) if current_price > 0 else 0,
                    'kc_upper': self._safe_float(kc['KCUe_20_2'].iloc[-1] if kc is not None else current_price * 1.015, current_price * 1.015),
                    'kc_middle': self._safe_float(kc['KCBe_20_2'].iloc[-1] if kc is not None else current_price, current_price),
                    'kc_lower': self._safe_float(kc['KCLe_20_2'].iloc[-1] if kc is not None else current_price * 0.985, current_price * 0.985),
                    'donchian_upper': self._safe_float(donchian['DCU_20_20'].iloc[-1] if donchian is not None else current_price * 1.03, current_price * 1.03),
                    'donchian_lower': self._safe_float(donchian['DCL_20_20'].iloc[-1] if donchian is not None else current_price * 0.97, current_price * 0.97)
                }
                
            except Exception as e:
                self.logger.log_with_context('error', f'변동성 지표 계산 중 오류: {e}')
                return self._get_default_volatility_indicators(current_price)

    def _calculate_volume_indicators(self, df: pd.DataFrame) -> Dict:
        """
        거래량 지표군 계산
        
        Args:
            df (pd.DataFrame): 가격 데이터
            
        Returns:
            Dict: 거래량 지표들
        """
        try:
            # 거래량 이동평균
            volume_sma_20 = ta.sma(df['volume'], length=20)
            
            # 거래량 비율
            current_volume = df['volume'].iloc[-1]
            volume_ratio = 1.0
            if not pd.isna(volume_sma_20.iloc[-1]) and volume_sma_20.iloc[-1] > 0:
                volume_ratio = current_volume / volume_sma_20.iloc[-1]
            
            # OBV (On-Balance Volume)
            obv = ta.obv(df['close'], df['volume'])
            
            # VWAP (Volume Weighted Average Price)
            vwap = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
            
            # MFI (Money Flow Index)
            mfi = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)
            
            # A/D Line (Accumulation/Distribution Line)
            ad = ta.ad(df['high'], df['low'], df['close'], df['volume'])
            
            # Chaikin Money Flow
            cmf = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
            
            return {
                'current_volume': float(current_volume),
                'volume_sma_20': self._safe_float(volume_sma_20.iloc[-1], 0),
                'volume_ratio': float(volume_ratio),
                'volume_spike': bool(volume_ratio > 2.0),
                'volume_confirmation': bool(volume_ratio > 1.5),
                'obv': self._safe_float(obv.iloc[-1], 0),
                'vwap': self._safe_float(vwap.iloc[-1], df['close'].iloc[-1]),
                'mfi': self._safe_float(mfi.iloc[-1], 50),
                'ad_line': self._safe_float(ad.iloc[-1], 0),
                'cmf': self._safe_float(cmf.iloc[-1], 0)
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'거래량 지표 계산 중 오류: {e}')
            return self._get_default_volume_indicators(df['close'].iloc[-1])

    def _calculate_trend_strength(self, current_price: float, sma_20: pd.Series, sma_60: pd.Series) -> int:
        """
        추세 강도 계산
        
        Args:
            current_price (float): 현재 가격
            sma_20 (pd.Series): 20일 이동평균
            sma_60 (pd.Series): 60일 이동평균
            
        Returns:
            int: 추세 강도 (-3 ~ +3)
        """
        try:
            if pd.isna(sma_20.iloc[-1]) or pd.isna(sma_60.iloc[-1]):
                return 0
            
            sma_20_val = sma_20.iloc[-1]
            sma_60_val = sma_60.iloc[-1]
            
            # 기본 추세 방향
            if current_price > sma_20_val > sma_60_val:
                # 상승 추세
                strength_ratio = (current_price - sma_60_val) / sma_60_val
                if strength_ratio > 0.10:  # 10% 이상
                    return 3  # 매우 강한 상승
                elif strength_ratio > 0.05:  # 5% 이상
                    return 2  # 강한 상승
                else:
                    return 1  # 약한 상승
            elif current_price < sma_20_val < sma_60_val:
                # 하락 추세
                strength_ratio = (sma_60_val - current_price) / sma_60_val
                if strength_ratio > 0.10:  # 10% 이상
                    return -3  # 매우 강한 하락
                elif strength_ratio > 0.05:  # 5% 이상
                    return -2  # 강한 하락
                else:
                    return -1  # 약한 하락
            else:
                return 0  # 횡보
                
        except Exception as e:
            self.logger.log_with_context('error', f'추세 강도 계산 중 오류: {e}')
            return 0

    def _detect_ma_crosses(self, sma_20: pd.Series, sma_60: pd.Series) -> Tuple[bool, bool]:
        """
        이동평균선 교차 감지
        
        Args:
            sma_20 (pd.Series): 20일 이동평균
            sma_60 (pd.Series): 60일 이동평균
            
        Returns:
            Tuple[bool, bool]: (골든크로스 여부, 데스크로스 여부)
        """
        try:
            if len(sma_20) < 2 or len(sma_60) < 2:
                return False, False
            
            # 골든크로스: 단기선이 장기선을 상향 돌파
            golden_cross = (sma_20.iloc[-1] > sma_60.iloc[-1] and 
                           sma_20.iloc[-2] <= sma_60.iloc[-2])
            
            # 데스크로스: 단기선이 장기선을 하향 돌파
            death_cross = (sma_20.iloc[-1] < sma_60.iloc[-1] and 
                          sma_20.iloc[-2] >= sma_60.iloc[-2])
            
            return golden_cross, death_cross
            
        except Exception as e:
            self.logger.log_with_context('error', f'이동평균선 교차 감지 중 오류: {e}')
            return False, False

    def _detect_rsi_divergence_v8(self, price_series: pd.Series, rsi_series: pd.Series, lookback: int = 10) -> str:
        """
        v8.0 RSI 다이버전스 감지 (개선된 알고리즘)
        
        Args:
            price_series (pd.Series): 가격 시리즈
            rsi_series (pd.Series): RSI 시리즈
            lookback (int): 확인할 기간
            
        Returns:
            str: 다이버전스 타입 ('bullish', 'bearish', 'none')
        """
        try:
            if len(price_series) < lookback or len(rsi_series) < lookback:
                return "none"
            
            recent_prices = price_series.tail(lookback)
            recent_rsi = rsi_series.tail(lookback)
            
            # 가격과 RSI의 기울기 계산
            price_slope = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / len(recent_prices)
            rsi_slope = (recent_rsi.iloc[-1] - recent_rsi.iloc[0]) / len(recent_rsi)
            
            # 다이버전스 임계값
            price_threshold = abs(recent_prices.iloc[0] * 0.02)  # 2%
            rsi_threshold = 5  # RSI 5포인트
            
            # 상승 다이버전스: 가격은 하락하지만 RSI는 상승
            if (price_slope < -price_threshold and rsi_slope > rsi_threshold):
                return "bullish"
            
            # 하락 다이버전스: 가격은 상승하지만 RSI는 하락
            elif (price_slope > price_threshold and rsi_slope < -rsi_threshold):
                return "bearish"
            
            return "none"
            
        except Exception as e:
            self.logger.log_with_context('error', f'RSI 다이버전스 감지 중 오류: {e}')
            return "none"

    def _detect_bb_squeeze_v8(self, bbands: pd.DataFrame, threshold: float = 0.7) -> bool:
        """
        v8.0 볼린저 밴드 스퀴즈 감지 (개선된 알고리즘)
        
        Args:
            bbands (pd.DataFrame): 볼린저 밴드 데이터
            threshold (float): 스퀴즈 임계값
            
        Returns:
            bool: 스퀴즈 상태 여부
        """
        try:
            if bbands is None or len(bbands) < 20:
                return False
            
            current_width = (bbands['BBU_20_2.0'].iloc[-1] - bbands['BBL_20_2.0'].iloc[-1])
            
            # 최근 20일 평균 폭
            avg_width = ((bbands['BBU_20_2.0'] - bbands['BBL_20_2.0']).tail(20).mean())
            
            # 최근 50일 평균 폭 (장기 기준)
            long_avg_width = ((bbands['BBU_20_2.0'] - bbands['BBL_20_2.0']).tail(50).mean())
            
            # 스퀴즈 조건: 현재 폭이 단기 및 장기 평균보다 작음
            squeeze = (current_width < avg_width * threshold and 
                      current_width < long_avg_width * threshold)
            
            return squeeze
            
        except Exception as e:
            self.logger.log_with_context('error', f'볼린저 밴드 스퀴즈 감지 중 오류: {e}')
            return False

    def _calculate_bb_position_v8(self, current_price: float, bbands: pd.DataFrame) -> float:
        """
        v8.0 볼린저 밴드 내 현재가 위치 계산 (0~1)
        
        Args:
            current_price (float): 현재 가격
            bbands (pd.DataFrame): 볼린저 밴드 데이터
            
        Returns:
            float: 볼린저 밴드 내 위치 (0=하단, 1=상단)
        """
        try:
            if bbands is None or len(bbands) == 0:
                return 0.5
            
            bb_upper = bbands['BBU_20_2.0'].iloc[-1]
            bb_lower = bbands['BBL_20_2.0'].iloc[-1]
            
            if bb_upper == bb_lower:
                return 0.5
            
            position = (current_price - bb_lower) / (bb_upper - bb_lower)
            return max(0, min(1, position))
            
        except Exception as e:
            self.logger.log_with_context('error', f'볼린저 밴드 위치 계산 중 오류: {e}')
            return 0.5

    def _safe_float(self, value, default: float) -> float:
        """
        안전한 float 변환
        
        Args:
            value: 변환할 값
            default (float): 기본값
            
        Returns:
            float: 변환된 값 또는 기본값
        """
        try:
            if pd.isna(value) or value is None:
                return float(default)
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return float(default)

    def _get_fallback_indicators_v8(self, current_price: float) -> Dict:
        """
        v8.0 지표 계산 실패 시 기본값 반환
        
        Args:
            current_price (float): 현재 가격
            
        Returns:
            Dict: 기본 지표값들
        """
        return {
            'trend': self._get_default_trend_indicators(current_price),
            'momentum': self._get_default_momentum_indicators(),
            'volatility': self._get_default_volatility_indicators(current_price),
            'volume': self._get_default_volume_indicators(current_price),
            'ohlc': {
                'open': current_price,
                'high': current_price,
                'low': current_price,
                'close': current_price
            }
        }

    def _get_default_trend_indicators(self, current_price: float) -> Dict:
        """
        기본 추세 지표값 반환
        
        Args:
            current_price (float): 현재 가격
            
        Returns:
            Dict: 기본 추세 지표값들
        """
        return {
            'sma_20': current_price,
            'sma_60': current_price,
            'ema_12': current_price,
            'ema_26': current_price,
            'ema_60': current_price,
            'trend_strength': 0,
            'golden_cross': False,
            'death_cross': False,
            'macd_line': 0,
            'macd_signal': 0,
            'macd_histogram': 0
        }

    def _get_default_momentum_indicators(self) -> Dict:
        """
        기본 모멘텀 지표값 반환
        
        Returns:
            Dict: 기본 모멘텀 지표값들
        """
        return {
            'rsi': 50,
            'rsi_oversold': False,
            'rsi_overbought': False,
            'rsi_divergence': 'none',
            'stoch_k': 50,
            'stoch_d': 50,
            'willr': -50,
            'cci': 0
        }

    def _get_default_volatility_indicators(self, current_price: float) -> Dict:
        """
        기본 변동성 지표값 반환
        
        Args:
            current_price (float): 현재 가격
            
        Returns:
            Dict: 기본 변동성 지표값들
        """
        return {
            'bb_upper': current_price * 1.02,
            'bb_middle': current_price,
            'bb_lower': current_price * 0.98,
            'bb_position': 0.5,
            'bb_squeeze': False,
            'atr': 0,
            'atr_ratio': 0,
            'kc_upper': current_price * 1.015,
            'kc_middle': current_price,
            'kc_lower': current_price * 0.985,
            'donchian_upper': current_price * 1.03,
            'donchian_lower': current_price * 0.97
        }

    def _get_default_volume_indicators(self, current_price: float) -> Dict:
        """
        기본 거래량 지표값 반환
        
        Args:
            current_price (float): 현재 가격
            
        Returns:
            Dict: 기본 거래량 지표값들
        """
        return {
            'current_volume': 0,
            'volume_sma_20': 0,
            'volume_ratio': 1,
            'volume_spike': False,
            'volume_confirmation': False,
            'obv': 0,
            'vwap': current_price,
            'mfi': 50,
            'ad_line': 0,
            'cmf': 0
        }

    def validate_and_cleanup_existing_plans_v8(self) -> None:
        """
        v8.0 시스템 시작 시 실제 포지션에 맞춰 DB 상태를 검증 및 정리
        """
        try:
            self.logger.log_with_context('info', 'v8.0 시스템 시작 - DB 상태 검증 및 정리 작업 시작')
            
            # 상태 변경
            if not self.state_manager.set_state(SystemState.ANALYZING, {'operation': 'startup_validation'}):
                self.logger.log_with_context('warning', 'DB 검증을 위한 상태 변경 실패')
                return
            
            try:
                # 실제 잔고 확인
                balances = self._api_call_wrapper(self.upbit_client.get_balances)
                if balances:
                    xrp_balance = 0
                    for balance in balances:
                        if balance['currency'] == "XRP":
                            xrp_balance = float(balance['balance'])
                            break
                    
                    has_position = xrp_balance > 0.0001
                    
                    self.logger.log_with_context(
                        'info',
                        f'실제 XRP 보유 상태: {"보유 중" if has_position else "미보유"}',
                        xrp_balance=f'{xrp_balance:.4f}' if has_position else '0'
                    )
                    
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        
                        # 현재 DB 상태 조회
                        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'PLANNED'")
                        planned_count = cursor.fetchone()[0]
                        
                        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'ACTIVE'")
                        active_count = cursor.fetchone()[0]
                        
                        self.logger.log_with_context(
                            'info',
                            f'현재 DB 상태',
                            planned=f'{planned_count}개',
                            active=f'{active_count}개'
                        )
                        
                        if has_position:
                            # XRP 보유 중 - ACTIVE 거래는 유지, PLANNED 거래는 모두 취소
                            cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status = 'PLANNED'")
                            cancelled_planned = cursor.rowcount
                            
                            if cancelled_planned > 0:
                                self.logger.log_with_context('info', f'불필요한 PLANNED 거래 {cancelled_planned}개 정리 완료')
                            
                            # ACTIVE 거래 상태 확인 및 정리
                            if active_count == 0:
                                self.logger.log_with_context('warning', 'XRP 보유 중이지만 ACTIVE 거래가 없음 - 첫 전략 분석에서 처리 예정')
                            elif active_count > 1:
                                # 가장 최근 ACTIVE만 남기고 나머지는 SUPERSEDED로 변경
                                cursor.execute('''
                                    UPDATE trades 
                                    SET status = 'SUPERSEDED' 
                                    WHERE status = 'ACTIVE' 
                                    AND trade_id NOT IN (
                                        SELECT trade_id FROM trades 
                                        WHERE status = 'ACTIVE' 
                                        ORDER BY entry_timestamp DESC 
                                        LIMIT 1
                                    )
                                ''')
                                cleaned_count = cursor.rowcount
                                self.logger.log_with_context('info', f'중복 ACTIVE 거래 {cleaned_count}개를 SUPERSEDED로 정리')
                            else:
                                self.logger.log_with_context('info', 'ACTIVE 거래 상태 정상')
                        
                        else:
                            # XRP 미보유 - 모든 ACTIVE 및 PLANNED 거래 정리
                            cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status IN ('ACTIVE', 'PLANNED')")
                            cancelled_total = cursor.rowcount
                            
                            if cancelled_total > 0:
                                self.logger.log_with_context('info', f'유령 거래/계획 {cancelled_total}개 정리 완료')
                            else:
                                self.logger.log_with_context('info', '정리할 거래 없음 - 깨끗한 상태')
                        
                        conn.commit()
                        
                    self.logger.log_with_context('info', 'v8.0 DB 상태 검증 및 정리 완료. 시스템이 안전한 상태에서 시작됩니다.')
                
                else:
                    self.logger.log_with_context('error', '잔고 정보 조회 실패')
                    
            finally:
                # 상태를 IDLE로 복원
                self.state_manager.set_state(SystemState.IDLE)
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 시스템 시작 검증 중 치명적 오류: {e}')
            # 오류 발생 시 안전을 위해 모든 계획 비활성화
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status IN ('PLANNED', 'ACTIVE')")
                    conn.commit()
                self.logger.log_with_context('info', '오류 발생으로 인한 안전 조치: 모든 계획 비활성화')
            except Exception as cleanup_error:
                self.logger.log_with_context('error', f'안전 조치마저 실패: {cleanup_error}')
            finally:
                self.state_manager.set_state(SystemState.IDLE)

## =============================================================================
    # Part 4: 위꼬리 방어 시스템
## =============================================================================

    def monitor_active_trades_v8(self) -> None:
            """
            v8.0 활성 거래 모니터링 - 고도화된 위꼬리 방어 시스템
            """
            try:
                # 상태 확인 - DEFENDING 상태가 아닐 때만 실행
                current_state, _ = self.state_manager.get_state()
                if current_state == SystemState.DEFENDING:
                    return  # 위꼬리 방어 중이므로 모니터링 스킵
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # 최신 ACTIVE 거래 하나만 조회
                    cursor.execute('''
                        SELECT trade_id, planned_target_price, planned_stop_loss, 
                            position_size_xrp, actual_entry_price, wick_defense_active
                        FROM trades 
                        WHERE status = 'ACTIVE'
                        ORDER BY entry_timestamp DESC
                        LIMIT 1
                    ''')
                    
                    active_trade = cursor.fetchone()
                
                if not active_trade:
                    return
                
                # 현재 가격 확인
                orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
                if not orderbook:
                    return
                
                current_price = float(orderbook['orderbook_units'][0]['ask_price'])
                
                trade_id, target_price, stop_loss, position_size, entry_price, wick_defense_active = active_trade
                
                # 목표가 도달 - 즉시 매도
                if current_price >= target_price:
                    self.logger.log_with_context(
                        'info',
                        f'거래 ID {trade_id} 목표가 도달 - 매도 실행',
                        current_price=f'{current_price:,.0f}원',
                        target_price=f'{target_price:,.0f}원'
                    )
                    self._execute_sell_order_v8(trade_id, current_price, "PROFIT_TAKE")
                    return
                
                # 손절가 도달 - v8.0 고도화된 위꼬리 방어 적용
                if current_price <= stop_loss:
                    if wick_defense_active and self.wick_defense_enabled:
                        self.logger.log_with_context(
                            'info',
                            f'거래 ID {trade_id} 손절가 도달 - v8.0 고도화된 위꼬리 방어 시스템 활성화',
                            current_price=f'{current_price:,.0f}원',
                            stop_loss=f'{stop_loss:,.0f}원'
                        )
                        self._activate_enhanced_wick_defense_v8(trade_id, current_price, stop_loss)
                    else:
                        self.logger.log_with_context(
                            'info',
                            f'거래 ID {trade_id} 손절가 도달 - 즉시 매도 실행',
                            current_price=f'{current_price:,.0f}원',
                            stop_loss=f'{stop_loss:,.0f}원'
                        )
                        self._execute_sell_order_v8(trade_id, current_price, "STOP_LOSS")
                    return
                            
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 활성 거래 모니터링 중 오류: {e}')

    def _activate_enhanced_wick_defense_v8(self, trade_id: int, current_price: float, stop_loss: float) -> None:
        """
        v8.0 고도화된 위꼬리 방어 시스템
        60초 유예 기간 + 재확인 방식
        
        Args:
            trade_id (int): 거래 ID
            current_price (float): 현재 가격
            stop_loss (float): 손절가
        """
        try:
            # 상태를 DEFENDING으로 변경
            context = {
                'trade_id': trade_id,
                'trigger_price': current_price,
                'stop_loss': stop_loss,
                'defense_start_time': time.time()
            }
            
            if not self.state_manager.set_state(SystemState.DEFENDING, context):
                self.logger.log_with_context('error', 'v8.0 위꼬리 방어 상태 변경 실패 - 즉시 매도')
                self._execute_sell_order_v8(trade_id, current_price, "STOP_LOSS")
                return
            
            self.logger.log_with_context(
                'info',
                'v8.0 고도화된 위꼬리 방어 시스템 활성화',
                grace_period=f'{self.wick_defense_grace_period}초',
                trade_id=trade_id
            )
            
            # 위꼬리 방어 상태를 DB에 기록
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE trades SET 
                        stop_loss_reason = stop_loss_reason || ' [v8.0 위꼬리방어 활성화: ' || ? || '초 유예]',
                        wick_defense_result = 'DEFENDING'
                    WHERE trade_id = ?
                ''', (self.wick_defense_grace_period, trade_id))
                conn.commit()
            
            # 60초 후 재확인 스케줄 등록
            defense_job_tag = f'wick_defense_v8_{trade_id}'
            schedule.every(self.wick_defense_grace_period).seconds.do(
                self._execute_enhanced_wick_defense_check_v8, 
                trade_id, 
                stop_loss, 
                current_price
            ).tag(defense_job_tag)
            
            self.logger.log_with_context(
                'info',
                'v8.0 고도화된 위꼬리 방어 스케줄 등록 완료',
                tag=defense_job_tag,
                check_time=f'{self.wick_defense_grace_period}초 후'
            )
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 위꼬리 방어 활성화 중 오류: {e}')
            # 오류 시 즉시 매도 및 상태 복원
            self.state_manager.set_state(SystemState.IDLE)
            self._execute_sell_order_v8(trade_id, current_price, "STOP_LOSS")

    def _execute_enhanced_wick_defense_check_v8(self, trade_id: int, original_stop_loss: float, trigger_price: float) -> None:
        """
        v8.0 고도화된 위꼬리 방어: 60초 후 재확인 로직
        
        Args:
            trade_id (int): 거래 ID
            original_stop_loss (float): 원래 손절가
            trigger_price (float): 방어 발동 당시 가격
        """
        try:
            self.logger.log_with_context(
                'info',
                f'v8.0 고도화된 위꼬리 방어 재확인 시작',
                trade_id=trade_id,
                grace_period_end=f'{self.wick_defense_grace_period}초 경과'
            )
            
            # 현재 가격 확인
            orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
            if not orderbook:
                self.logger.log_with_context('error', 'v8.0 위꼬리 방어: 현재 가격 조회 실패 - 안전을 위해 매도')
                self._finalize_wick_defense_v8(trade_id, trigger_price, "PRICE_CHECK_FAILED", False)
                return
            
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            self.logger.log_with_context(
                'info',
                'v8.0 위꼬리 방어 재확인 가격 정보',
                current_price=f'{current_price:,.0f}원',
                stop_loss=f'{original_stop_loss:,.0f}원',
                trigger_price=f'{trigger_price:,.0f}원'
            )
            
            # 방어 성공/실패 판정
            if current_price <= original_stop_loss:
                # 방어 실패: 여전히 손절가 아래
                price_change_pct = ((current_price - trigger_price) / trigger_price * 100)
                
                self.logger.log_with_context(
                    'info',
                    'v8.0 위꼬리 방어 실패 - 실제 하락 추세로 판단',
                    current_price=f'{current_price:,.0f}원',
                    price_change=f'{price_change_pct:+.2f}%',
                    action='즉시 매도'
                )
                
                self._finalize_wick_defense_v8(trade_id, current_price, "DEFENSE_FAILED", False)
                
            else:
                # 방어 성공: 손절가 위로 회복
                recovery_pct = ((current_price - original_stop_loss) / original_stop_loss * 100)
                
                self.logger.log_with_context(
                    'info',
                    'v8.0 위꼬리 방어 성공! 위꼬리 패턴으로 확인',
                    current_price=f'{current_price:,.0f}원',
                    recovery=f'{recovery_pct:+.2f}%',
                    action='포지션 유지'
                )
                
                self._finalize_wick_defense_v8(trade_id, current_price, "DEFENSE_SUCCESS", True)
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 위꼬리 방어 재확인 중 오류: {e}')
            # 오류 시 안전을 위해 매도
            self._finalize_wick_defense_v8(trade_id, trigger_price, "RECHECK_ERROR", False)

    def _finalize_wick_defense_v8(self, trade_id: int, final_price: float, result_reason: str, defense_success: bool) -> None:
        """
        v8.0 위꼬리 방어 최종 처리 및 정리
        
        Args:
            trade_id (int): 거래 ID
            final_price (float): 최종 처리 가격
            result_reason (str): 처리 사유
            defense_success (bool): 방어 성공 여부
        """
        try:
            # 스케줄 정리
            defense_job_tag = f'wick_defense_v8_{trade_id}'
            cleared_jobs = schedule.clear(defense_job_tag)
            
            if cleared_jobs:
                self.logger.log_with_context('info', f'v8.0 위꼬리 방어 스케줄 정리 완료: {cleared_jobs}개')
            
            # DB 업데이트
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if defense_success:
                    # 방어 성공 - 포지션 유지
                    cursor.execute('''
                        UPDATE trades SET 
                            stop_loss_reason = stop_loss_reason || ' [v8.0 위꼬리방어 성공: ' || ? || ' - ' || ? || '원으로 회복]',
                            wick_defense_result = 'SUCCESS'
                        WHERE trade_id = ?
                    ''', (result_reason, int(final_price), trade_id))
                    
                    self.logger.log_with_context(
                        'info',
                        'v8.0 위꼬리 방어 성공 - 포지션 유지',
                        trade_id=trade_id,
                        final_price=f'{final_price:,.0f}원'
                    )
                    
                else:
                    # 방어 실패 - 매도 실행
                    cursor.execute('''
                        UPDATE trades SET 
                            stop_loss_reason = stop_loss_reason || ' [v8.0 위꼬리방어 실패: ' || ? || ']',
                            wick_defense_result = 'FAILED'
                        WHERE trade_id = ?
                    ''', (result_reason, trade_id))
                    
                    self.logger.log_with_context(
                        'info',
                        'v8.0 위꼬리 방어 실패 - 매도 실행',
                        trade_id=trade_id,
                        reason=result_reason
                    )
                    
                    # 매도 실행
                    self._execute_sell_order_v8(trade_id, final_price, "STOP_LOSS")
                
                conn.commit()
            
            # 상태를 IDLE로 복원 (매도가 실행되지 않은 경우에만)
            if defense_success:
                self.state_manager.set_state(SystemState.IDLE)
                self.logger.log_with_context('info', 'v8.0 위꼬리 방어 완료 - 시스템 정상 상태 복원')
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 위꼬리 방어 최종 처리 중 오류: {e}')
            # 오류 시 강제로 상태 복원
            self.state_manager.set_state(SystemState.IDLE)

    def _execute_sell_order_v8(self, trade_id: int, current_price: float, trade_result: str) -> bool:
        """
        v8.0 매도 주문 실행 - 상태 관리 및 성능 추적 포함
        
        Args:
            trade_id (int): 거래 ID
            current_price (float): 현재 가격
            trade_result (str): 거래 결과 타입
            
        Returns:
            bool: 매도 성공 여부
        """
        try:
            # 상태를 TRADING으로 변경
            context = {
                'operation': 'sell_order',
                'trade_id': trade_id,
                'expected_price': current_price
            }
            
            if not self.state_manager.set_state(SystemState.TRADING, context):
                self.logger.log_with_context('error', 'v8.0 매도를 위한 상태 변경 실패')
                return False
            
            start_time = time.time()
            
            self.logger.log_with_context(
                'info',
                'v8.0 매도 주문 실행 시작',
                trade_id=trade_id,
                price=f'{current_price:,.0f}원',
                result_type=trade_result
            )
            
            # XRP 잔고 확인
            xrp_balance = self._api_call_wrapper(self.upbit_client.get_balance, "XRP")
            if xrp_balance is None:
                self.logger.log_with_context('error', 'XRP 잔고 조회 실패')
                return False
            
            if xrp_balance < 0.0001:
                self.logger.log_with_context('warning', '매도할 XRP가 부족합니다')
                return False
            
            # 시장가 매도 주문 실행
            order_result = self._api_call_wrapper(
                self.upbit_client.sell_market_order, 
                "KRW-XRP", 
                xrp_balance
            )
            
            if not order_result or 'uuid' not in order_result:
                self.logger.log_with_context('error', 'v8.0 매도 주문 실패')
                return False
            
            # 주문 완료 대기
            time.sleep(3)
            
            # 실제 매도 체결 정보 가져오기
            order_details = self._api_call_wrapper(self.upbit_client.get_order, order_result['uuid'])
            
            if not order_details:
                self.logger.log_with_context('error', 'v8.0 매도 주문 상세 정보 조회 실패')
                return False
            
            # 실제 매도 정보 추출 및 DB 업데이트
            success = self._process_sell_order_result_v8(
                trade_id, order_details, trade_result, start_time
            )
            
            if success:
                # 거래 완료 즉시 회고 실행
                self.logger.log_with_context('info', 'v8.0 거래 완료 - 즉시 회고 분석 시작')
                self._perform_immediate_reflection_v8(trade_id)
                
                # 매도 완료 후 즉시 분석 예약
                self.logger.log_with_context('info', 'v8.0 매도 완료 - 10초 후 즉시 새로운 매수 기회 분석 예약')
                schedule.every(10).seconds.do(self.run_strategy_analysis_v8).tag('immediate_analysis')
                
                # 주기 재평가 쿨다운 리셋
                self.last_regime_check = None
                
            return success
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 매도 주문 실행 중 오류: {e}')
            return False
        
        finally:
            # 상태를 IDLE로 복원
            self.state_manager.set_state(SystemState.IDLE)

    def _execute_buy_order_v8(self, trade_id: int, planned_entry_price: float) -> bool:
            """
            v8.0 매수 주문 실행 - 상태 관리 및 성능 추적 포함
            
            Args:
                trade_id (int): 거래 ID
                planned_entry_price (float): 계획된 진입가
                
            Returns:
                bool: 매수 성공 여부
            """
            try:
                # 상태를 TRADING으로 변경
                context = {
                    'operation': 'buy_order',
                    'trade_id': trade_id,
                    'expected_price': planned_entry_price
                }
                
                if not self.state_manager.set_state(SystemState.TRADING, context):
                    self.logger.log_with_context('error', 'v8.0 매수를 위한 상태 변경 실패')
                    return False
                
                start_time = time.time()
                
                self.logger.log_with_context(
                    'info',
                    'v8.0 매수 주문 실행 시작',
                    trade_id=trade_id,
                    planned_price=f'{planned_entry_price:,.0f}원'
                )
                
                # 현재 KRW 잔고 확인
                krw_balance = self._api_call_wrapper(self.upbit_client.get_balance, "KRW")
                if krw_balance is None:
                    self.logger.log_with_context('error', 'KRW 잔고 조회 실패')
                    return False
                
                # 거래 계획에서 투자 금액 확인
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT calculated_position_ratio FROM trades 
                        WHERE trade_id = ? AND status = 'PLANNED'
                    ''', (trade_id,))
                    
                    result = cursor.fetchone()
                    if not result:
                        self.logger.log_with_context('error', 'v8.0 매수 계획을 찾을 수 없습니다')
                        return False
                    
                    position_ratio = result[0]
                
                # 실제 투자 금액 계산
                invest_amount = krw_balance * position_ratio
                min_investment = self.config_manager.get('trading.min_investment_krw')
                
                if invest_amount < min_investment:
                    self.logger.log_with_context(
                        'error', 
                        f'v8.0 투자 가능 금액 부족: {invest_amount:,.0f}원 < {min_investment:,.0f}원'
                    )
                    return False
                
                # 시장가 매수 주문 실행
                order_result = self._api_call_wrapper(
                    self.upbit_client.buy_market_order, 
                    "KRW-XRP", 
                    invest_amount
                )
                
                if not order_result or 'uuid' not in order_result:
                    self.logger.log_with_context('error', 'v8.0 매수 주문 실패')
                    return False
                
                # 주문 완료 대기
                time.sleep(3)
                
                # 실제 매수 체결 정보 가져오기
                order_details = self._api_call_wrapper(self.upbit_client.get_order, order_result['uuid'])
                
                if not order_details:
                    self.logger.log_with_context('error', 'v8.0 매수 주문 상세 정보 조회 실패')
                    return False
                
                # 실제 매수 정보 추출 및 DB 업데이트
                success = self._process_buy_order_result_v8(
                    trade_id, order_details, start_time
                )
                
                if success:
                    self.logger.log_with_context('info', 'v8.0 매수 완료 - 활성 거래로 전환')
                    
                    # 매수 완료 후 위꼬리 방어 시스템 준비
                    self.current_active_plan_id = trade_id
                    
                    # 주기 재평가 쿨다운 리셋
                    self.last_regime_check = None
                    
                return success
                
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 매수 주문 실행 중 오류: {e}')
                return False
            
            finally:
                # 상태를 IDLE로 복원
                self.state_manager.set_state(SystemState.IDLE)

    def _process_sell_order_result_v8(self, trade_id: int, order_details: Dict, trade_result: str, start_time: float) -> bool:
        """
        v8.0 매도 주문 결과 처리 - 정확한 수익률 계산 및 성능 추적
        
        Args:
            trade_id (int): 거래 ID
            order_details (Dict): 주문 상세 정보
            trade_result (str): 거래 결과
            start_time (float): 매도 시작 시간
            
        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 실제 체결 정보 추출
            executed_volume = float(order_details.get('executed_volume', 0))
            paid_fee = float(order_details.get('paid_fee', 0))
            
            if executed_volume <= 0:
                self.logger.log_with_context('error', 'v8.0 체결된 물량이 없습니다')
                return False
            
            # 실제 매도 단가 계산
            total_received = 0
            trades = order_details.get('trades', [])
            
            if trades:
                total_received = sum(float(trade['price']) * float(trade['volume']) for trade in trades)
                actual_exit_price = total_received / executed_volume
            else:
                total_received = float(order_details.get('price', 0)) * executed_volume
                actual_exit_price = float(order_details.get('price', 0))
            
            net_received = total_received - paid_fee
            exit_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 기존 거래 정보 조회 및 수익률 계산
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT position_size_xrp, actual_entry_price, commission_krw, 
                           wick_defense_active, wick_defense_result, 
                           checklist_score, signal_confidence_multiplier
                    FROM trades WHERE trade_id = ?
                ''', (trade_id,))
                
                row = cursor.fetchone()
                if not row:
                    self.logger.log_with_context('error', 'v8.0 기존 거래 정보를 찾을 수 없습니다')
                    return False
                
                (original_position, entry_price, buy_commission, wick_defense_was_active, 
                 wick_defense_result, checklist_score, signal_multiplier) = row
                
                # 정확한 수익률 계산
                total_buy_cost = (entry_price * original_position) + buy_commission
                total_sell_received = net_received
                net_profit = total_sell_received - total_buy_cost
                profit_rate = (net_profit / total_buy_cost * 100) if total_buy_cost > 0 else 0
                total_commission = buy_commission + paid_fee
                
                # v8.0 위꼬리 방어 결과 확인
                final_trade_result = trade_result
                if wick_defense_result == 'SUCCESS' and trade_result == "PROFIT_TAKE":
                    final_trade_result = "WICK_DEFENSE_SAVE"
                elif wick_defense_result == 'SUCCESS' and trade_result == "STOP_LOSS":
                    final_trade_result = "GRACE_PERIOD_SAVE"
                
                # 성능 데이터 기록
                operation_duration = time.time() - start_time
                
                # 데이터베이스 업데이트
                cursor.execute('''
                    UPDATE trades SET 
                        status = 'COMPLETED',
                        exit_timestamp = ?,
                        actual_exit_price = ?,
                        trade_result = ?,
                        commission_krw = ?,
                        net_profit_krw = ?,
                        profit_rate_pct = ?,
                        analysis_duration_seconds = ?
                    WHERE trade_id = ?
                ''', (exit_timestamp, actual_exit_price, final_trade_result, 
                      total_commission, net_profit, profit_rate, operation_duration, trade_id))
                
                # 성능 추적 테이블에 기록
                cursor.execute('''
                    INSERT INTO system_performance (
                        timestamp, operation_type, duration_seconds, 
                        api_calls_count, success, context_data
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (exit_timestamp, 'SELL_ORDER', operation_duration, 
                      3, True, json.dumps({
                          'trade_id': trade_id,
                          'final_result': final_trade_result,
                          'profit_rate': profit_rate,
                          'wick_defense_used': bool(wick_defense_was_active)
                      })))
                
                conn.commit()
            
            # 성공 로그 출력
            profit_emoji = "💰" if net_profit > 0 else "💸"
            defense_emoji = "🛡️" if final_trade_result in ["WICK_DEFENSE_SAVE", "GRACE_PERIOD_SAVE"] else ""
            
            self.logger.log_with_context(
                'info',
                f'v8.0 {profit_emoji}{defense_emoji} 정확한 매도 완료',
                trade_id=trade_id,
                exit_price=f'{actual_exit_price:,.0f}원',
                net_profit=f'{net_profit:+,.0f}원',
                profit_rate=f'{profit_rate:+.2f}%',
                total_commission=f'{total_commission:,.0f}원',
                result=final_trade_result,
                duration=f'{operation_duration:.2f}초'
            )
            
            return True
                    
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 매도 주문 결과 처리 중 오류: {e}')
            return False

    def _process_buy_order_result_v8(self, trade_id: int, order_details: Dict, start_time: float) -> bool:
        """
        v8.0 매수 주문 결과 처리 - 정확한 진입가 계산 및 성능 추적
        
        Args:
            trade_id (int): 거래 ID
            order_details (Dict): 주문 상세 정보
            start_time (float): 매수 시작 시간
            
        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 실제 체결 정보 추출
            executed_volume = float(order_details.get('executed_volume', 0))
            paid_fee = float(order_details.get('paid_fee', 0))
            
            if executed_volume <= 0:
                self.logger.log_with_context('error', 'v8.0 체결된 물량이 없습니다')
                return False
            
            # 실제 매수 단가 계산
            total_paid = 0
            trades = order_details.get('trades', [])
            
            if trades:
                total_paid = sum(float(trade['price']) * float(trade['volume']) for trade in trades)
                actual_entry_price = total_paid / executed_volume
            else:
                total_paid = float(order_details.get('price', 0)) * executed_volume
                actual_entry_price = float(order_details.get('price', 0))
            
            total_cost = total_paid + paid_fee
            entry_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 성능 데이터 기록
            operation_duration = time.time() - start_time
            
            # 데이터베이스 업데이트
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE trades SET 
                        status = 'ACTIVE',
                        position_size_xrp = ?,
                        entry_timestamp = ?,
                        actual_entry_price = ?,
                        commission_krw = ?,
                        analysis_duration_seconds = ?
                    WHERE trade_id = ?
                ''', (executed_volume, entry_timestamp, actual_entry_price, 
                      paid_fee, operation_duration, trade_id))
                
                # 성능 추적 테이블에 기록
                cursor.execute('''
                    INSERT INTO system_performance (
                        timestamp, operation_type, duration_seconds, 
                        api_calls_count, success, context_data
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (entry_timestamp, 'BUY_ORDER', operation_duration, 
                      3, True, json.dumps({
                          'trade_id': trade_id,
                          'position_size': executed_volume,
                          'entry_price': actual_entry_price,
                          'total_cost': total_cost
                      })))
                
                conn.commit()
            
            # 성공 로그 출력
            self.logger.log_with_context(
                'info',
                f'v8.0 💰 정확한 매수 완료',
                trade_id=trade_id,
                entry_price=f'{actual_entry_price:,.0f}원',
                position_size=f'{executed_volume:,.4f} XRP',
                total_cost=f'{total_cost:,.0f}원',
                commission=f'{paid_fee:,.0f}원',
                duration=f'{operation_duration:.2f}초'
            )
            
            return True
                    
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 매수 주문 결과 처리 중 오류: {e}')
            return False

    def _monitor_planned_trades_v8(self) -> None:
        """
        v8.0 계획된 거래(PLANNED) 실시간 감시 - 진입 조건 확인
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 최신 PLANNED 거래 하나만 조회
                cursor.execute('''
                    SELECT trade_id, planned_entry_price, checklist_score, 
                           signal_confidence_multiplier, calculated_position_ratio
                    FROM trades 
                    WHERE status = 'PLANNED' AND planned_entry_price > 0
                    ORDER BY plan_timestamp DESC
                    LIMIT 1
                ''')
                
                planned_trade = cursor.fetchone()
            
            if not planned_trade:
                return
            
            trade_id, planned_entry_price, checklist_score, signal_multiplier, position_ratio = planned_trade
            
            # 현재 가격 확인
            orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
            if not orderbook:
                return
            
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # v8.0 진입 조건 확인
            entry_tolerance = self._calculate_entry_tolerance_v8(checklist_score, signal_multiplier)
            price_diff = abs(current_price - planned_entry_price)
            max_allowed_diff = planned_entry_price * entry_tolerance
            
            if price_diff <= max_allowed_diff:
                self.logger.log_with_context(
                    'info',
                    'v8.0 계획된 매수 조건 만족!',
                    trade_id=trade_id,
                    planned_price=f'{planned_entry_price:,.0f}원',
                    current_price=f'{current_price:,.0f}원',
                    price_diff=f'{price_diff:,.0f}원',
                    allowed_diff=f'{max_allowed_diff:,.0f}원',
                    tolerance=f'{entry_tolerance:.1%}',
                    checklist_score=f'{checklist_score:.1f}/5.5'
                )
                
                # 매수 실행
                success = self._execute_buy_order_v8(trade_id, current_price)
                if success:
                    self.logger.log_with_context('info', f'v8.0 계획된 매수 성공! (거래 ID: {trade_id})')
                else:
                    self.logger.log_with_context('warning', f'v8.0 계획된 매수 실패 (거래 ID: {trade_id})')
            else:
                # 디버그 로그 (너무 자주 출력되지 않도록 조건부)
                if price_diff > max_allowed_diff * 2:  # 허용 범위의 2배 이상 차이날 때만 로그
                    self.logger.log_with_context(
                        'debug',
                        'v8.0 계획된 매수 조건 미달성',
                        trade_id=trade_id,
                        price_diff=f'{price_diff:,.0f}원',
                        required_diff=f'≤{max_allowed_diff:,.0f}원'
                    )
                            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 계획된 거래 감시 중 오류: {e}')

    def _calculate_entry_tolerance_v8(self, checklist_score: float, signal_multiplier: float) -> float:
        """
        v8.0 진입 허용 오차 계산 (신호 품질에 따른 동적 조정)
        
        Args:
            checklist_score (float): 체크리스트 점수
            signal_multiplier (float): 신호 신뢰도 승수
            
        Returns:
            float: 진입 허용 오차 (비율)
        """
        try:
            # 기본 허용 오차: 1%
            base_tolerance = 0.01
            
            # 신호 품질이 높을수록 더 관대한 허용 오차
            if checklist_score >= 4.5:  # A+ 등급
                quality_multiplier = 2.0  # 2% 허용
            elif checklist_score >= 3.5:  # A 등급
                quality_multiplier = 1.5  # 1.5% 허용
            elif checklist_score >= 2.5:  # B 등급
                quality_multiplier = 1.0  # 1% 허용
            else:
                quality_multiplier = 0.5  # 0.5% 허용 (엄격)
            
            # 신호 신뢰도 승수 반영
            confidence_adjustment = min(1.5, signal_multiplier)
            
            final_tolerance = base_tolerance * quality_multiplier * confidence_adjustment
            
            # 안전 범위: 0.3% ~ 3%
            return max(0.003, min(0.03, final_tolerance))
            
        except Exception as e:
            self.logger.log_with_context('error', f'진입 허용 오차 계산 중 오류: {e}')
            return 0.01  # 기본값 1%

## =============================================================================
    # Part 5: 확률론적 체크리스트 및 AI 전략 시스템
## =============================================================================

    def _validate_entry_checklist_v8(self, market_data: Dict, market_regime: Dict) -> Dict:
            """
            v8.0 5단계 진입 체크리스트 + XRP 전문가 보너스 (강화된 알고리즘)
            
            Args:
                market_data (Dict): 시장 데이터
                market_regime (Dict): 시장 체제 분석 결과
                
            Returns:
                Dict: 체크리스트 검증 결과
            """
            try:
                self.logger.log_with_context('info', 'v8.0 확률론적 진입 조건 체크리스트 검증 시작')
                
                checklist = {
                    'market_regime': 0,
                    'trend_alignment': 0, 
                    'signal_strength': 0,
                    'no_contrary_signals': 0,
                    'risk_reward': 0,
                    'xrp_expert_bonus': 0
                }
                
                # 1. 시장체제 진단 검증 (0-1점)
                regime = market_regime['regime']
                confidence = market_regime['confidence']
                
                if regime == '명백한_상승장' and confidence == '높음':
                    checklist['market_regime'] = 1.0
                elif regime == '횡보_박스권' or confidence == '중간':
                    checklist['market_regime'] = 0.5
                elif regime == '명백한_하락장' or confidence == '낮음':
                    checklist['market_regime'] = 0.0
                else:
                    checklist['market_regime'] = 0.3
                    
                self.logger.log_with_context(
                    'debug',
                    '체크리스트 1단계: 시장체제',
                    score=f'{checklist["market_regime"]:.1f}/1.0',
                    regime=regime,
                    confidence=confidence
                )
                
                # 2. 다중 시간대 추세 일치성 (0-1점)
                indicators = market_data['technical_indicators']
                aligned_timeframes = 0
                total_timeframes = 0
                trend_direction = None
                
                for tf in ['15m', '1h', '4h', 'day']:
                    if tf in indicators:
                        total_timeframes += 1
                        trend_strength = indicators[tf]['trend'].get('trend_strength', 0)
                        
                        if abs(trend_strength) >= 1:
                            if trend_direction is None:
                                trend_direction = 1 if trend_strength > 0 else -1
                            
                            if (trend_direction > 0 and trend_strength > 0) or (trend_direction < 0 and trend_strength < 0):
                                aligned_timeframes += 1
                
                if total_timeframes > 0:
                    alignment_ratio = aligned_timeframes / total_timeframes
                    if alignment_ratio >= 0.8:
                        checklist['trend_alignment'] = 1.0
                    elif alignment_ratio >= 0.6:
                        checklist['trend_alignment'] = 0.5
                    else:
                        checklist['trend_alignment'] = 0.0
                
                self.logger.log_with_context(
                    'debug',
                    '체크리스트 2단계: 추세일치',
                    score=f'{checklist["trend_alignment"]:.1f}/1.0',
                    aligned=f'{aligned_timeframes}/{total_timeframes}'
                )
                
                # 3. 진입 신호 강도 검증 (0-1점)
                signal_count = self._count_entry_signals_v8(market_regime, indicators)
                
                if signal_count >= 3:
                    checklist['signal_strength'] = 1.0
                elif signal_count >= 2:
                    checklist['signal_strength'] = 0.5
                else:
                    checklist['signal_strength'] = 0.0
                    
                self.logger.log_with_context(
                    'debug',
                    '체크리스트 3단계: 신호강도',
                    score=f'{checklist["signal_strength"]:.1f}/1.0',
                    signal_count=f'{signal_count}/3'
                )
                
                # 4. 반대 신호 부재 확인 (0-1점)
                contrary_signals = self._count_contrary_signals_v8(market_regime, indicators)
                
                if contrary_signals == 0:
                    checklist['no_contrary_signals'] = 1.0
                elif contrary_signals == 1:
                    checklist['no_contrary_signals'] = 0.5
                else:
                    checklist['no_contrary_signals'] = 0.0
                    
                self.logger.log_with_context(
                    'debug',
                    '체크리스트 4단계: 반대신호부재',
                    score=f'{checklist["no_contrary_signals"]:.1f}/1.0',
                    contrary_count=contrary_signals
                )
                
                # 5. 손익비 적절성 (0-1점)
                risk_reward_ratio = self._calculate_risk_reward_ratio_v8(market_data, indicators)
                
                if risk_reward_ratio >= 2.0:
                    checklist['risk_reward'] = 1.0
                elif risk_reward_ratio >= 1.5:
                    checklist['risk_reward'] = 0.5
                else:
                    checklist['risk_reward'] = 0.0
                    
                self.logger.log_with_context(
                    'debug',
                    '체크리스트 5단계: 손익비',
                    score=f'{checklist["risk_reward"]:.1f}/1.0',
                    ratio=f'{risk_reward_ratio:.2f}'
                )
                
                # 6. v8.0 XRP 전문가 보너스 (0-0.5점)
                xrp_analysis = market_data.get('xrp_expert_analysis', {})
                expert_confidence = xrp_analysis.get('expert_confidence', 0)
                energy_compression = xrp_analysis.get('energy_compression_detected', False)
                breakout_prob = xrp_analysis.get('breakout_probability', 0)
                
                if energy_compression and breakout_prob > 0.8:
                    checklist['xrp_expert_bonus'] = 0.5
                elif energy_compression or expert_confidence >= 3:
                    checklist['xrp_expert_bonus'] = 0.3
                elif expert_confidence >= 2:
                    checklist['xrp_expert_bonus'] = 0.1
                else:
                    checklist['xrp_expert_bonus'] = 0.0
                    
                self.logger.log_with_context(
                    'debug',
                    '체크리스트 6단계: XRP전문가보너스',
                    score=f'{checklist["xrp_expert_bonus"]:.1f}/0.5',
                    confidence=f'{expert_confidence}/5'
                )
                
                # 총점 계산 (최대 5.5점)
                total_score = sum(checklist.values())
                
                # 상세 내역 생성
                breakdown = {
                    'market_regime': f"{checklist['market_regime']:.1f}/1점 - 체제: {regime}",
                    'trend_alignment': f"{checklist['trend_alignment']:.1f}/1점 - {aligned_timeframes}/{total_timeframes} 시간대",
                    'signal_strength': f"{checklist['signal_strength']:.1f}/1점 - {signal_count}개 신호",
                    'no_contrary_signals': f"{checklist['no_contrary_signals']:.1f}/1점 - {contrary_signals}개 반대신호",
                    'risk_reward': f"{checklist['risk_reward']:.1f}/1점 - R:R {risk_reward_ratio:.2f}",
                    'xrp_expert_bonus': f"{checklist['xrp_expert_bonus']:.1f}/0.5점 - 전문가 신뢰도 {expert_confidence}/5"
                }
                
                self.logger.log_with_context(
                    'info',
                    'v8.0 확률론적 체크리스트 검증 완료',
                    total_score=f'{total_score:.1f}/5.5',
                    grade=self._get_signal_grade_v8(total_score)
                )
                
                return {
                    'checklist': checklist,
                    'total_score': total_score,
                    'breakdown': breakdown
                }
                
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 확률론적 체크리스트 검증 중 오류: {e}')
                return {'total_score': 0, 'checklist': {}, 'breakdown': {}}

    def _count_entry_signals_v8(self, market_regime: Dict, indicators: Dict) -> int:
            """
            v8.0 진입 신호 개수 계산
            
            Args:
                market_regime (Dict): 시장 체제 분석 결과
                indicators (Dict): 기술적 지표들
                
            Returns:
                int: 신호 개수
            """
            try:
                signal_count = 0
                
                # 골든크로스 체크
                if market_regime.get('key_signals', {}).get('golden_cross', False):
                    signal_count += 1
                    
                # 거래량 급증 체크
                h1_volume = indicators.get('1h', {}).get('volume', {})
                volume_ratio = h1_volume.get('volume_ratio', 1.0)
                if volume_ratio >= 2.0:
                    signal_count += 1
                    
                # 모멘텀 신호 체크 (RSI 과매도에서 반등 또는 강세 모멘텀)
                h1_momentum = indicators.get('1h', {}).get('momentum', {})
                rsi = h1_momentum.get('rsi', 50)
                if h1_momentum.get('rsi_oversold', False) or (rsi > 50 and rsi < 70):
                    signal_count += 1
                    
                # 추가 신호: MACD 상승 교차
                h1_trend = indicators.get('1h', {}).get('trend', {})
                macd_line = h1_trend.get('macd_line', 0)
                macd_signal = h1_trend.get('macd_signal', 0)
                if macd_line > macd_signal and macd_line > 0:
                    signal_count += 1
                    
                # 볼린저 밴드 하단 바운스
                h1_volatility = indicators.get('1h', {}).get('volatility', {})
                bb_position = h1_volatility.get('bb_position', 0.5)
                if bb_position < 0.2:  # 하단 20% 이하에서 바운스
                    signal_count += 1
                
                return min(signal_count, 3)  # 최대 3개까지만 인정
                
            except Exception as e:
                self.logger.log_with_context('error', f'진입 신호 계산 중 오류: {e}')
                return 0

    def _count_contrary_signals_v8(self, market_regime: Dict, indicators: Dict) -> int:
        """
        v8.0 반대 신호 개수 계산
        
        Args:
            market_regime (Dict): 시장 체제 분석 결과
            indicators (Dict): 기술적 지표들
            
        Returns:
            int: 반대 신호 개수
        """
        try:
            contrary_signals = 0
            
            # 베어리시 다이버전스 체크
            h1_momentum = indicators.get('1h', {}).get('momentum', {})
            rsi_div = h1_momentum.get('rsi_divergence', 'none')
            if rsi_div == 'bearish':
                contrary_signals += 1
                
            # BTC 급락 체크
            btc_analysis = market_regime.get('btc_analysis', {})
            btc_1h_change = btc_analysis.get('btc_1h_change', 0)
            if btc_1h_change < -3:
                contrary_signals += 1
                
            # 주요 저항선 근처 체크 (BB 상단)
            h1_volatility = indicators.get('1h', {}).get('volatility', {})
            bb_position = h1_volatility.get('bb_position', 0.5)
            if bb_position > 0.8:
                contrary_signals += 1
                
            # RSI 과매수 체크
            rsi = h1_momentum.get('rsi', 50)
            if rsi > 70:
                contrary_signals += 1
                
            # 데스크로스 체크
            if market_regime.get('key_signals', {}).get('death_cross', False):
                contrary_signals += 1
            
            return contrary_signals
            
        except Exception as e:
            self.logger.log_with_context('error', f'반대 신호 계산 중 오류: {e}')
            return 0

    def _calculate_risk_reward_ratio_v8(self, market_data: Dict, indicators: Dict) -> float:
        """
        v8.0 리스크-리워드 비율 계산
        
        Args:
            market_data (Dict): 시장 데이터
            indicators (Dict): 기술적 지표들
            
        Returns:
            float: 리스크-리워드 비율
        """
        try:
            current_price = market_data['current_price']
            
            # ATR 기반 목표가/손절가 추정
            h1_volatility = indicators.get('1h', {}).get('volatility', {})
            atr = h1_volatility.get('atr', current_price * 0.02)
            
            # 동적 목표가/손절가 계산
            estimated_target = current_price + (atr * 2.5)
            estimated_stop = current_price - (atr * 1.0)
            
            if estimated_stop > 0:
                risk_reward_ratio = (estimated_target - current_price) / (current_price - estimated_stop)
                return max(0.5, min(5.0, risk_reward_ratio))  # 0.5 ~ 5.0 범위로 제한
            
            return 1.0
            
        except Exception as e:
            self.logger.log_with_context('error', f'리스크-리워드 비율 계산 중 오류: {e}')
            return 1.0

    def _get_signal_grade_v8(self, total_score: float) -> str:
        """
        v8.0 신호 등급 계산
        
        Args:
            total_score (float): 체크리스트 총점
            
        Returns:
            str: 신호 등급
        """
        if total_score >= 4.5:
            return "A+"
        elif total_score >= 3.5:
            return "A"
        elif total_score >= 2.5:
            return "B"
        else:
            return "F"

    def _calculate_signal_confidence_multiplier_v8(self, checklist_score: float) -> Dict:
        """
        v8.0 신호 신뢰도 승수 계산
        
        Args:
            checklist_score (float): 체크리스트 점수
            
        Returns:
            Dict: 신호 신뢰도 정보
        """
        try:
            if checklist_score >= 4.5:
                multiplier = 1.0
                grade = "A+"
                description = "A+급 최상의 기회 (100% 투자비중)"
            elif checklist_score >= 3.5:
                multiplier = 0.7
                grade = "A"
                description = "좋은 기회 (70% 투자비중)"
            elif checklist_score >= 2.5:
                multiplier = 0.4
                grade = "B"
                description = "XRP 특별 허용 구간 (40% 투자비중)"
            else:
                multiplier = 0.0
                grade = "F"
                description = "진입 절대 금지 (0% 투자비중)"
            
            self.logger.log_with_context(
                'info',
                'v8.0 신호 신뢰도 계산 완료',
                grade=grade,
                score=f'{checklist_score:.1f}/5.5',
                multiplier=f'{multiplier:.1f}'
            )
            
            return {
                'multiplier': multiplier,
                'grade': grade,
                'score': checklist_score,
                'description': description
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 신호 신뢰도 승수 계산 중 오류: {e}')
            return {'multiplier': 0.0, 'grade': 'F', 'score': 0, 'description': '계산 실패'}

    def _calculate_dynamic_position_size_v8(self, krw_balance: float, market_regime: Dict, signal_confidence: Dict) -> Dict:
        """
        v8.0 확률론적 동적 포지션 사이징 (신호 신뢰도 승수 통합)
        
        Args:
            krw_balance (float): KRW 잔고
            market_regime (Dict): 시장 체제 분석 결과
            signal_confidence (Dict): 신호 신뢰도 정보
            
        Returns:
            Dict: 포지션 사이징 결과
        """
        try:
            regime = market_regime.get('regime', '분석실패')
            confidence = market_regime.get('confidence', '없음')
            reliability_score = market_regime.get('reliability_score', 50)
            
            # 1. 기본 투자 비중 결정 (시장 체제 기반)
            base_risk_pct = self._get_base_risk_percentage_v8(regime, confidence)
            risk_level = self._get_risk_level_description_v8(regime, confidence)
            
            # 2. v8.0 핵심: 신호 신뢰도 승수 적용
            signal_multiplier = signal_confidence['multiplier']
            signal_grade = signal_confidence['grade']
            
            # 3. 비트코인 분석 기반 조정
            btc_adjustment = self._calculate_btc_adjustment_v8(market_regime)
            
            # 4. 신뢰도 점수 기반 조정
            reliability_adjustment = self._calculate_reliability_adjustment_v8(reliability_score)
            
            # 5. 추가 리스크 수정자 적용
            modifier_adjustment = self._calculate_modifier_adjustment_v8(market_regime)
            
            # 6. v8.0 최종 투자 비중 계산
            final_risk_pct = (base_risk_pct * signal_multiplier * 
                             btc_adjustment * reliability_adjustment * modifier_adjustment)
            
            # 7. 안전 한계 적용
            final_risk_pct = max(0.0, min(0.90, final_risk_pct))
            
            # 8. 추가 안전 조건
            regime_score = market_regime.get('regime_score', 0)
            if regime_score <= -2.5:
                final_risk_pct = min(final_risk_pct, 0.15)
                risk_level += "+초강하락제한"
            elif regime_score <= -2:
                final_risk_pct = min(final_risk_pct, 0.25)
                risk_level += "+강하락제한"
            
            invest_amount = krw_balance * final_risk_pct
            
            self.logger.log_with_context(
                'info',
                'v8.0 확률론적 동적 포지션 사이징 완료',
                regime=regime,
                base_ratio=f'{base_risk_pct:.0%}',
                signal_multiplier=f'{signal_multiplier:.1f}',
                signal_grade=signal_grade,
                final_ratio=f'{final_risk_pct:.0%}',
                invest_amount=f'{invest_amount:,.0f}원',
                risk_level=risk_level
            )
            
            return {
                'invest_amount': invest_amount,
                'risk_percentage': final_risk_pct,
                'base_risk_percentage': base_risk_pct,
                'signal_multiplier': signal_multiplier,
                'signal_grade': signal_grade,
                'btc_adjustment': btc_adjustment,
                'reliability_adjustment': reliability_adjustment,
                'modifier_adjustment': modifier_adjustment,
                'risk_level': risk_level,
                'regime': regime,
                'reliability_score': reliability_score
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 확률론적 동적 포지션 사이징 계산 중 오류: {e}')
            return {
                'invest_amount': krw_balance * 0.20,
                'risk_percentage': 0.20,
                'signal_multiplier': 0.2,
                'signal_grade': 'F',
                'risk_level': "오류발생-안전모드",
                'regime': "계산실패"
            }

    def _get_base_risk_percentage_v8(self, regime: str, confidence: str) -> float:
        """
        v8.0 기본 투자 비중 결정
        
        Args:
            regime (str): 시장 체제
            confidence (str): 신뢰도
            
        Returns:
            float: 기본 투자 비중
        """
        if regime == "명백한_상승장" and confidence == "높음":
            return 0.90
        elif regime == "명백한_상승장":
            return 0.75
        elif regime == "횡보_박스권":
            return 0.55
        elif regime == "고변동성_혼조장":
            return 0.35
        elif regime == "애매한_혼조장":
            return 0.25
        else:
            return 0.0

    def _get_risk_level_description_v8(self, regime: str, confidence: str) -> str:
        """
        v8.0 리스크 레벨 설명 생성
        
        Args:
            regime (str): 시장 체제
            confidence (str): 신뢰도
            
        Returns:
            str: 리스크 레벨 설명
        """
        if regime == "명백한_상승장" and confidence == "높음":
            return "매우적극적"
        elif regime == "명백한_상승장":
            return "중간-적극"
        elif regime == "횡보_박스권":
            return "중립적"
        elif regime == "고변동성_혼조장":
            return "보수적"
        elif regime == "애매한_혼조장":
            return "매우보수적"
        else:
            return "매매금지"

    def _calculate_btc_adjustment_v8(self, market_regime: Dict) -> float:
        """
        v8.0 비트코인 기반 조정 계수 계산
        
        Args:
            market_regime (Dict): 시장 체제 분석 결과
            
        Returns:
            float: BTC 조정 계수
        """
        try:
            btc_analysis = market_regime.get('btc_analysis', {})
            btc_influence = btc_analysis.get('btc_influence', '낮음')
            
            if btc_influence not in ["높음", "매우높음"]:
                return 1.0
            
            btc_1h_change = btc_analysis.get('btc_1h_change', 0)
            
            if btc_1h_change < -4:
                return 0.2  # 80% 감소
            elif btc_1h_change < -2:
                return 0.6  # 40% 감소
            elif btc_1h_change > 3:
                return 1.3  # 30% 증가
            elif btc_1h_change > 1:
                return 1.1  # 10% 증가
            else:
                return 1.0
                
        except Exception as e:
            self.logger.log_with_context('error', f'BTC 조정 계수 계산 중 오류: {e}')
            return 1.0

    def _calculate_reliability_adjustment_v8(self, reliability_score: int) -> float:
        """
        v8.0 신뢰도 점수 기반 조정 계수 계산
        
        Args:
            reliability_score (int): 신뢰도 점수 (0-100)
            
        Returns:
            float: 신뢰도 조정 계수
        """
        if reliability_score < 50:
            return 0.5
        elif reliability_score < 70:
            return 0.8
        elif reliability_score > 85:
            return 1.2
        elif reliability_score > 75:
            return 1.1
        else:
            return 1.0

    def _calculate_modifier_adjustment_v8(self, market_regime: Dict) -> float:
        """
        v8.0 위험 수정자 기반 조정 계수 계산
        
        Args:
            market_regime (Dict): 시장 체제 분석 결과
            
        Returns:
            float: 수정자 조정 계수
        """
        try:
            confidence_modifiers = market_regime.get('confidence_modifiers', [])
            adjustment = 1.0
            
            for modifier in confidence_modifiers:
                if "BTC강하락위험" in str(modifier):
                    adjustment *= 0.4
                elif "구조변화위험" in str(modifier):
                    adjustment *= 0.7
                elif "BTC추세불일치" in str(modifier):
                    adjustment *= 0.8
            
            return adjustment
            
        except Exception as e:
            self.logger.log_with_context('error', f'수정자 조정 계수 계산 중 오류: {e}')
            return 1.0

    def orient_and_decide_v8(self, market_data: Dict) -> Optional[Dict]:
        """
        v8.0 판단(Orient) & 결정(Decide): 확률론적 접근 + XRP 전문가 통합 전략 수립
        
        Args:
            market_data (Dict): 시장 데이터
            
        Returns:
            Optional[Dict]: 전략 또는 None
        """
        try:
            # 상태 확인
            if not self.state_manager.is_idle():
                current_state, _ = self.state_manager.get_state()
                self.logger.log_with_context('debug', f'전략 수립 스킵: 시스템 상태 {current_state.value}')
                return None
            
            self.logger.log_with_context('info', 'v8.0 확률론적 접근 + XRP 전문가 AI 전략 수립 중')
            
            # 포지션 상태 확인
            position_status = market_data.get('position_status', {})
            has_position = position_status.get('has_position', False)
            
            if has_position:
                self.logger.log_with_context('info', 'XRP 보유 중 - v8.0 트리거 기반 포지션 관리 모드')
                return self._generate_position_management_advice_v8(market_data)
            else:
                self.logger.log_with_context('info', 'XRP 미보유 - v8.0 확률론적 접근 신규 진입 전략 모드')
                return self._generate_new_entry_strategy_v8(market_data)
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 전략 수립 중 오류: {e}')
            return None

    def _generate_new_entry_strategy_v8(self, market_data: Dict) -> Optional[Dict]:
        """
        v8.0 신규 진입 전략: 확률론적 접근 + XRP 전문가 통합
        
        Args:
            market_data (Dict): 시장 데이터
            
        Returns:
            Optional[Dict]: 진입 전략 또는 None
        """
        try:
            # 1. 시장체제 분석
            market_regime = self._analyze_market_regime_v8(market_data)
            
            self.logger.log_with_context(
                'info',
                'v8.0 진입 분석 시작',
                regime=market_regime['regime'],
                confidence=market_regime['confidence']
            )
            
            # 2. v8.0 확률론적 체크리스트 검증
            checklist_result = self._validate_entry_checklist_v8(market_data, market_regime)
            
            # 3. v8.0 신호 신뢰도 승수 계산
            signal_confidence = self._calculate_signal_confidence_multiplier_v8(checklist_result['total_score'])
            
            # 4. v8.0 하드 임계값 검사 (2.5점 미만 진입 금지)
            if checklist_result['total_score'] < 2.5:
                self.logger.log_with_context(
                    'warning',
                    f'v8.0 하드 임계값 미달: {checklist_result["total_score"]:.1f}/5.5점 - 진입 금지'
                )
                return self._create_no_entry_response_v8(market_regime, checklist_result, signal_confidence)
            
            # 5. v8.0 확률론적 동적 포지션 사이징
            krw_balance = self._api_call_wrapper(self.upbit_client.get_balance, "KRW")
            if krw_balance is None:
                self.logger.log_with_context('error', 'KRW 잔고 조회 실패')
                return None
            
            position_info = self._calculate_dynamic_position_size_v8(krw_balance, market_regime, signal_confidence)
            
            # 6. 최소 투자금 검증
            min_investment = self.config_manager.get('trading.min_investment_krw')
            if position_info['invest_amount'] < min_investment:
                self.logger.log_with_context(
                    'warning',
                    f'v8.0 최종 투자금({position_info["invest_amount"]:,.0f}원) 부족 - 진입 금지'
                )
                return self._create_no_entry_response_v8(market_regime, checklist_result, signal_confidence)
            
            # 7. 하드 임계값 통과 - AI 정교 분석 요청
            self.logger.log_with_context(
                'info',
                f'v8.0 확률론적 검증 통과: {signal_confidence["grade"]}등급 ({checklist_result["total_score"]:.1f}/5.5점)',
                invest_amount=f'{position_info["invest_amount"]:,.0f}원',
                risk_ratio=f'{position_info["risk_percentage"]:.0%}'
            )
            
            return self._request_ai_entry_analysis_v8(market_data, market_regime, checklist_result, signal_confidence, position_info)
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 신규 진입 전략 생성 중 오류: {e}')
            return None

    def _create_no_entry_response_v8(self, market_regime: Dict, checklist_result: Dict, signal_confidence: Dict) -> Dict:
        """
        v8.0 진입 조건 미달 시 응답 생성
        
        Args:
            market_regime (Dict): 시장 체제 분석 결과
            checklist_result (Dict): 체크리스트 결과
            signal_confidence (Dict): 신호 신뢰도
            
        Returns:
            Dict: 진입 금지 응답
        """
        total_score = checklist_result['total_score']
        breakdown = checklist_result['breakdown']
        grade = signal_confidence['grade']
        
        return {
            "market_analysis": {
                "regime_verification": f"v8.0 확률론적 검증 실패 - {grade}등급 ({total_score:.1f}/5.5점)",
                "trend_group": f"다중 시간대: {breakdown.get('trend_alignment', 'N/A')}",
                "momentum_group": f"신호 강도: {breakdown.get('signal_strength', 'N/A')}",
                "volatility_group": f"반대 신호: {breakdown.get('no_contrary_signals', 'N/A')}",
                "volume_group": f"XRP 전문가: {breakdown.get('xrp_expert_bonus', 'N/A')}",
                "overall_confidence": "진입 금지",
                "market_condition": "관망 필요"
            },
            "risk_assessment": {
                "risk_level": "매우높음",
                "position_size": "진입 금지",
                "max_holding_time": "해당없음",
                "key_risks": f"v8.0 확률론적 점수 {total_score:.1f}/5.5점으로 진입 조건 미충족"
            },
            "entry_price": 0,
            "target_price": 0,
            "stop_loss_price": 0,
            "entry_reason": f"v8.0 확률론적 검증 실패 ({grade}등급, {total_score:.1f}/5.5점) - 하드 임계값 2.5점 미달",
            "target_reason": "진입하지 않으므로 목표가 설정 불필요",
            "stop_loss_reason": "진입하지 않으므로 손절가 설정 불필요",
            "sell_strategy": "진입 대기 - 확률론적 조건 개선까지 관망",
            "lessons_applied": f"v8.0 확률론적 접근으로 낮은 품질 신호 필터링 (총점: {total_score:.1f}/5.5)",
            "regime_adaptation": f"체제 '{market_regime['regime']}'에서 신중한 접근으로 자본 보호",
            "signal_grade": grade,
            "checklist_score": total_score,
            "checklist_breakdown": breakdown
        }

    def _request_ai_entry_analysis_v8(self, market_data: Dict, market_regime: Dict, 
                                        checklist_result: Dict, signal_confidence: Dict, 
                                        position_info: Dict) -> Optional[Dict]:
            """
            v8.0 확률론적 검증 통과 후 AI 정교 분석 요청
            
            Args:
                market_data (Dict): 시장 데이터
                market_regime (Dict): 시장 체제 분석 결과
                checklist_result (Dict): 체크리스트 결과
                signal_confidence (Dict): 신호 신뢰도
                position_info (Dict): 포지션 사이징 정보
                
            Returns:
                Optional[Dict]: AI 분석 결과 또는 None
            """
            try:
                self.logger.log_with_context(
                    'info',
                    'v8.0 확률론적 검증 통과 - AI 정교 분석 요청',
                    grade=signal_confidence['grade'],
                    score=f'{checklist_result["total_score"]:.1f}/5.5'
                )
                
                # 현재 활성 교훈 로드
                current_lessons = self.get_current_lessons_for_strategy_v8()
                
                # AI 분석 프롬프트 생성
                ai_prompt = self._create_entry_analysis_prompt_v8(
                    market_data, market_regime, checklist_result, signal_confidence, 
                    position_info, current_lessons
                )
                
                # GPT 호출
                response = self.openai_client.chat.completions.create(
                    model=self.config_manager.get('ai.model'),
                    messages=[
                        {
                            "role": "system",
                            "content": self._get_entry_analysis_system_prompt_v8()
                        },
                        {
                            "role": "user",
                            "content": ai_prompt
                        }
                    ],
                    max_tokens=self.config_manager.get('ai.max_tokens'),
                    temperature=self.config_manager.get('ai.temperature')
                )
                
                ai_analysis = response.choices[0].message.content
                
                # AI 응답 파싱
                parsed_strategy = self._parse_ai_entry_response_v8(ai_analysis, market_data, position_info)
                
                if parsed_strategy:
                    # v8.0 확률론적 정보 추가
                    parsed_strategy.update({
                        'checklist_score': checklist_result['total_score'],
                        'checklist_breakdown': checklist_result['breakdown'],
                        'signal_confidence_multiplier': signal_confidence['multiplier'],
                        'signal_grade': signal_confidence['grade'],
                        'calculated_position_ratio': position_info['risk_percentage'],
                        'wick_defense_active': True,  # v8.0 기본 활성화
                        'energy_compression_detected': market_data.get('xrp_expert_analysis', {}).get('energy_compression_detected', False),
                        'xrp_pattern_type': market_data.get('xrp_expert_analysis', {}).get('dominant_pattern', 'NONE')
                    })
                    
                    self.logger.log_with_context(
                        'info',
                        'v8.0 AI 정교 분석 완료',
                        entry_price=f'{parsed_strategy["entry_price"]:,.0f}원',
                        target_price=f'{parsed_strategy["target_price"]:,.0f}원',
                        expected_return=f'{((parsed_strategy["target_price"]/parsed_strategy["entry_price"]-1)*100):+.1f}%'
                    )
                    
                    return parsed_strategy
                else:
                    self.logger.log_with_context('error', 'v8.0 AI 응답 파싱 실패')
                    return None
                    
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 AI 정교 분석 요청 중 오류: {e}')
                return None
            
    def _create_entry_analysis_prompt_v8(self, market_data: Dict, market_regime: Dict,
                                        checklist_result: Dict, signal_confidence: Dict,
                                        position_info: Dict, current_lessons: str) -> str:
        """
        v8.0 진입 분석 프롬프트 생성
        
        Args:
            market_data (Dict): 시장 데이터
            market_regime (Dict): 시장 체제 분석 결과
            checklist_result (Dict): 체크리스트 결과
            signal_confidence (Dict): 신호 신뢰도
            position_info (Dict): 포지션 사이징 정보
            current_lessons (str): 현재 교훈
            
        Returns:
            str: AI 분석 프롬프트
        """
        current_price = market_data['current_price']
        indicators = market_data['technical_indicators']
        xrp_analysis = market_data.get('xrp_expert_analysis', {})
        
        # 핵심 지표 요약
        h1_indicators = indicators.get('1h', {})
        trend = h1_indicators.get('trend', {})
        momentum = h1_indicators.get('momentum', {})
        volatility = h1_indicators.get('volatility', {})
        volume = h1_indicators.get('volume', {})
        
        return f"""
# OMNI-XRP v8.0 확률론적 검증 통과 - 정교한 진입 전략 수립 요청

## 🎯 v8.0 확률론적 검증 결과
**신호 등급**: {signal_confidence['grade']} ({checklist_result['total_score']:.1f}/5.5점)
**투자 비중**: {position_info['risk_percentage']:.0%} ({position_info['invest_amount']:,.0f}원)
**신호 신뢰도**: {signal_confidence['multiplier']:.1f}x

### 체크리스트 상세 결과
{chr(10).join([f"- {key}: {value}" for key, value in checklist_result['breakdown'].items()])}

## 📊 현재 시장 상황
**현재가**: {current_price:,.0f}원
**시장 체제**: {market_regime['regime']} (신뢰도: {market_regime['confidence']})
**체제 점수**: {market_regime['regime_score']}/5

### 핵심 기술 지표 (1시간)
- **추세 강도**: {trend.get('trend_strength', 0)}/3
- **RSI**: {momentum.get('rsi', 50):.1f} (과매도: {momentum.get('rsi_oversold', False)})
- **볼린저밴드 위치**: {volatility.get('bb_position', 0.5):.1%}
- **거래량 비율**: {volume.get('volume_ratio', 1.0):.1f}x

### XRP 전문가 분석
- **에너지 압축**: {xrp_analysis.get('energy_compression_detected', False)}
- **돌파 확률**: {xrp_analysis.get('breakout_probability', 0):.0%}
- **지배적 패턴**: {xrp_analysis.get('dominant_pattern', 'NONE')}
- **전문가 신뢰도**: {xrp_analysis.get('expert_confidence', 0)}/5

## 🎓 적용해야 할 교훈
{current_lessons}

## 🔍 정교한 전략 수립 요청

v8.0 확률론적 시스템이 **{signal_confidence['grade']}등급 신호**를 감지했습니다.
다음 조건들을 종합하여 **정확한 진입/목표/손절 가격**을 결정해주세요:

### 필수 고려사항
1. **현재가 {current_price:,.0f}원 기준 현실적인 가격대 설정**
2. **v8.0 위꼬리 방어 시스템 활용 전제** (손절가 근처에서 60초 유예 + 재확인)
3. **XRP 특성 반영** (변동성, 패턴, 에너지 압축 등)
4. **축적된 교훈 적극 반영**
5. **리스크-리워드 비율 최소 1.5:1 이상**

### 출력 형식
다음 형식으로 **명확한 수치와 근거**를 제시해주세요:

**진입가**: [구체적 가격]원
**진입 근거**: [왜 이 가격이 최적인지 3가지 이유]

**목표가**: [구체적 가격]원  
**목표 근거**: [왜 이 가격이 현실적인지 3가지 이유]

**손절가**: [구체적 가격]원
**손절 근거**: [왜 이 가격이 적절한지 3가지 이유]

**매도 전략**: [구체적인 관리 방법]

**적용된 교훈**: [이번 거래에서 특별히 적용한 교훈 3가지]

**예상 시나리오**: 
- 성공 시나리오: [확률 %] - [상황 설명]
- 실패 시나리오: [확률 %] - [상황 설명]

모든 가격은 **현재가 {current_price:,.0f}원 대비 현실적인 범위** 내에서 설정해주세요.
"""

    def _get_entry_analysis_system_prompt_v8(self) -> str:
        """
        v8.0 진입 분석 시스템 프롬프트
        
        Returns:
            str: 시스템 프롬프트
        """
        return """당신은 OMNI-XRP v8.0의 정교한 진입 전략 전문가입니다.

핵심 역할:
1. v8.0 확률론적 검증을 통과한 신호에 대해 **정확한 진입/목표/손절 가격** 결정
2. **XRP의 특성과 시장 구조**를 깊이 이해한 현실적인 가격 설정
3. **축적된 교훈**을 적극 반영한 개선된 전략 수립
4. **v8.0 위꼬리 방어 시스템**을 활용한 리스크 관리 최적화

전문 분야:
- XRP/KRW 시장의 **지지/저항선, 패턴, 변동성** 특성 분석
- **현실적이고 달성 가능한** 목표가 설정 (과도한 욕심 금지)
- **v8.0 위꼬리 방어**를 고려한 적절한 손절가 배치
- **과거 교훈**을 바탕으로 한 실수 방지 및 성공 패턴 재현

중요 원칙:
- **현재가 기준으로 현실적인 가격대** 제시 (±10% 내외)
- **명확한 수치적 근거**와 함께 설명
- **감정적 판단 배제**, 데이터와 교훈에 기반한 객관적 분석
- **리스크 우선 사고**: 수익보다 손실 방지가 우선

목표: v8.0 시스템이 **높은 성공률**과 **안정적인 수익**을 달성할 수 있는 정교한 전략 제공"""

    def _parse_ai_entry_response_v8(self, ai_response: str, market_data: Dict, position_info: Dict) -> Optional[Dict]:
        """
        v8.0 AI 진입 분석 응답 파싱
        
        Args:
            ai_response (str): AI 응답
            market_data (Dict): 시장 데이터
            position_info (Dict): 포지션 정보
            
        Returns:
            Optional[Dict]: 파싱된 전략 또는 None
        """
        try:
            current_price = market_data['current_price']
            
            # 가격 추출을 위한 정규표현식
            entry_match = re.search(r'진입가[:\s]*([0-9,]+)원', ai_response)
            target_match = re.search(r'목표가[:\s]*([0-9,]+)원', ai_response)
            stop_match = re.search(r'손절가[:\s]*([0-9,]+)원', ai_response)
            
            if not (entry_match and target_match and stop_match):
                self.logger.log_with_context('error', 'v8.0 AI 응답에서 가격 정보 추출 실패')
                return None
            
            # 가격 파싱
            entry_price = float(entry_match.group(1).replace(',', ''))
            target_price = float(target_match.group(1).replace(',', ''))
            stop_loss_price = float(stop_match.group(1).replace(',', ''))
            
            # 유효성 검증
            if not self._validate_prices_v8(current_price, entry_price, target_price, stop_loss_price):
                return None
            
            # 근거 추출
            entry_reason = self._extract_reason_v8(ai_response, '진입 근거')
            target_reason = self._extract_reason_v8(ai_response, '목표 근거')
            stop_loss_reason = self._extract_reason_v8(ai_response, '손절 근거')
            sell_strategy = self._extract_reason_v8(ai_response, '매도 전략')
            lessons_applied = self._extract_reason_v8(ai_response, '적용된 교훈')
            
            return {
                'entry_price': entry_price,
                'target_price': target_price,
                'stop_loss_price': stop_loss_price,
                'entry_reason': entry_reason or f"v8.0 AI 분석: 현재가 {current_price:,.0f}원 대비 최적 진입점",
                'target_reason': target_reason or f"v8.0 AI 분석: 기술적 목표가 {target_price:,.0f}원",
                'stop_loss_reason': stop_loss_reason or f"v8.0 AI 분석: 위꼬리 방어 고려 손절가 {stop_loss_price:,.0f}원",
                'sell_strategy': sell_strategy or "목표가 도달 시 즉시 매도",
                'lessons_applied': lessons_applied or "v8.0 확률론적 접근 적용",
                'regime_adaptation': f"시장 체제 '{market_data.get('market_regime', {}).get('regime', '분석중')}'에 최적화된 전략"
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 AI 응답 파싱 중 오류: {e}')
            return None

    def _validate_prices_v8(self, current_price: float, entry_price: float, 
                           target_price: float, stop_loss_price: float) -> bool:
        """
        v8.0 가격 유효성 검증
        
        Args:
            current_price (float): 현재 가격
            entry_price (float): 진입가
            target_price (float): 목표가
            stop_loss_price (float): 손절가
            
        Returns:
            bool: 유효성 여부
        """
        try:
            # 1. 기본 논리 검증
            if not (stop_loss_price < entry_price < target_price):
                self.logger.log_with_context('error', 'v8.0 가격 논리 오류: 손절가 < 진입가 < 목표가 위반')
                return False
            
            # 2. 현실성 검증 (현재가 대비 ±15% 범위)
            price_tolerance = 0.15
            min_price = current_price * (1 - price_tolerance)
            max_price = current_price * (1 + price_tolerance)
            
            if not (min_price <= entry_price <= max_price):
                self.logger.log_with_context(
                    'error', 
                    f'v8.0 진입가 현실성 오류: {entry_price:,.0f}원 (허용범위: {min_price:,.0f}~{max_price:,.0f}원)'
                )
                return False
            
            # 3. 리스크-리워드 비율 검증 (최소 1.2:1)
            risk = entry_price - stop_loss_price
            reward = target_price - entry_price
            
            if risk <= 0 or reward <= 0:
                self.logger.log_with_context('error', 'v8.0 리스크-리워드 계산 오류')
                return False
            
            risk_reward_ratio = reward / risk
            if risk_reward_ratio < 1.2:
                self.logger.log_with_context(
                    'error', 
                    f'v8.0 리스크-리워드 비율 부족: {risk_reward_ratio:.2f} < 1.2'
                )
                return False
            
            self.logger.log_with_context(
                'info',
                'v8.0 가격 유효성 검증 통과',
                entry=f'{entry_price:,.0f}원',
                target=f'{target_price:,.0f}원',
                stop=f'{stop_loss_price:,.0f}원',
                rr_ratio=f'{risk_reward_ratio:.2f}'
            )
            
            return True
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 가격 유효성 검증 중 오류: {e}')
            return False

    def _extract_reason_v8(self, ai_response: str, section_name: str) -> str:
        """
        v8.0 AI 응답에서 특정 섹션의 근거 추출
        
        Args:
            ai_response (str): AI 응답
            section_name (str): 섹션 이름
            
        Returns:
            str: 추출된 근거
        """
        try:
            # 섹션 시작점 찾기
            start_pattern = f"**{section_name}**:"
            start_index = ai_response.find(start_pattern)
            
            if start_index == -1:
                return ""
            
            # 섹션 내용 추출 (다음 ** 까지)
            start_index += len(start_pattern)
            end_index = ai_response.find("**", start_index)
            
            if end_index == -1:
                # 다음 섹션이 없으면 끝까지
                content = ai_response[start_index:].strip()
            else:
                content = ai_response[start_index:end_index].strip()
            
            # 정리 및 반환
            content = re.sub(r'\n+', ' ', content)  # 줄바꿈을 공백으로
            content = re.sub(r'\s+', ' ', content)  # 연속 공백 제거
            
            return content[:500] if content else ""  # 최대 500자
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 근거 추출 중 오류: {e}')
            return ""

    def _analyze_market_regime_v8(self, market_data: Dict) -> Dict:
        """
        v8.0 다중 시간프레임 균형 잡힌 시장체제 분석
        
        Args:
            market_data (Dict): 시장 데이터
            
        Returns:
            Dict: 시장 체제 분석 결과
        """
        try:
            indicators = market_data['technical_indicators']
            current_price = market_data['current_price']
            
            self.logger.log_with_context(
                'info',
                'v8.0 시장체제 분석 시작',
                current_price=f'{current_price:,.0f}원'
            )
            
            # 시간프레임별 점수 계산
            timeframe_scores = {}
            timeframe_weights = {
                '5m': 0.15, '15m': 0.20, '1h': 0.25, '4h': 0.25, 'day': 0.15
            }
            
            total_weighted_score = 0
            
            for tf, weight in timeframe_weights.items():
                if tf not in indicators:
                    continue
                    
                tf_data = indicators[tf]['trend']
                trend_strength = tf_data.get('trend_strength', 0)
                
                # 골든/데스크로스 추가 점수
                if tf_data.get('golden_cross', False):
                    trend_strength += 1
                elif tf_data.get('death_cross', False):
                    trend_strength -= 1
                
                trend_strength = max(-3, min(3, trend_strength))
                
                timeframe_scores[tf] = trend_strength
                weighted_contribution = trend_strength * weight
                total_weighted_score += weighted_contribution
            
            # 변동성 및 구조 분석
            volatility_analysis = self._analyze_volatility_state_v8(indicators)
            btc_analysis = self._analyze_bitcoin_correlation_v8(market_data)
            structure_analysis = self._check_market_structure_shift_v8(market_data)
            
            # 체제 결정
            regime_result = self._determine_market_regime_v8(
                total_weighted_score, volatility_analysis, btc_analysis, structure_analysis
            )
            
            # 신뢰도 점수 계산
            reliability_score = self._calculate_regime_reliability_v8(
                regime_result, btc_analysis, structure_analysis
            )
            
            final_result = {
                'regime': regime_result['regime'],
                'risk_level': regime_result['risk_level'],
                'approach': regime_result['approach'],
                'confidence': regime_result['confidence'],
                'regime_score': total_weighted_score,
                'timeframe_scores': timeframe_scores,
                'volatility_state': volatility_analysis['state'],
                'key_signals': volatility_analysis['signals'],
                'btc_analysis': btc_analysis,
                'structure_analysis': structure_analysis,
                'reliability_score': reliability_score
            }
            
            self.logger.log_with_context(
                'info',
                'v8.0 시장체제 분석 완료',
                regime=final_result['regime'],
                confidence=final_result['confidence'],
                reliability=f'{reliability_score}/100'
            )
            
            return final_result
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 시장 체제 분석 중 오류: {e}')
            return {
                'regime': '분석실패',
                'risk_level': '매우높음',
                'approach': '매매금지',
                'confidence': '없음',
                'regime_score': 0,
                'reliability_score': 0
            }

    def _analyze_volatility_state_v8(self, indicators: Dict) -> Dict:
            """
            v8.0 변동성 상태 분석
            
            Args:
                indicators (Dict): 기술적 지표들
                
            Returns:
                Dict: 변동성 분석 결과
            """
            try:
                volatility_state = {
                    'state': 'normal',
                    'signals': {},
                    'squeeze_detected': False,
                    'expansion_detected': False
                }
                
                # 다중 시간대 변동성 분석
                squeeze_count = 0
                expansion_count = 0
                signals = {}
                
                for tf in ['15m', '1h', '4h', 'day']:
                    if tf not in indicators:
                        continue
                        
                    volatility = indicators[tf].get('volatility', {})
                    trend = indicators[tf].get('trend', {})
                    
                    # 볼린저 밴드 스퀴즈 확인
                    if volatility.get('bb_squeeze', False):
                        squeeze_count += 1
                    
                    # ATR 기반 변동성 확장 확인
                    atr_ratio = volatility.get('atr_ratio', 0)
                    if atr_ratio > 3.0:  # 평소보다 3배 이상 변동성
                        expansion_count += 1
                    
                    # 골든크로스/데스크로스 신호
                    if trend.get('golden_cross', False):
                        signals['golden_cross'] = True
                    if trend.get('death_cross', False):
                        signals['death_cross'] = True
                
                # 변동성 상태 결정
                if squeeze_count >= 2:
                    volatility_state['state'] = 'squeeze'
                    volatility_state['squeeze_detected'] = True
                elif expansion_count >= 2:
                    volatility_state['state'] = 'expansion'
                    volatility_state['expansion_detected'] = True
                elif squeeze_count >= 1 and expansion_count >= 1:
                    volatility_state['state'] = 'mixed'
                
                volatility_state['signals'] = signals
                
                self.logger.log_with_context(
                    'debug',
                    'v8.0 변동성 상태 분석 완료',
                    state=volatility_state['state'],
                    squeeze_count=squeeze_count,
                    expansion_count=expansion_count
                )
                
                return volatility_state
                
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 변동성 상태 분석 중 오류: {e}')
                return {'state': 'unknown', 'signals': {}}

    def _analyze_bitcoin_correlation_v8(self, market_data: Dict) -> Dict:
        """
        v8.0 비트코인 상관관계 분석 (BTC 급변동 감지)
        
        Args:
            market_data (Dict): 시장 데이터
            
        Returns:
            Dict: BTC 분석 결과
        """
        try:
            btc_analysis = {
                'btc_influence': '낮음',
                'btc_1h_change': 0,
                'btc_trend': 'neutral',
                'correlation_strength': 'low'
            }
            
            # BTC 1시간 변동률 추정 (실제로는 BTC 데이터가 필요하지만 XRP 변동성으로 추정)
            indicators = market_data.get('technical_indicators', {})
            h1_data = indicators.get('1h', {})
            
            if h1_data:
                # XRP의 1시간 변동성을 통해 BTC 영향도 추정
                volume_ratio = h1_data.get('volume', {}).get('volume_ratio', 1.0)
                atr_ratio = h1_data.get('volatility', {}).get('atr_ratio', 0)
                
                # 거래량 급증 + 변동성 급증 = BTC 영향 가능성 높음
                if volume_ratio > 3.0 and atr_ratio > 2.0:
                    btc_analysis['btc_influence'] = '매우높음'
                    btc_analysis['btc_1h_change'] = -2.5  # 추정값 (하락 추정)
                elif volume_ratio > 2.0 and atr_ratio > 1.5:
                    btc_analysis['btc_influence'] = '높음'
                    btc_analysis['btc_1h_change'] = -1.5
                elif volume_ratio > 1.5:
                    btc_analysis['btc_influence'] = '중간'
                    btc_analysis['btc_1h_change'] = -0.5
                
                # 추세 방향 추정
                trend_strength = h1_data.get('trend', {}).get('trend_strength', 0)
                if trend_strength > 1:
                    btc_analysis['btc_trend'] = 'bullish'
                elif trend_strength < -1:
                    btc_analysis['btc_trend'] = 'bearish'
            
            self.logger.log_with_context(
                'debug',
                'v8.0 BTC 상관관계 분석 완료',
                influence=btc_analysis['btc_influence'],
                estimated_change=f"{btc_analysis['btc_1h_change']:+.1f}%"
            )
            
            return btc_analysis
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 BTC 상관관계 분석 중 오류: {e}')
            return {'btc_influence': '알수없음', 'btc_1h_change': 0}

    def _check_market_structure_shift_v8(self, market_data: Dict) -> Dict:
        """
        v8.0 시장 구조 변화 감지
        
        Args:
            market_data (Dict): 시장 데이터
            
        Returns:
            Dict: 구조 변화 분석 결과
        """
        try:
            structure_analysis = {
                'structure_shift': False,
                'shift_type': 'none',
                'confidence': 'low',
                'key_levels': []
            }
            
            indicators = market_data.get('technical_indicators', {})
            current_price = market_data['current_price']
            
            # 4시간봉 기준 구조 변화 감지
            h4_data = indicators.get('4h', {})
            day_data = indicators.get('day', {})
            
            if h4_data and day_data:
                h4_trend = h4_data.get('trend', {})
                day_trend = day_data.get('trend', {})
                
                h4_strength = h4_trend.get('trend_strength', 0)
                day_strength = day_trend.get('trend_strength', 0)
                
                # 시간대별 추세 급변 감지
                if abs(h4_strength - day_strength) >= 3:
                    structure_analysis['structure_shift'] = True
                    structure_analysis['confidence'] = 'high'
                    
                    if h4_strength > day_strength:
                        structure_analysis['shift_type'] = 'bullish_breakout'
                    else:
                        structure_analysis['shift_type'] = 'bearish_breakdown'
                
                # 주요 지지/저항선 계산
                day_volatility = day_data.get('volatility', {})
                bb_upper = day_volatility.get('bb_upper', current_price * 1.05)
                bb_lower = day_volatility.get('bb_lower', current_price * 0.95)
                
                structure_analysis['key_levels'] = [
                    {'type': 'resistance', 'price': bb_upper},
                    {'type': 'support', 'price': bb_lower}
                ]
            
            self.logger.log_with_context(
                'debug',
                'v8.0 시장 구조 변화 분석 완료',
                shift_detected=structure_analysis['structure_shift'],
                shift_type=structure_analysis['shift_type']
            )
            
            return structure_analysis
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 시장 구조 변화 감지 중 오류: {e}')
            return {'structure_shift': False, 'shift_type': 'unknown'}

    def _determine_market_regime_v8(self, regime_score: float, volatility_analysis: Dict, 
                                   btc_analysis: Dict, structure_analysis: Dict) -> Dict:
        """
        v8.0 최종 시장 체제 결정
        
        Args:
            regime_score (float): 체제 점수
            volatility_analysis (Dict): 변동성 분석
            btc_analysis (Dict): BTC 분석
            structure_analysis (Dict): 구조 분석
            
        Returns:
            Dict: 체제 결정 결과
        """
        try:
            regime_result = {
                'regime': '애매한_혼조장',
                'risk_level': '중간',
                'approach': '보수적',
                'confidence': '낮음',
                'confidence_modifiers': []
            }
            
            # 1. 기본 체제 결정 (점수 기반)
            if regime_score >= 2.0:
                regime_result['regime'] = '명백한_상승장'
                regime_result['risk_level'] = '낮음'
                regime_result['approach'] = '적극적'
                regime_result['confidence'] = '높음'
            elif regime_score >= 1.0:
                regime_result['regime'] = '횡보_박스권'
                regime_result['risk_level'] = '중간'
                regime_result['approach'] = '중립적'
                regime_result['confidence'] = '중간'
            elif regime_score >= -1.0:
                regime_result['regime'] = '고변동성_혼조장'
                regime_result['risk_level'] = '높음'
                regime_result['approach'] = '신중함'
                regime_result['confidence'] = '중간'
            elif regime_score >= -2.0:
                regime_result['regime'] = '애매한_혼조장'
                regime_result['risk_level'] = '매우높음'
                regime_result['approach'] = '보수적'
                regime_result['confidence'] = '낮음'
            else:
                regime_result['regime'] = '명백한_하락장'
                regime_result['risk_level'] = '극도높음'
                regime_result['approach'] = '매매금지'
                regime_result['confidence'] = '높음'
            
            # 2. 수정자 적용
            modifiers = []
            
            # BTC 영향 수정자
            btc_influence = btc_analysis.get('btc_influence', '낮음')
            btc_change = btc_analysis.get('btc_1h_change', 0)
            
            if btc_influence in ['높음', '매우높음'] and btc_change < -2:
                modifiers.append('BTC강하락위험')
                if regime_result['confidence'] == '높음':
                    regime_result['confidence'] = '중간'
                elif regime_result['confidence'] == '중간':
                    regime_result['confidence'] = '낮음'
            
            # 구조 변화 수정자
            if structure_analysis.get('structure_shift', False):
                shift_type = structure_analysis.get('shift_type', 'none')
                modifiers.append(f'구조변화_{shift_type}')
                
                if shift_type == 'bearish_breakdown':
                    regime_result['confidence'] = '낮음'
                    regime_result['approach'] = '매우보수적'
            
            # 변동성 수정자
            volatility_state = volatility_analysis.get('state', 'normal')
            if volatility_state == 'expansion':
                modifiers.append('고변동성확장')
                regime_result['risk_level'] = '높음'
            elif volatility_state == 'squeeze':
                modifiers.append('변동성압축_돌파대기')
                # 스퀴즈는 긍정적 신호일 수 있음
            
            regime_result['confidence_modifiers'] = modifiers
            
            self.logger.log_with_context(
                'info',
                'v8.0 시장 체제 결정 완료',
                regime=regime_result['regime'],
                confidence=regime_result['confidence'],
                modifiers=modifiers
            )
            
            return regime_result
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 시장 체제 결정 중 오류: {e}')
            return {
                'regime': '분석실패',
                'risk_level': '극도높음',
                'approach': '매매금지',
                'confidence': '없음'
            }

    def _calculate_regime_reliability_v8(self, regime_result: Dict, btc_analysis: Dict, 
                                        structure_analysis: Dict) -> int:
        """
        v8.0 체제 신뢰도 점수 계산 (0-100)
        
        Args:
            regime_result (Dict): 체제 결정 결과
            btc_analysis (Dict): BTC 분석
            structure_analysis (Dict): 구조 분석
            
        Returns:
            int: 신뢰도 점수
        """
        try:
            base_confidence = {
                '높음': 85,
                '중간': 65,
                '낮음': 45,
                '없음': 20
            }
            
            reliability = base_confidence.get(regime_result['confidence'], 50)
            
            # 수정자들로 인한 신뢰도 조정
            modifiers = regime_result.get('confidence_modifiers', [])
            
            for modifier in modifiers:
                if 'BTC강하락위험' in str(modifier):
                    reliability -= 15
                elif '구조변화' in str(modifier):
                    reliability -= 10
                elif '고변동성확장' in str(modifier):
                    reliability -= 5
                elif '변동성압축' in str(modifier):
                    reliability += 5  # 압축은 예측 가능성 증가
            
            # BTC 영향도 추가 반영
            btc_influence = btc_analysis.get('btc_influence', '낮음')
            if btc_influence == '매우높음':
                reliability -= 10
            elif btc_influence == '높음':
                reliability -= 5
            
            # 구조 변화 신뢰도 추가 반영
            if structure_analysis.get('structure_shift', False):
                structure_confidence = structure_analysis.get('confidence', 'low')
                if structure_confidence == 'high':
                    reliability -= 5  # 구조 변화는 불확실성 증가
            
            # 범위 제한
            reliability = max(10, min(95, reliability))
            
            return reliability
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 체제 신뢰도 계산 중 오류: {e}')
            return 50

    def _generate_position_management_advice_v8(self, market_data: Dict) -> Optional[Dict]:
            """
            v8.0 XRP 보유 중 포지션 관리 전략 (트리거 기반 관리 변경)
            
            Args:
                market_data (Dict): 시장 데이터
                
            Returns:
                Optional[Dict]: 관리 전략 또는 None
            """
            try:
                self.logger.log_with_context('info', 'v8.0 XRP 보유 중 - 트리거 기반 포지션 관리 모드')
                
                position_status = market_data.get('position_status', {})
                active_trade_info = position_status.get('active_trade_info')
                
                if not active_trade_info:
                    self.logger.log_with_context('warning', 'v8.0 XRP 보유 중이지만 활성 거래 정보 없음')
                    return None
                
                # 현재 활성 거래 정보 추출
                (trade_id, current_target, current_stop, position_size, 
                entry_price, wick_defense_active) = active_trade_info[:6]
                
                current_price = market_data['current_price']
                
                # 현재 수익률 계산
                if entry_price and entry_price > 0:
                    current_profit_pct = ((current_price - entry_price) / entry_price * 100)
                else:
                    current_profit_pct = 0
                
                # v8.0 관리 트리거 검증
                trigger_analysis = self._validate_management_triggers_v8(market_data, {
                    'trade_id': trade_id,
                    'current_target': current_target,
                    'current_stop': current_stop,
                    'entry_price': entry_price,
                    'current_profit_pct': current_profit_pct
                })
                
                if not trigger_analysis['change_needed']:
                    # 변경 불필요 - 현재 전략 유지
                    return self._create_hold_strategy_v8(market_data, trigger_analysis)
                else:
                    # 변경 필요 - AI 기반 새로운 관리 전략 요청
                    self.logger.log_with_context(
                        'info',
                        'v8.0 포지션 관리 변경 트리거 발동',
                        trigger=trigger_analysis['trigger_type'],
                        reason=trigger_analysis['trigger_reason']
                    )
                    
                    return self._request_ai_management_analysis_v8(market_data, trigger_analysis)
                
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 포지션 관리 전략 생성 중 오류: {e}')
                return None

    def _validate_management_triggers_v8(self, market_data: Dict, current_trade: Dict) -> Dict:
        """
        v8.0 포지션 관리 변경 트리거 검증
        
        Args:
            market_data (Dict): 시장 데이터
            current_trade (Dict): 현재 거래 정보
            
        Returns:
            Dict: 트리거 분석 결과
        """
        try:
            trigger_analysis = {
                'change_needed': False,
                'trigger_type': 'NONE',
                'trigger_reason': '',
                'urgency_level': 'low',
                'evidence': []
            }
            
            current_price = market_data['current_price']
            current_profit_pct = current_trade['current_profit_pct']
            entry_price = current_trade['entry_price']
            
            # 1. 급격한 수익 발생 트리거 (15% 이상)
            if current_profit_pct >= 15:
                trigger_analysis.update({
                    'change_needed': True,
                    'trigger_type': 'PROFIT_SURGE',
                    'trigger_reason': f'급격한 수익 발생 ({current_profit_pct:+.1f}%) - 목표가 상향 검토 필요',
                    'urgency_level': 'medium',
                    'evidence': [f'현재 수익률 {current_profit_pct:+.1f}%']
                })
                return trigger_analysis
            
            # 2. 급격한 손실 발생 트리거 (-8% 이상)
            if current_profit_pct <= -8:
                trigger_analysis.update({
                    'change_needed': True,
                    'trigger_type': 'LOSS_SURGE',
                    'trigger_reason': f'급격한 손실 발생 ({current_profit_pct:+.1f}%) - 손절가 재검토 필요',
                    'urgency_level': 'high',
                    'evidence': [f'현재 손실률 {current_profit_pct:+.1f}%']
                })
                return trigger_analysis
            
            # 3. 시장 체제 급변 트리거
            market_regime = self._analyze_market_regime_v8(market_data)
            regime = market_regime.get('regime', '')
            
            if regime in ['명백한_하락장', '고변동성_혼조장']:
                # BTC 급락 확인
                btc_analysis = market_regime.get('btc_analysis', {})
                btc_change = btc_analysis.get('btc_1h_change', 0)
                
                if btc_change < -3:
                    trigger_analysis.update({
                        'change_needed': True,
                        'trigger_type': 'MARKET_REGIME_SHIFT',
                        'trigger_reason': f'시장 체제 급변 ({regime}) + BTC 급락 ({btc_change:+.1f}%) - 방어적 조정 필요',
                        'urgency_level': 'high',
                        'evidence': [f'체제: {regime}', f'BTC 변동: {btc_change:+.1f}%']
                    })
                    return trigger_analysis
            
            # 4. XRP 전문가 시스템 트리거
            xrp_analysis = market_data.get('xrp_expert_analysis', {})
            wick_risk = xrp_analysis.get('wick_pattern_risk', 'low')
            energy_compression = xrp_analysis.get('energy_compression_detected', False)
            breakout_prob = xrp_analysis.get('breakout_probability', 0)
            
            if wick_risk == 'high':
                trigger_analysis.update({
                    'change_needed': True,
                    'trigger_type': 'XRP_EXPERT_WARNING',
                    'trigger_reason': f'XRP 전문가 시스템 위험 신호 - 위꼬리 패턴 위험도 {wick_risk}',
                    'urgency_level': 'medium',
                    'evidence': [f'위꼬리 위험: {wick_risk}']
                })
                return trigger_analysis
            
            if energy_compression and breakout_prob > 0.8:
                trigger_analysis.update({
                    'change_needed': True,
                    'trigger_type': 'XRP_EXPERT_OPPORTUNITY',
                    'trigger_reason': f'XRP 에너지 압축 돌파 임박 (확률 {breakout_prob:.0%}) - 목표가 상향 검토',
                    'urgency_level': 'medium',
                    'evidence': [f'돌파 확률: {breakout_prob:.0%}']
                })
                return trigger_analysis
            
            # 5. 기술적 지표 극단 트리거
            indicators = market_data.get('technical_indicators', {})
            h1_momentum = indicators.get('1h', {}).get('momentum', {})
            rsi = h1_momentum.get('rsi', 50)
            
            if rsi > 80:  # 극도 과매수
                trigger_analysis.update({
                    'change_needed': True,
                    'trigger_type': 'TECHNICAL_EXTREME',
                    'trigger_reason': f'극도 과매수 상태 (RSI {rsi:.1f}) - 부분 매도 또는 목표가 하향 검토',
                    'urgency_level': 'medium',
                    'evidence': [f'RSI: {rsi:.1f}']
                })
                return trigger_analysis
            elif rsi < 20:  # 극도 과매도
                trigger_analysis.update({
                    'change_needed': True,
                    'trigger_type': 'TECHNICAL_EXTREME',
                    'trigger_reason': f'극도 과매도 상태 (RSI {rsi:.1f}) - 손절가 하향 또는 매수 추가 검토',
                    'urgency_level': 'medium',
                    'evidence': [f'RSI: {rsi:.1f}']
                })
                return trigger_analysis
            
            # 6. 시간 기반 트리거 (24시간 이상 보유)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT entry_timestamp FROM trades 
                    WHERE trade_id = ? AND status = 'ACTIVE'
                ''', (current_trade['trade_id'],))
                
                result = cursor.fetchone()
                if result:
                    entry_time = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
                    holding_hours = (datetime.now() - entry_time).total_seconds() / 3600
                    
                    if holding_hours > 48:  # 48시간 이상 보유
                        trigger_analysis.update({
                            'change_needed': True,
                            'trigger_type': 'TIME_BASED',
                            'trigger_reason': f'장기 보유 ({holding_hours:.1f}시간) - 전략 재검토 필요',
                            'urgency_level': 'low',
                            'evidence': [f'보유 시간: {holding_hours:.1f}시간']
                        })
                        return trigger_analysis
            
            # 트리거 없음 - 현재 전략 유지
            trigger_analysis['trigger_reason'] = '현재 전략 유지 - 트리거 조건 미달성'
            
            self.logger.log_with_context(
                'debug',
                'v8.0 포지션 관리 트리거 검증 완료',
                result='변경불필요',
                current_profit=f'{current_profit_pct:+.1f}%'
            )
            
            return trigger_analysis
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 관리 트리거 검증 중 오류: {e}')
            return {'change_needed': False, 'trigger_type': 'ERROR', 'trigger_reason': '검증 실패'}

    def _create_hold_strategy_v8(self, market_data: Dict, trigger_analysis: Dict) -> Dict:
        """
        v8.0 현재 전략 유지 응답 생성
        
        Args:
            market_data (Dict): 시장 데이터
            trigger_analysis (Dict): 트리거 분석 결과
            
        Returns:
            Dict: 유지 전략 응답
        """
        try:
            current_price = market_data['current_price']
            position_status = market_data.get('position_status', {})
            active_trade_info = position_status.get('active_trade_info')
            
            if active_trade_info:
                (trade_id, current_target, current_stop, position_size, 
                 entry_price, wick_defense_active) = active_trade_info[:6]
                
                current_profit_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            else:
                current_target = current_price * 1.05
                current_stop = current_price * 0.95
                current_profit_pct = 0
            
            return {
                "market_analysis": {
                    "regime_verification": f"v8.0 포지션 관리 모드 - 현재 전략 유지",
                    "trend_group": f"현재 수익률: {current_profit_pct:+.1f}%",
                    "momentum_group": f"목표가: {current_target:,.0f}원",
                    "volatility_group": f"손절가: {current_stop:,.0f}원",
                    "volume_group": f"위꼬리 방어: {'활성화' if wick_defense_active else '비활성화'}",
                    "overall_confidence": "현재 전략 유지",
                    "market_condition": "관리 트리거 미발동"
                },
                "risk_assessment": {
                    "risk_level": "현재 유지",
                    "position_size": f"보유 중: {position_size:.4f} XRP",
                    "max_holding_time": "트리거 기반 관리",
                    "key_risks": trigger_analysis['trigger_reason']
                },
                "entry_price": 0,  # 이미 진입 완료
                "target_price": current_target,
                "stop_loss_price": current_stop,
                "entry_reason": "이미 진입 완료 - 포지션 관리 모드",
                "target_reason": f"현재 목표가 {current_target:,.0f}원 유지",
                "stop_loss_reason": f"현재 손절가 {current_stop:,.0f}원 유지",
                "sell_strategy": "기존 계획대로 목표가 도달 시 매도 또는 손절가 도달 시 위꼬리 방어 적용",
                "lessons_applied": "v8.0 트리거 기반 관리 - 불필요한 변경 방지로 안정성 확보",
                "regime_adaptation": "현재 시장 상황에서 기존 전략이 여전히 유효함",
                "signal_grade": "HOLD",
                "change_trigger": "NONE",
                "trigger_evidence": trigger_analysis.get('evidence', [])
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 유지 전략 생성 중 오류: {e}')
            return {"entry_price": 0, "target_price": 0, "stop_loss_price": 0}

    def _request_ai_management_analysis_v8(self, market_data: Dict, trigger_analysis: Dict) -> Optional[Dict]:
        """
        v8.0 AI 기반 포지션 관리 변경 분석 요청
        
        Args:
            market_data (Dict): 시장 데이터
            trigger_analysis (Dict): 트리거 분석 결과
            
        Returns:
            Optional[Dict]: AI 관리 분석 결과 또는 None
        """
        try:
            self.logger.log_with_context(
                'info',
                'v8.0 AI 기반 포지션 관리 변경 분석 요청',
                trigger=trigger_analysis['trigger_type'],
                urgency=trigger_analysis['urgency_level']
            )
            
            # 현재 활성 교훈 로드
            current_lessons = self.get_current_lessons_for_strategy_v8()
            
            # AI 관리 분석 프롬프트 생성
            management_prompt = self._create_management_analysis_prompt_v8(
                market_data, trigger_analysis, current_lessons
            )
            
            # GPT 호출
            response = self.openai_client.chat.completions.create(
                model=self.config_manager.get('ai.model'),
                messages=[
                    {
                        "role": "system",
                        "content": self._get_management_analysis_system_prompt_v8()
                    },
                    {
                        "role": "user",
                        "content": management_prompt
                    }
                ],
                max_tokens=self.config_manager.get('ai.max_tokens'),
                temperature=self.config_manager.get('ai.temperature')
            )
            
            ai_analysis = response.choices[0].message.content
            
            # AI 응답 파싱
            parsed_management = self._parse_ai_management_response_v8(ai_analysis, market_data, trigger_analysis)
            
            if parsed_management:
                self.logger.log_with_context(
                    'info',
                    'v8.0 AI 포지션 관리 분석 완료',
                    new_target=f'{parsed_management.get("target_price", 0):,.0f}원',
                    new_stop=f'{parsed_management.get("stop_loss_price", 0):,.0f}원',
                    trigger=trigger_analysis['trigger_type']
                )
                
                return parsed_management
            else:
                self.logger.log_with_context('error', 'v8.0 AI 관리 응답 파싱 실패')
                return None
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 AI 포지션 관리 분석 요청 중 오류: {e}')
            return None

    def _create_management_analysis_prompt_v8(self, market_data: Dict, trigger_analysis: Dict, 
                                             current_lessons: str) -> str:
        """
        v8.0 포지션 관리 분석 프롬프트 생성
        
        Args:
            market_data (Dict): 시장 데이터
            trigger_analysis (Dict): 트리거 분석
            current_lessons (str): 현재 교훈
            
        Returns:
            str: 관리 분석 프롬프트
        """
        current_price = market_data['current_price']
        position_status = market_data.get('position_status', {})
        active_trade_info = position_status.get('active_trade_info')
        
        if active_trade_info:
            (trade_id, current_target, current_stop, position_size, 
             entry_price, wick_defense_active) = active_trade_info[:6]
            current_profit_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        else:
            current_target = current_price * 1.05
            current_stop = current_price * 0.95
            entry_price = current_price
            current_profit_pct = 0
            
        return f"""
# OMNI-XRP v8.0 포지션 관리 변경 요청

## 🚨 변경 트리거 발동
**트리거 타입**: {trigger_analysis['trigger_type']}
**긴급도**: {trigger_analysis['urgency_level']}
**발동 사유**: {trigger_analysis['trigger_reason']}
**증거**: {', '.join(trigger_analysis.get('evidence', []))}

## 📊 현재 포지션 상황
**진입가**: {entry_price:,.0f}원
**현재가**: {current_price:,.0f}원
**현재 수익률**: {current_profit_pct:+.1f}%
**보유 수량**: {position_size:.4f} XRP

## 📈 기존 관리 계획
**현재 목표가**: {current_target:,.0f}원
**현재 손절가**: {current_stop:,.0f}원
**위꼬리 방어**: {'활성화' if wick_defense_active else '비활성화'}

## 🎓 적용해야 할 교훈
{current_lessons}

## 🔄 관리 변경 요청

위 트리거 상황에 맞춰 **목표가와 손절가를 조정**해주세요.

### 필수 고려사항
1. **현재 수익률 {current_profit_pct:+.1f}% 상황에서의 최적 조정**
2. **v8.0 위꼬리 방어 시스템 지속 활용**
3. **트리거 타입 '{trigger_analysis['trigger_type']}'에 특화된 대응**
4. **축적된 교훈 반영으로 과거 실수 방지**
5. **과도한 욕심 금지 - 현실적인 조정 범위**

### 출력 형식

**새로운 목표가**: [구체적 가격]원
**목표가 변경 근거**: [왜 이 가격으로 조정하는지 3가지 이유]

**새로운 손절가**: [구체적 가격]원  
**손절가 변경 근거**: [왜 이 가격으로 조정하는지 3가지 이유]

**관리 전략**: [구체적인 포지션 관리 방법]

**적용된 교훈**: [이번 조정에서 특별히 적용한 교훈 3가지]

**리스크 평가**: 
- 조정 후 예상 결과: [성공/실패 시나리오]
- 최악의 경우 최대 손실: [%]
- 최선의 경우 최대 수익: [%]

현재 수익률이 {current_profit_pct:+.1f}%인 상황에서 **현실적이고 안전한 조정**을 해주세요.
"""

    def _get_management_analysis_system_prompt_v8(self) -> str:
        """
        v8.0 포지션 관리 분석 시스템 프롬프트
        
        Returns:
            str: 시스템 프롬프트
        """
        return """당신은 OMNI-XRP v8.0의 포지션 관리 전문가입니다.

핵심 역할:
1. **트리거 발동 상황**에서 목표가/손절가의 **최적 조정** 결정
2. **현재 수익률**을 고려한 **현실적이고 안전한** 관리 변경
3. **과거 교훈**을 적극 반영하여 **반복되는 실수 방지**
4. **v8.0 위꼬리 방어 시스템**과 조화되는 리스크 관리

전문 분야:
- **트리거 타입별 최적 대응법** (수익 급증, 손실 급증, 시장 급변 등)
- **수익률 구간별 관리 전략** (-10% ~ +20% 각 구간별 최적 조정)
- **XRP 시장 특성**을 고려한 목표가/손절가 재배치
- **심리적 함정 방지** (과도한 욕심, 성급한 손절 등)

중요 원칙:
- **현재 수익률**에 따른 단계별 접근
- **트리거의 긴급도**에 맞는 조정 강도
- **과거 성공/실패 교훈**의 적극적 반영
- **리스크 우선 사고**: 수익 확장보다 손실 방지가 우선

목표: v8.0 시스템이 **변화하는 시장에 유연하게 적응**하면서도 **안정적인 수익**을 확보할 수 있는 관리 전략 제공"""

    def _parse_ai_management_response_v8(self, ai_response: str, market_data: Dict, 
                                        trigger_analysis: Dict) -> Optional[Dict]:
        """
        v8.0 AI 포지션 관리 응답 파싱
        
        Args:
            ai_response (str): AI 응답
            market_data (Dict): 시장 데이터
            trigger_analysis (Dict): 트리거 분석
            
        Returns:
            Optional[Dict]: 파싱된 관리 전략 또는 None
        """
        try:
            current_price = market_data['current_price']
            
            # 가격 추출
            target_match = re.search(r'새로운 목표가[:\s]*([0-9,]+)원', ai_response)
            stop_match = re.search(r'새로운 손절가[:\s]*([0-9,]+)원', ai_response)
            
            if not (target_match and stop_match):
                self.logger.log_with_context('error', 'v8.0 AI 관리 응답에서 가격 정보 추출 실패')
                return None
            
            new_target_price = float(target_match.group(1).replace(',', ''))
            new_stop_price = float(stop_match.group(1).replace(',', ''))
            
            # 관리 변경 유효성 검증
            if not self._validate_management_prices_v8(current_price, new_target_price, new_stop_price):
                return None
            
            # 근거 추출
            target_reason = self._extract_reason_v8(ai_response, '목표가 변경 근거')
            stop_reason = self._extract_reason_v8(ai_response, '손절가 변경 근거')
            management_strategy = self._extract_reason_v8(ai_response, '관리 전략')
            lessons_applied = self._extract_reason_v8(ai_response, '적용된 교훈')
            
            return {
                'entry_price': 0,  # 관리 모드에서는 진입가 변경 없음
                'target_price': new_target_price,
                'stop_loss_price': new_stop_price,
                'target_reason': target_reason or f"v8.0 AI 관리: {trigger_analysis['trigger_type']} 트리거 대응 목표가 조정",
                'stop_loss_reason': stop_reason or f"v8.0 AI 관리: {trigger_analysis['trigger_type']} 트리거 대응 손절가 조정",
                'sell_strategy': management_strategy or "조정된 목표가/손절가 기준 관리",
                'lessons_applied': lessons_applied or f"v8.0 트리거 기반 관리 - {trigger_analysis['trigger_type']} 대응",
                'change_trigger': trigger_analysis['trigger_type'],
                'trigger_evidence': ', '.join(trigger_analysis.get('evidence', [])),
                'regime_adaptation': f"트리거 '{trigger_analysis['trigger_type']}' 상황에 최적화된 관리 전략"
            }
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 AI 관리 응답 파싱 중 오류: {e}')
            return None

    def _validate_management_prices_v8(self, current_price: float, new_target: float, new_stop: float) -> bool:
        """
        v8.0 관리 변경 가격 유효성 검증
        
        Args:
            current_price (float): 현재 가격
            new_target (float): 새로운 목표가
            new_stop (float): 새로운 손절가
            
        Returns:
            bool: 유효성 여부
        """
        try:
            # 1. 기본 논리 검증
            if not (new_stop < current_price < new_target):
                self.logger.log_with_context('error', 'v8.0 관리 가격 논리 오류: 손절가 < 현재가 < 목표가 위반')
                return False
            
            # 2. 현실성 검증 (현재가 대비 ±30% 범위) - 관리 모드는 더 관대
            tolerance = 0.30
            min_price = current_price * (1 - tolerance)
            max_price = current_price * (1 + tolerance)
            
            if not (min_price <= new_target <= max_price * 1.5):  # 목표가는 더 관대
                self.logger.log_with_context(
                    'warning', 
                    f'v8.0 새로운 목표가 현실성 경고: {new_target:,.0f}원'
                )
            
            if not (min_price * 0.7 <= new_stop <= max_price):  # 손절가도 더 관대
                self.logger.log_with_context(
                    'warning', 
                    f'v8.0 새로운 손절가 현실성 경고: {new_stop:,.0f}원'
                )
            
            self.logger.log_with_context(
                'info',
                'v8.0 관리 가격 유효성 검증 통과',
                new_target=f'{new_target:,.0f}원',
                new_stop=f'{new_stop:,.0f}원'
            )
            
            return True
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 관리 가격 유효성 검증 중 오류: {e}')
            return False

## =============================================================================
    # Part 6: 학습 시스템 및 회고 분석
## =============================================================================

    def _perform_immediate_reflection_v8(self, trade_id: int) -> None:
            """
            v8.0 즉시 회고 분석 실행 (학습 시스템 통합)
            
            Args:
                trade_id (int): 완료된 거래 ID
            """
            try:
                self.logger.log_with_context('info', f'v8.0 거래 ID {trade_id} 즉시 회고 분석 시작')
                
                # 상태를 ANALYZING으로 변경
                context = {'operation': 'reflection', 'trade_id': trade_id}
                if not self.state_manager.set_state(SystemState.ANALYZING, context):
                    self.logger.log_with_context('warning', '회고를 위한 상태 변경 실패')
                    return
                
                try:
                    # 1단계: 개별 거래 회고 생성
                    reflection_content = self._generate_individual_reflection_v8(trade_id)
                    if reflection_content:
                        # 회고 파일 저장
                        reflection_file = self._save_reflection_file_v8(trade_id, reflection_content)
                        
                        # 2단계: 교훈 추출 및 통합
                        self._extract_and_integrate_lessons_v8(trade_id, reflection_content)
                        
                        self.logger.log_with_context(
                            'info', 
                            'v8.0 즉시 회고 분석 완료',
                            reflection_file=reflection_file
                        )
                    else:
                        self.logger.log_with_context('error', 'v8.0 회고 생성 실패')
                        
                finally:
                    # 상태 복원
                    self.state_manager.set_state(SystemState.IDLE)
                    
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 즉시 회고 분석 중 오류: {e}')
                self.state_manager.set_state(SystemState.IDLE)

    def _generate_individual_reflection_v8(self, trade_id: int) -> Optional[str]:
        """
        v8.0 개별 거래 회고 생성 (GPT 기반)
        
        Args:
            trade_id (int): 거래 ID
            
        Returns:
            Optional[str]: 회고 내용 또는 None
        """
        try:
            # 거래 상세 정보 조회
            trade_details = self._get_trade_details_v8(trade_id)
            if not trade_details:
                return None
            
            # 포지션 히스토리 추적
            position_history = self._trace_position_history_v8(trade_id)
            
            # 시장 맥락 분석
            market_context = self._analyze_trade_market_context_v8(trade_details)
            
            # 현재 활성 교훈 로드
            current_lessons = self._load_current_lessons()
            
            # GPT 회고 프롬프트 생성
            reflection_prompt = self._create_reflection_prompt_v8(
                trade_details, position_history, market_context, current_lessons
            )
            
            # GPT 호출
            response = self.openai_client.chat.completions.create(
                model=self.config_manager.get('ai.model'),
                messages=[
                    {
                        "role": "system",
                        "content": self._get_reflection_system_prompt_v8()
                    },
                    {
                        "role": "user", 
                        "content": reflection_prompt
                    }
                ],
                max_tokens=self.config_manager.get('ai.max_tokens'),
                temperature=self.config_manager.get('ai.temperature')
            )
            
            reflection_content = response.choices[0].message.content
            
            self.logger.log_with_context(
                'info',
                'v8.0 개별 거래 회고 생성 완료',
                trade_id=trade_id,
                content_length=len(reflection_content)
            )
            
            return reflection_content
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 개별 거래 회고 생성 중 오류: {e}')
            return None

    def _get_trade_details_v8(self, trade_id: int) -> Optional[Dict]:
        """
        v8.0 거래 상세 정보 조회
        
        Args:
            trade_id (int): 거래 ID
            
        Returns:
            Optional[Dict]: 거래 상세 정보 또는 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM trades WHERE trade_id = ? AND status = 'COMPLETED'
                ''', (trade_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # 컬럼명 가져오기
                columns = [description[0] for description in cursor.description]
                
                # 딕셔너리로 변환
                trade_details = dict(zip(columns, row))
                
                return trade_details
                
        except Exception as e:
            self.logger.log_with_context('error', f'거래 상세 정보 조회 중 오류: {e}')
            return None

    def _trace_position_history_v8(self, trade_id: int) -> Dict:
        """
        v8.0 포지션 히스토리 추적 (확장된 정보 포함)
        
        Args:
            trade_id (int): 거래 ID
            
        Returns:
            Dict: 포지션 히스토리
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 완료된 거래의 포지션 크기 확인
                cursor.execute('''
                    SELECT position_size_xrp, entry_timestamp, exit_timestamp 
                    FROM trades WHERE trade_id = ?
                ''', (trade_id,))
                
                result = cursor.fetchone()
                if not result:
                    return {}
                
                position_size, entry_time, exit_time = result
                
                # 관련된 모든 거래 조회 (같은 포지션 크기 또는 시간대)
                cursor.execute('''
                    SELECT trade_id, status, planned_entry_price, planned_target_price, 
                           planned_stop_loss, entry_reason, target_reason, stop_loss_reason,
                           plan_timestamp, wick_defense_active, wick_defense_result,
                           change_trigger, trigger_evidence
                    FROM trades 
                    WHERE (position_size_xrp = ? OR trade_id = ?)
                    AND plan_timestamp BETWEEN ? AND ?
                    ORDER BY plan_timestamp ASC
                ''', (position_size, trade_id, 
                      entry_time, exit_time if exit_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                
                related_trades = cursor.fetchall()
                
                # 히스토리 구성
                history = {
                    'original_entry': None,
                    'management_changes': [],
                    'wick_defense_events': [],
                    'final_exit': None
                }
                
                for trade in related_trades:
                    (t_id, status, plan_entry, plan_target, plan_stop, 
                     entry_reason, target_reason, stop_reason, plan_time,
                     wick_defense, wick_result, change_trigger, trigger_evidence) = trade
                    
                    if status == 'ACTIVE' and t_id == trade_id:
                        history['original_entry'] = {
                            'trade_id': t_id,
                            'entry_reason': entry_reason,
                            'original_target': plan_target,
                            'original_stop': plan_stop,
                            'plan_time': plan_time
                        }
                    elif status == 'SUPERSEDED':
                        history['management_changes'].append({
                            'trade_id': t_id,
                            'plan_time': plan_time,
                            'target_price': plan_target,
                            'stop_price': plan_stop,
                            'change_trigger': change_trigger,
                            'trigger_evidence': trigger_evidence
                        })
                    
                    if wick_defense and wick_result:
                        history['wick_defense_events'].append({
                            'trade_id': t_id,
                            'result': wick_result,
                            'plan_time': plan_time
                        })
                
                if trade_id:
                    history['final_exit'] = {
                        'trade_id': trade_id,
                        'exit_time': exit_time
                    }
                
                return history
                
        except Exception as e:
            self.logger.log_with_context('error', f'포지션 히스토리 추적 중 오류: {e}')
            return {}

    def _analyze_trade_market_context_v8(self, trade_details: Dict) -> str:
        """
        v8.0 거래 당시 시장 맥락 분석
        
        Args:
            trade_details (Dict): 거래 상세 정보
            
        Returns:
            str: 시장 맥락 분석 결과
        """
        try:
            entry_time = trade_details.get('entry_timestamp')
            exit_time = trade_details.get('exit_timestamp')
            entry_price = trade_details.get('actual_entry_price')
            exit_price = trade_details.get('actual_exit_price')
            
            context = f"""
거래 시장 맥락 분석:

진입 시점: {entry_time}
진입가: {entry_price:,.0f}원
청산 시점: {exit_time}
청산가: {exit_price:,.0f}원

확률론적 정보:
- 체크리스트 점수: {trade_details.get('checklist_score', 0):.1f}/5.5
- 신호 신뢰도 승수: {trade_details.get('signal_confidence_multiplier', 0):.2f}
- 계산된 포지션 비율: {trade_details.get('calculated_position_ratio', 0):.0%}

XRP 전문가 정보:
- 위꼬리 방어 활성: {trade_details.get('wick_defense_active', False)}
- 위꼬리 방어 결과: {trade_details.get('wick_defense_result', 'NONE')}
- 에너지 압축 감지: {trade_details.get('energy_compression_detected', False)}
- XRP 패턴 타입: {trade_details.get('xrp_pattern_type', 'NONE')}

결과:
- 최종 수익률: {trade_details.get('profit_rate_pct', 0):+.2f}%
- 순수익: {trade_details.get('net_profit_krw', 0):+,.0f}원
- 거래 결과: {trade_details.get('trade_result', 'UNKNOWN')}
"""
            return context
            
        except Exception as e:
            self.logger.log_with_context('error', f'거래 시장 맥락 분석 중 오류: {e}')
            return "시장 맥락 분석 실패"

    def _load_current_lessons(self) -> str:
        """
        현재 활성 교훈 로드
        
        Returns:
            str: 현재 교훈 내용
        """
        try:
            if os.path.exists(self.lessons_file):
                with open(self.lessons_file, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                return "아직 축적된 교훈이 없습니다."
                
        except Exception as e:
            self.logger.log_with_context('error', f'현재 교훈 로드 중 오류: {e}')
            return "교훈 로드 실패"

    def _create_reflection_prompt_v8(self, trade_details: Dict, position_history: Dict, 
                                    market_context: str, current_lessons: str) -> str:
        """
        v8.0 회고 프롬프트 생성
        
        Args:
            trade_details (Dict): 거래 상세 정보
            position_history (Dict): 포지션 히스토리
            market_context (str): 시장 맥락
            current_lessons (str): 현재 교훈
            
        Returns:
            str: 회고 프롬프트
        """
        return f"""
# OMNI-XRP v8.0 거래 회고 분석 요청

## 🎯 분석 목표
다음 완료된 거래에 대해 **즉시 적용 가능한 구체적 교훈**을 추출해주세요.

## 📊 거래 기본 정보
{market_context}

## 📈 포지션 관리 히스토리
원본 진입: {position_history.get('original_entry', {})}
관리 변경: {len(position_history.get('management_changes', []))}회
위꼬리 방어 이벤트: {len(position_history.get('wick_defense_events', []))}회

## 🎓 기존 축적된 교훈
{current_lessons}

## 🔍 상세 분석 요청

다음 **5가지 핵심 관점**에서 이 거래를 심층 분석해주세요:

### 1️⃣ v8.0 확률론적 접근 평가
- 체크리스트 점수({trade_details.get('checklist_score', 0):.1f}/5.5)의 적절성
- 신호 신뢰도 승수({trade_details.get('signal_confidence_multiplier', 0):.2f})의 효과성
- 포지션 사이징({trade_details.get('calculated_position_ratio', 0):.0%})의 타당성

### 2️⃣ XRP 전문가 시스템 효과성
- 위꼬리 방어 시스템의 작동 결과
- 에너지 압축 등 XRP 특화 분석의 정확도
- XRP 패턴 인식의 유용성

### 3️⃣ 포지션 관리 적절성
- 목표가/손절가 설정의 현실성
- 관리 변경 결정의 타이밍과 효과
- 트리거 기반 관리의 성과

### 4️⃣ 시장 타이밍 최적성
- 진입 타이밍의 적절성
- 보유 기간의 최적성
- 청산 타이밍의 효율성

### 5️⃣ 기존 교훈 적용도
- 축적된 교훈이 잘 적용되었는지
- 반복되는 실수가 있었는지
- 새로운 패턴 발견 여부

## 📝 최종 출력 요구사항

위 분석을 바탕으로 다음 형식으로 정리해주세요:

### 핵심 성과 (잘한 점 3가지)
1. [구체적 성과와 이유]
2. [구체적 성과와 이유]  
3. [구체적 성과와 이유]

### 개선 필요 사항 (문제점 3가지)
1. [구체적 문제와 원인]
2. [구체적 문제와 원인]
3. [구체적 문제와 원인]

### 즉시 적용할 교훈 (액션 아이템 5가지)
1. [구체적 상황] → [명확한 액션] → [적용 방법]
2. [구체적 상황] → [명확한 액션] → [적용 방법]
3. [구체적 상황] → [명확한 액션] → [적용 방법]
4. [구체적 상황] → [명확한 액션] → [적용 방법]
5. [구체적 상황] → [명확한 액션] → [적용 방법]

**각 교훈은 다음 거래에서 바로 체크하고 적용할 수 있는 명확하고 실행 가능한 내용이어야 합니다.**
"""

    def _get_reflection_system_prompt_v8(self) -> str:
        """
        v8.0 회고 시스템 프롬프트
        
        Returns:
            str: 시스템 프롬프트
        """
        return """당신은 OMNI-XRP v8.0의 전문 거래 회고 분석가입니다.

핵심 역할:
1. 완료된 거래에서 **즉시 적용 가능한 구체적 교훈** 추출
2. v8.0의 확률론적 접근과 XRP 전문가 시스템의 효과성 평가
3. 다음 거래에서 **바로 체크하고 적용할 수 있는 액션 아이템** 제시
4. 반복되는 패턴(성공/실패)의 발견 및 규칙화

분석 원칙:
- 복잡한 기술분석보다는 **실전에서 바로 쓸 수 있는 교훈** 중심
- 감정적, 심리적 요소까지 포함한 **인간적인 거래 개선점** 발견
- 이론이 아닌 **실전에서 검증 가능한 개선 방향** 제시
- 다음 거래 시 **체크리스트 형태로 바로 적용** 가능한 내용

목표: v8.0 시스템이 스스로 학습하고 발전할 수 있는 구체적이고 실행 가능한 개선점 도출"""

    def _save_reflection_file_v8(self, trade_id: int, reflection_content: str) -> str:
        """
        v8.0 회고 파일 저장
        
        Args:
            trade_id (int): 거래 ID
            reflection_content (str): 회고 내용
            
        Returns:
            str: 저장된 파일 경로
        """
        try:
            # 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.reflections_dir}/reflection_trade_{trade_id}_{timestamp}.md"
            
            # 회고 내용을 마크다운 형식으로 저장
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# OMNI-XRP v8.0 거래 회고 분석\n\n")
                f.write(f"**거래 ID**: {trade_id}\n")
                f.write(f"**분석 시간**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**분석 시스템**: OMNI-XRP v8.0 학습 시스템\n\n")
                f.write("---\n\n")
                f.write(reflection_content)
                f.write("\n\n---\n")
                f.write(f"*Generated by OMNI-XRP v8.0 Learning System*\n")
            
            self.logger.log_with_context(
                'info',
                'v8.0 회고 파일 저장 완료',
                trade_id=trade_id,
                filename=filename
            )
            
            return filename
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 회고 파일 저장 중 오류: {e}')
            return ""

    def _extract_and_integrate_lessons_v8(self, trade_id: int, reflection_content: str) -> None:
        """
        v8.0 교훈 추출 및 통합 (핵심 학습 시스템)
        
        Args:
            trade_id (int): 거래 ID
            reflection_content (str): 회고 내용
        """
        try:
            self.logger.log_with_context('info', f'v8.0 교훈 추출 및 통합 시작 - 거래 ID {trade_id}')
            
            # 1. 모든 기존 회고 파일 수집
            all_reflections = self._collect_all_reflections_v8()
            
            # 2. 현재 교훈 로드
            current_lessons = self._load_current_lessons()
            
            # 3. GPT를 통한 교훈 통합 분석
            integrated_lessons = self._generate_integrated_lessons_v8(
                all_reflections, current_lessons, reflection_content
            )
            
            if integrated_lessons:
                # 4. 새로운 교훈 파일 저장
                self._save_updated_lessons_v8(integrated_lessons)
                
                # 5. 학습 데이터 테이블에 기록
                self._record_learning_data_v8(trade_id, integrated_lessons)
                
                self.logger.log_with_context('info', 'v8.0 교훈 추출 및 통합 완료')
            else:
                self.logger.log_with_context('error', 'v8.0 교훈 통합 생성 실패')
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 교훈 추출 및 통합 중 오류: {e}')

    def _collect_all_reflections_v8(self) -> str:
        """
        v8.0 모든 회고 파일 수집
        
        Returns:
            str: 통합된 회고 내용
        """
        try:
            all_reflections = []
            
            if os.path.exists(self.reflections_dir):
                reflection_files = [f for f in os.listdir(self.reflections_dir) if f.endswith('.md')]
                
                # 최근 10개 파일만 처리 (토큰 제한 고려)
                reflection_files.sort(reverse=True)
                recent_files = reflection_files[:10]
                
                for filename in recent_files:
                    file_path = os.path.join(self.reflections_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            all_reflections.append(f"## {filename}\n{content}\n")
                    except Exception as e:
                        self.logger.log_with_context('warning', f'회고 파일 읽기 실패: {filename}: {e}')
            
            return "\n".join(all_reflections)
            
        except Exception as e:
            self.logger.log_with_context('error', f'회고 파일 수집 중 오류: {e}')
            return ""

    def _generate_integrated_lessons_v8(self, all_reflections: str, current_lessons: str, 
                                       new_reflection: str) -> Optional[str]:
        """
        v8.0 GPT 기반 교훈 통합 생성
        
        Args:
            all_reflections (str): 모든 회고 내용
            current_lessons (str): 현재 교훈
            new_reflection (str): 새로운 회고
            
        Returns:
            Optional[str]: 통합된 교훈 또는 None
        """
        try:
            integration_prompt = f"""
# OMNI-XRP v8.0 교훈 통합 분석

## 🎯 목표
모든 거래 회고를 종합하여 **최신화되고 실행 가능한 거래 원칙**을 수립해주세요.

## 📚 기존 축적된 교훈
{current_lessons}

## 📝 모든 거래 회고 내역
{all_reflections}

## 🆕 최신 회고 (우선 반영)
{new_reflection}

## 🔄 교훈 통합 요청

위의 모든 정보를 종합하여 다음 구조로 **최신화된 교훈 파일**을 작성해주세요:

### 구조:
```markdown
# OMNI-XRP v8.0 학습된 거래 교훈

## 시스템 철학
[핵심 거래 철학]

## 핵심 원칙

### 1. 진입 원칙
- [성공률이 높았던 진입 조건들]
- [피해야 할 진입 상황들]

### 2. 관리 원칙  
- [효과적이었던 관리 방식들]
- [실패했던 관리 패턴들]

### 3. 매도 원칙
- [최적의 매도 타이밍 원칙들]
- [매도 실수 방지 규칙들]

### 4. 리스크 원칙
- [자금 관리 핵심 원칙들]
- [위험 신호 감지 방법들]

### 5. 학습 원칙
- [지속적 개선 방법들]
- [반복 실수 방지 체계]

## v8.0 특화 원칙

### 확률론적 접근
- [체크리스트 점수별 대응법]
- [신호 신뢰도 활용법]

### XRP 전문가 시스템
- [위꼬리 방어 최적 활용법]
- [에너지 압축 패턴 대응법]

## 최근 적용된 교훈 (자동 업데이트)
[최근 거래에서 학습한 새로운 인사이트들]
```

**중요 지침:**
1. 반복되는 성공 패턴은 강화하여 명확한 원칙으로 정립
2. 반복되는 실패 패턴은 구체적인 금지 규칙으로 전환
3. 모든 원칙은 다음 거래에서 바로 체크하고 적용 가능해야 함
4. 최신 회고의 교훈을 우선적으로 반영
5. 상충하는 교훈이 있다면 최신 데이터를 우선시
"""

            # GPT 호출
            response = self.openai_client.chat.completions.create(
                model=self.config_manager.get('ai.model'),
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 OMNI-XRP v8.0의 학습 시스템 전문가입니다.

핵심 역할:
1. 모든 거래 경험을 종합하여 **실행 가능한 거래 원칙** 수립
2. 반복되는 패턴을 발견하고 **명확한 규칙**으로 체계화
3. 최신 경험을 우선 반영하여 **지속적으로 진화하는 교훈** 생성
4. 다음 거래에서 **즉시 적용 가능한 체크리스트** 형태로 정리

목표: v8.0 시스템이 과거 경험을 통해 지속적으로 발전할 수 있는 학습 기반 구축"""
                    },
                    {
                        "role": "user",
                        "content": integration_prompt
                    }
                ],
                max_tokens=3000,
                temperature=0.1
            )
            
            integrated_lessons = response.choices[0].message.content
            
            self.logger.log_with_context(
                'info',
                'v8.0 GPT 기반 교훈 통합 완료',
                content_length=len(integrated_lessons)
            )
            
            return integrated_lessons
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 GPT 기반 교훈 통합 중 오류: {e}')
            return None

    def _save_updated_lessons_v8(self, integrated_lessons: str) -> None:
            """
            v8.0 업데이트된 교훈 저장
            
            Args:
                integrated_lessons (str): 통합된 교훈 내용
            """
            try:
                # 백업 생성
                if os.path.exists(self.lessons_file):
                    backup_file = f"{self.lessons_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    with open(self.lessons_file, 'r', encoding='utf-8') as src:
                        with open(backup_file, 'w', encoding='utf-8') as dst:
                            dst.write(src.read())
                    self.logger.log_with_context('info', f'교훈 파일 백업 생성: {backup_file}')
                
                # 새로운 교훈 저장
                with open(self.lessons_file, 'w', encoding='utf-8') as f:
                    f.write(integrated_lessons)
                
                self.logger.log_with_context('info', 'v8.0 업데이트된 교훈 저장 완료')
                
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 교훈 저장 중 오류: {e}')

    def _record_learning_data_v8(self, trade_id: int, lesson_content: str) -> None:
        """
        v8.0 학습 데이터 기록
        
        Args:
            trade_id (int): 거래 ID
            lesson_content (str): 교훈 내용
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO learning_data (
                        trade_id, lesson_type, lesson_content, 
                        confidence_score, created_timestamp
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (trade_id, 'INTEGRATED_REFLECTION', lesson_content[:1000], 
                      0.8, timestamp))  # 통합 회고는 기본 0.8 신뢰도
                conn.commit()
            
            self.logger.log_with_context('info', f'v8.0 학습 데이터 기록 완료 - 거래 ID {trade_id}')
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 학습 데이터 기록 중 오류: {e}')

    def get_current_lessons_for_strategy_v8(self) -> str:
        """
        v8.0 전략 수립 시 현재 교훈들을 가져와서 적용
        
        Returns:
            str: 현재 활성 교훈들
        """
        try:
            if not os.path.exists(self.lessons_file):
                return "아직 축적된 교훈이 없습니다."
            
            with open(self.lessons_file, 'r', encoding='utf-8') as f:
                lessons_content = f.read()
            
            # 최근 적용 횟수 업데이트
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE learning_data 
                        SET application_count = application_count + 1,
                            last_applied = ?
                        WHERE lesson_type = 'INTEGRATED_REFLECTION'
                        ORDER BY created_timestamp DESC
                        LIMIT 1
                    ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
                    conn.commit()
            except Exception:
                pass  # 업데이트 실패해도 교훈 제공은 계속
            
            return lessons_content
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 현재 교훈 조회 중 오류: {e}')
            return "교훈 조회 실패"

    def run_strategy_analysis_v8(self) -> None:
        """
        v8.0 전략 분석 - 확률론적 접근 통합 + 상태 관리
        """
        try:
            # 상태 확인
            if not self.state_manager.is_idle():
                current_state, context = self.state_manager.get_state()
                self.logger.log_with_context(
                    'debug',
                    f'전략 분석 스킵: 시스템 상태 {current_state.value}',
                    context=str(context)
                )
                return
            
            # 1회성 즉시 분석 스케줄 처리
            cleared_jobs = schedule.clear('immediate_analysis')
            if cleared_jobs:
                self.logger.log_with_context(
                    'info',
                    f'v8.0 매도 후 즉시 분석 실행 ({cleared_jobs}개 즉시 분석 작업 완료)'
                )
            
            # 상태를 ANALYZING으로 변경
            analysis_context = {
                'operation': 'strategy_analysis',
                'interval': f'{self.current_analysis_interval}분'
            }
            
            if not self.state_manager.set_state(SystemState.ANALYZING, analysis_context):
                self.logger.log_with_context('warning', 'v8.0 전략 분석을 위한 상태 변경 실패')
                return
            
            try:
                start_time = time.time()
                
                self.logger.log_with_context(
                    'info',
                    f'v8.0 확률론적 동적 주기 전략 분석 시작',
                    current_interval=f'{self.current_analysis_interval}분'
                )
                
                # 1. OBSERVE - 시장 데이터 관찰 (API 최적화 적용)
                market_data = self.get_optimized_market_data()
                if not market_data:
                    self.logger.log_with_context('error', 'v8.0 시장 데이터 수집 실패 - 전략 분석 중단')
                    return
                
                # 2. ORIENT & DECIDE - v8.0 확률론적 접근 전략 수립
                strategy = self.orient_and_decide_v8(market_data)
                if strategy:
                    # 3. ACT - v8.0 거래 계획 저장
                    trade_id = self.save_trade_plan_v8(strategy)
                    if trade_id:
                        self.logger.log_with_context(
                            'info',
                            f'v8.0 새로운 거래 계획 저장 완료',
                            trade_id=trade_id
                        )
                        
                        # 즉시 매수 조건 체크
                        position_status = market_data.get('position_status', {})
                        if not position_status.get('has_position', False):
                            self._check_immediate_buy_opportunity_v8(trade_id)
                    else:
                        self.logger.log_with_context('info', 'v8.0 포지션 관리 조언 또는 저장 불필요')
                
                # 성능 추적
                analysis_duration = time.time() - start_time
                api_calls_used = market_data.get('api_calls_used', 0)
                
                # 성능 데이터 기록
                self._record_performance_data_v8('STRATEGY_ANALYSIS', analysis_duration, api_calls_used, True)
                
                self.logger.log_with_context(
                    'info',
                    f'v8.0 확률론적 동적 주기 전략 분석 완료',
                    duration=f'{analysis_duration:.2f}초',
                    api_calls=api_calls_used
                )
                
            finally:
                # 상태를 IDLE로 복원
                self.state_manager.set_state(SystemState.IDLE)
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 전략 분석 중 오류: {e}')
            self.state_manager.set_state(SystemState.IDLE)

    def _record_performance_data_v8(self, operation_type: str, duration: float, 
                                   api_calls: int, success: bool, error_msg: str = "") -> None:
        """
        v8.0 성능 데이터 기록
        
        Args:
            operation_type (str): 작업 타입
            duration (float): 실행 시간
            api_calls (int): API 호출 횟수
            success (bool): 성공 여부
            error_msg (str): 오류 메시지
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO system_performance (
                        timestamp, operation_type, duration_seconds,
                        api_calls_count, success, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (timestamp, operation_type, duration, api_calls, success, error_msg))
                conn.commit()
                
        except Exception as e:
            self.logger.log_with_context('error', f'성능 데이터 기록 중 오류: {e}')

    def _check_and_update_analysis_interval_v8(self) -> None:
            """
            v8.0 동적 분석 주기 재평가 및 업데이트 (5분마다 실행)
            """
            try:
                # 쿨다운 체크 (최소 5분 간격)
                current_time = time.time()
                if (self.last_interval_change and 
                    current_time - self.last_interval_change < 300):
                    return
                
                self.logger.log_with_context('debug', 'v8.0 동적 분석 주기 재평가 시작')
                
                # 현재 시장 데이터 수집
                market_data = self.get_optimized_market_data()
                if not market_data:
                    return
                
                position_status = market_data.get('position_status', {})
                market_regime = self._analyze_market_regime_v8(market_data)
                
                # 새로운 최적 주기 계산
                new_interval, mode_desc = self._get_dynamic_analysis_interval_v8(position_status, market_regime)
                
                # 현재 주기와 비교
                if new_interval != self.current_analysis_interval:
                    self.logger.log_with_context(
                        'info',
                        'v8.0 분석 주기 변경 감지',
                        old_interval=f'{self.current_analysis_interval}분',
                        new_interval=f'{new_interval}분',
                        reason=mode_desc
                    )
                    
                    # 기존 스케줄 제거
                    schedule.clear('strategy_analysis')
                    
                    # 새로운 스케줄 등록
                    schedule.every(new_interval).minutes.do(self.run_strategy_analysis_v8).tag('strategy_analysis')
                    
                    # 상태 업데이트
                    self.current_analysis_interval = new_interval
                    self.last_interval_change = current_time
                    
                    next_run = datetime.now() + timedelta(minutes=new_interval)
                    self.logger.log_with_context(
                        'info',
                        f'v8.0 분석 주기 업데이트 완료: {mode_desc}',
                        next_analysis=next_run.strftime("%H:%M:%S")
                    )
                else:
                    self.logger.log_with_context(
                        'debug',
                        'v8.0 분석 주기 유지',
                        current_interval=f'{self.current_analysis_interval}분'
                    )
                    
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 동적 분석 주기 재평가 중 오류: {e}')

    def _get_dynamic_analysis_interval_v8(self, position_status: Dict, market_regime: Dict) -> Tuple[int, str]:
        """
        v8.0 시장 상황에 따른 최적 분석 주기 계산
        
        Args:
            position_status (Dict): 포지션 상태
            market_regime (Dict): 시장 체제
            
        Returns:
            Tuple[int, str]: (분석 주기(분), 모드 설명)
        """
        try:
            has_position = position_status.get('has_position', False)
            regime = market_regime.get('regime', '애매한_혼조장')
            regime_score = market_regime.get('regime_score', 0)
            
            # 1. 포지션 보유 여부에 따른 기본 주기
            if has_position:
                # XRP 보유 중 - 더 자주 모니터링
                if regime in ['명백한_상승장', '횡보_박스권']:
                    base_interval = 15  # 15분
                    mode = "보유중-안정모드"
                else:
                    base_interval = 5   # 5분 (위험 상황)
                    mode = "보유중-위험모드"
            else:
                # XRP 미보유 - 기회 포착 모드
                if regime == '명백한_상승장':
                    base_interval = 10  # 10분 (기회 놓치지 않기)
                    mode = "미보유-기회포착모드"
                elif regime in ['횡보_박스권', '고변동성_혼조장']:
                    base_interval = 30  # 30분
                    mode = "미보유-일반모드"
                elif regime == '애매한_혼조장':
                    base_interval = 60  # 1시간
                    mode = "미보유-관망모드"
                else:  # 명백한_하락장
                    base_interval = 120 # 2시간
                    mode = "미보유-휴식모드"
            
            # 2. 시장 체제 점수에 따른 조정
            if regime_score >= 2.0:
                adjustment = 0.8  # 20% 단축 (더 자주)
            elif regime_score <= -2.0:
                adjustment = 1.5  # 50% 연장 (덜 자주)
            else:
                adjustment = 1.0
            
            # 3. BTC 영향도에 따른 조정
            btc_analysis = market_regime.get('btc_analysis', {})
            btc_influence = btc_analysis.get('btc_influence', '낮음')
            
            if btc_influence in ['높음', '매우높음']:
                adjustment *= 0.7  # 30% 단축 (BTC 변동 민감)
                mode += "+BTC민감"
            
            # 4. 최종 주기 계산 및 범위 제한
            final_interval = int(base_interval * adjustment)
            final_interval = max(5, min(180, final_interval))  # 5분~3시간 범위
            
            return final_interval, mode
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 동적 분석 주기 계산 중 오류: {e}')
            return 30, "오류-기본모드"

    def show_system_status_v8(self) -> None:
        """
        v8.0 시스템 상태 종합 조회 (터미널 명령어용)
        """
        try:
            print("\n" + "="*80)
            print("🎯 OMNI-XRP v8.0 시스템 상태 종합 리포트")
            print("="*80)
            
            # 1. 현재 시스템 상태
            current_state, context = self.state_manager.get_state()
            print(f"📊 시스템 상태: {current_state.value}")
            if context:
                print(f"   └─ 컨텍스트: {context}")
            
            # 2. 현재 포지션 및 잔고 상태
            print("\n💰 잔고 및 포지션 상태")
            try:
                balances = self._api_call_wrapper(self.upbit_client.get_balances)
                if balances:
                    xrp_balance = 0
                    krw_balance = 0
                    xrp_avg_price = 0
                    
                    for balance in balances:
                        if balance['currency'] == "XRP":
                            xrp_balance = float(balance['balance'])
                            xrp_avg_price = float(balance['avg_buy_price'])
                        elif balance['currency'] == "KRW":
                            krw_balance = float(balance['balance'])
                    
                    # 현재가 조회
                    orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
                    current_price = float(orderbook['orderbook_units'][0]['ask_price']) if orderbook else 0
                    
                    print(f"   XRP 보유: {xrp_balance:.4f} XRP")
                    if xrp_balance > 0:
                        print(f"   평균 매수가: {xrp_avg_price:,.0f}원")
                        print(f"   현재가: {current_price:,.0f}원")
                        if xrp_avg_price > 0:
                            profit_pct = ((current_price - xrp_avg_price) / xrp_avg_price * 100)
                            profit_emoji = "🟢" if profit_pct > 0 else "🔴" if profit_pct < 0 else "⚪"
                            print(f"   평가 손익: {profit_emoji} {profit_pct:+.2f}%")
                    
                    print(f"   KRW 잔고: {krw_balance:,.0f}원")
                else:
                    print("   ❌ 잔고 조회 실패")
            except Exception as e:
                print(f"   ❌ 잔고 조회 오류: {e}")
            
            # 3. 활성 거래 및 계획 상태
            print("\n📈 거래 현황")
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # 활성 거래
                    cursor.execute('''
                        SELECT trade_id, planned_target_price, planned_stop_loss, 
                               actual_entry_price, entry_timestamp,
                               checklist_score, signal_confidence_multiplier
                        FROM trades WHERE status = 'ACTIVE'
                        ORDER BY entry_timestamp DESC LIMIT 1
                    ''')
                    active_trade = cursor.fetchone()
                    
                    if active_trade:
                        (trade_id, target, stop, entry_price, entry_time, 
                         checklist_score, signal_multiplier) = active_trade
                        print(f"   🟢 활성 거래 ID: {trade_id}")
                        print(f"      진입가: {entry_price:,.0f}원 ({entry_time})")
                        print(f"      목표가: {target:,.0f}원")
                        print(f"      손절가: {stop:,.0f}원")
                        print(f"      체크리스트: {checklist_score:.1f}/5.5점")
                        print(f"      신호 승수: {signal_multiplier:.1f}x")
                    else:
                        print("   ⚪ 활성 거래 없음")
                    
                    # 계획된 거래
                    cursor.execute('''
                        SELECT trade_id, planned_entry_price, planned_target_price, 
                               plan_timestamp, checklist_score
                        FROM trades WHERE status = 'PLANNED'
                        ORDER BY plan_timestamp DESC LIMIT 1
                    ''')
                    planned_trade = cursor.fetchone()
                    
                    if planned_trade:
                        (plan_id, entry_price, target, plan_time, checklist_score) = planned_trade
                        print(f"   🟡 계획 거래 ID: {plan_id}")
                        print(f"      진입가: {entry_price:,.0f}원")
                        print(f"      목표가: {target:,.0f}원")
                        print(f"      계획 시간: {plan_time}")
                        print(f"      체크리스트: {checklist_score:.1f}/5.5점")
                    else:
                        print("   ⚪ 계획된 거래 없음")
                        
            except Exception as e:
                print(f"   ❌ 거래 현황 조회 오류: {e}")
            
            # 4. 최근 성과 요약
            print("\n📊 최근 성과 (최근 10건)")
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT trade_result, net_profit_krw, profit_rate_pct, 
                               exit_timestamp, wick_defense_result
                        FROM trades 
                        WHERE status = 'COMPLETED' 
                        ORDER BY exit_timestamp DESC 
                        LIMIT 10
                    ''')
                    recent_trades = cursor.fetchall()
                    
                    if recent_trades:
                        total_profit = sum(trade[1] for trade in recent_trades if trade[1])
                        win_count = sum(1 for trade in recent_trades if trade[1] and trade[1] > 0)
                        total_count = len(recent_trades)
                        win_rate = (win_count / total_count * 100) if total_count > 0 else 0
                        
                        print(f"   총 수익: {total_profit:+,.0f}원")
                        print(f"   승률: {win_rate:.1f}% ({win_count}/{total_count})")
                        
                        # 위꼬리 방어 성과
                        defense_saves = sum(1 for trade in recent_trades if trade[4] == 'SUCCESS')
                        if defense_saves > 0:
                            print(f"   🛡️ 위꼬리 방어 성공: {defense_saves}회")
                        
                        print("   최근 거래 내역:")
                        for i, trade in enumerate(recent_trades[:5], 1):
                            result, profit, profit_pct, exit_time, defense = trade
                            profit_emoji = "💰" if profit > 0 else "💸" if profit < 0 else "⚪"
                            defense_emoji = "🛡️" if defense == 'SUCCESS' else ""
                            print(f"      {i}. {profit_emoji}{defense_emoji} {profit:+,.0f}원 ({profit_pct:+.1f}%) - {exit_time}")
                    else:
                        print("   ⚪ 완료된 거래 없음")
                        
            except Exception as e:
                print(f"   ❌ 성과 조회 오류: {e}")
            
            # 5. 시스템 설정 및 운영 상태
            print("\n⚙️ 시스템 운영 상태")
            print(f"   현재 분석 주기: {self.current_analysis_interval}분")
            print(f"   위꼬리 방어: {'활성화' if self.wick_defense_enabled else '비활성화'}")
            print(f"   가격 알림 임계값: {self.price_alert_threshold:.1%}")
            print(f"   거래량 급증 임계값: {self.volume_spike_threshold:.1f}x")
            print(f"   긴급 쿨다운: {self.emergency_cooldown}초")
            
            # 6. API 사용량 및 성능
            print("\n🔧 API 및 성능 현황")
            print(f"   분당 API 호출: {self.api_call_tracker['calls_per_minute']}/{self.config_manager.get('api.rate_limit_per_minute')}")
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT AVG(duration_seconds), COUNT(*), 
                               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END)
                        FROM system_performance 
                        WHERE timestamp > datetime('now', '-24 hours')
                    ''')
                    perf_data = cursor.fetchone()
                    
                    if perf_data and perf_data[1] > 0:
                        avg_duration, total_ops, success_ops = perf_data
                        success_rate = (success_ops / total_ops * 100) if total_ops > 0 else 0
                        print(f"   24시간 평균 실행 시간: {avg_duration:.2f}초")
                        print(f"   24시간 작업 성공률: {success_rate:.1f}% ({success_ops}/{total_ops})")
                    else:
                        print("   24시간 성능 데이터 없음")
                        
            except Exception as e:
                print(f"   ❌ 성능 데이터 조회 오류: {e}")
            
            # 7. 현재 시장 상황 (간략)
            print("\n📈 현재 시장 상황")
            try:
                market_data = self.get_optimized_market_data()
                if market_data:
                    current_price = market_data['current_price']
                    xrp_analysis = market_data.get('xrp_expert_analysis', {})
                    
                    print(f"   현재 XRP/KRW: {current_price:,.0f}원")
                    print(f"   에너지 압축: {'감지됨' if xrp_analysis.get('energy_compression_detected', False) else '없음'}")
                    print(f"   XRP 전문가 신뢰도: {xrp_analysis.get('expert_confidence', 0)}/5")
                    print(f"   지배적 패턴: {xrp_analysis.get('dominant_pattern', 'NONE')}")
                else:
                    print("   ❌ 시장 데이터 조회 실패")
            except Exception as e:
                print(f"   ❌ 시장 상황 조회 오류: {e}")
            
            # 8. 학습된 교훈 요약
            print("\n🎓 학습 시스템 현황")
            try:
                if os.path.exists(self.lessons_file):
                    with open(self.lessons_file, 'r', encoding='utf-8') as f:
                        lessons_content = f.read()
                    
                    print(f"   교훈 파일 크기: {len(lessons_content):,} 문자")
                    
                    # 최근 적용된 교훈 개수
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            SELECT COUNT(*) FROM learning_data 
                            WHERE created_timestamp > datetime('now', '-7 days')
                        ''')
                        recent_lessons = cursor.fetchone()[0]
                        print(f"   최근 7일 신규 교훈: {recent_lessons}개")
                else:
                    print("   ⚪ 교훈 파일 없음")
                    
                # 회고 파일 개수
                if os.path.exists(self.reflections_dir):
                    reflection_count = len([f for f in os.listdir(self.reflections_dir) if f.endswith('.md')])
                    print(f"   누적 회고 파일: {reflection_count}개")
                else:
                    print("   ⚪ 회고 디렉토리 없음")
                    
            except Exception as e:
                print(f"   ❌ 학습 시스템 조회 오류: {e}")
            
            print("\n" + "="*80)
            print(f"🕐 리포트 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*80 + "\n")
            
        except Exception as e:
            print(f"❌ 시스템 상태 조회 중 오류: {e}")

    def get_trading_status_v8(self) -> Optional[Dict]:
        """
        v8.0 프로그래밍 방식 거래 상태 조회
        
        Returns:
            Optional[Dict]: 거래 상태 정보 또는 None
        """
        try:
            status = {
                'system_state': self.state_manager.get_state()[0].value,
                'has_position': False,
                'active_trade': None,
                'planned_trade': None,
                'current_price': 0,
                'balances': {},
                'recent_performance': {}
            }
            
            # 현재가 조회
            orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
            if orderbook:
                status['current_price'] = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 잔고 조회
            balances = self._api_call_wrapper(self.upbit_client.get_balances)
            if balances:
                for balance in balances:
                    currency = balance['currency']
                    if currency in ['XRP', 'KRW']:
                        status['balances'][currency] = {
                            'balance': float(balance['balance']),
                            'avg_buy_price': float(balance.get('avg_buy_price', 0))
                        }
                
                # XRP 보유 여부 확인 (안전한 방식)
                xrp_info = status['balances'].get('XRP', {})
                status['has_position'] = xrp_info.get('balance', 0) > 0.0001
            
            # 거래 상태 조회
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 활성 거래
                cursor.execute('''
                    SELECT trade_id, planned_target_price, planned_stop_loss,
                        actual_entry_price, checklist_score
                    FROM trades WHERE status = 'ACTIVE'
                    ORDER BY entry_timestamp DESC LIMIT 1
                ''')
                active_result = cursor.fetchone()
                
                if active_result:
                    status['active_trade'] = {
                        'trade_id': active_result[0],
                        'target_price': active_result[1],
                        'stop_loss': active_result[2],
                        'entry_price': active_result[3],
                        'checklist_score': active_result[4]
                    }
                
                # 계획 거래
                cursor.execute('''
                    SELECT trade_id, planned_entry_price, checklist_score
                    FROM trades WHERE status = 'PLANNED'
                    ORDER BY plan_timestamp DESC LIMIT 1
                ''')
                planned_result = cursor.fetchone()
                
                if planned_result:
                    status['planned_trade'] = {
                        'trade_id': planned_result[0],
                        'entry_price': planned_result[1],
                        'checklist_score': planned_result[2]
                    }
                
                # 최근 성과
                cursor.execute('''
                    SELECT COUNT(*), AVG(profit_rate_pct), SUM(net_profit_krw)
                    FROM trades 
                    WHERE status = 'COMPLETED' 
                    AND exit_timestamp > datetime('now', '-30 days')
                ''')
                perf_result = cursor.fetchone()
                
                if perf_result and perf_result[0] > 0:
                    status['recent_performance'] = {
                        'trade_count': perf_result[0],
                        'avg_profit_rate': perf_result[1] or 0,
                        'total_profit': perf_result[2] or 0
                    }
            
            return status
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 거래 상태 조회 중 오류: {e}')
            return None

    def _detect_price_spike_v8(self, current_price: float) -> Tuple[bool, float, str]:
        """
        v8.0 급변동 감지 (가격 기반)
        
        Args:
            current_price (float): 현재 가격
            
        Returns:
            Tuple[bool, float, str]: (급변동 여부, 변동률, 급변동 타입)
        """
        try:
            # 이전 가격이 없으면 저장 후 False 반환
            if not hasattr(self, '_last_spike_check_price'):
                self._last_spike_check_price = current_price
                self._last_spike_check_time = time.time()
                return False, 0.0, 'none'
            
            # 최소 30초 간격으로 체크
            current_time = time.time()
            if current_time - getattr(self, '_last_spike_check_time', 0) < 30:
                return False, 0.0, 'none'
            
            # 변동률 계산
            prev_price = self._last_spike_check_price
            change_pct = ((current_price - prev_price) / prev_price * 100)
            
            # 급변동 임계값 확인
            spike_detected = abs(change_pct) >= (self.price_alert_threshold * 100)
            
            if spike_detected:
                spike_type = 'surge' if change_pct > 0 else 'drop'
                
                self.logger.log_with_context(
                    'info',
                    f'v8.0 급변동 감지',
                    change=f'{change_pct:+.2f}%',
                    type=spike_type,
                    prev_price=f'{prev_price:,.0f}원',
                    current_price=f'{current_price:,.0f}원'
                )
            else:
                spike_type = 'none'
            
            # 상태 업데이트
            self._last_spike_check_price = current_price
            self._last_spike_check_time = current_time
            
            return spike_detected, change_pct, spike_type
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 급변동 감지 중 오류: {e}')
            return False, 0.0, 'error'

    def _is_emergency_cooldown_active_v8(self) -> bool:
        """
        v8.0 긴급 분석 쿨다운 활성 여부 확인
        
        Returns:
            bool: 쿨다운 활성 여부
        """
        if not self.last_emergency_time:
            return False
        
        return (time.time() - self.last_emergency_time) < self.emergency_cooldown

    def _emergency_strategy_analysis_v8(self, current_price: float, change_pct: float, spike_type: str) -> None:
        """
        v8.0 급변동 발생 시 긴급 전략 재분석
        
        Args:
            current_price (float): 현재 가격
            change_pct (float): 변동률
            spike_type (str): 급변동 타입
        """
        try:
            self.logger.log_with_context(
                'info',
                f'v8.0 긴급 전략 재분석 시작',
                trigger=f'{spike_type} {change_pct:+.2f}%'
            )
            
            # 긴급 분석 실행 (일반 전략 분석과 동일하지만 로그로 구분)
            self.run_strategy_analysis_v8()
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 긴급 전략 재분석 중 오류: {e}')

    def _update_position_management_v8(self, trade_plan: Dict) -> Optional[int]:
        """
        v8.0 XRP 보유 중일 때: 포지션 관리 업데이트
        
        Args:
            trade_plan (Dict): 관리 전략
            
        Returns:
            Optional[int]: 업데이트된 거래 ID 또는 None
        """
        try:
            change_trigger = trade_plan.get('change_trigger', 'NONE')
            
            if change_trigger == 'NONE':
                # 변경 불필요 - 로그만 남기고 종료
                self.logger.log_with_context('info', 'v8.0 포지션 관리 - 현재 전략 유지')
                return None
            
            # 변경 필요 - 기존 ACTIVE 거래를 SUPERSEDED로 변경 후 새로운 관리 계획 저장
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 현재 ACTIVE 거래 ID 조회
                cursor.execute('''
                    SELECT trade_id, position_size_xrp, actual_entry_price, commission_krw
                    FROM trades WHERE status = 'ACTIVE'
                    ORDER BY entry_timestamp DESC LIMIT 1
                ''')
                
                current_active = cursor.fetchone()
                if not current_active:
                    self.logger.log_with_context('error', 'v8.0 포지션 관리 - 활성 거래를 찾을 수 없음')
                    return None
                
                old_trade_id, position_size, entry_price, entry_commission = current_active
                
                # 기존 거래를 SUPERSEDED로 변경
                cursor.execute('''
                    UPDATE trades SET 
                        status = 'SUPERSEDED',
                        target_reason = target_reason || ' [v8.0 관리변경으로 대체됨]'
                    WHERE trade_id = ?
                ''', (old_trade_id,))
                
                # 새로운 관리 계획 저장
                plan_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute('''
                    INSERT INTO trades (
                        asset_ticker, status, plan_timestamp,
                        planned_entry_price, planned_target_price, planned_stop_loss,
                        entry_reason, target_reason, stop_loss_reason,
                        position_size_xrp, entry_timestamp, actual_entry_price, commission_krw,
                        change_trigger, trigger_evidence, wick_defense_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'XRP', 'ACTIVE', plan_timestamp,
                    0, trade_plan['target_price'], trade_plan['stop_loss_price'],
                    '포지션 관리 변경 - 기존 진입 유지',
                    trade_plan['target_reason'], trade_plan['stop_loss_reason'],
                    position_size, plan_timestamp, entry_price, entry_commission,
                    change_trigger, trade_plan.get('trigger_evidence', ''),
                    trade_plan.get('wick_defense_active', True)
                ))
                
                new_trade_id = cursor.lastrowid
                conn.commit()
                
                self.logger.log_with_context(
                    'info',
                    f'v8.0 포지션 관리 업데이트 완료',
                    old_trade_id=old_trade_id,
                    new_trade_id=new_trade_id,
                    trigger=change_trigger,
                    new_target=f'{trade_plan["target_price"]:,.0f}원',
                    new_stop=f'{trade_plan["stop_loss_price"]:,.0f}원'
                )
                
                return new_trade_id
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 포지션 관리 업데이트 중 오류: {e}')
            return None

    def _check_immediate_buy_opportunity_v8(self, trade_id: int) -> None:
        """
        v8.0 새로운 계획 저장 직후 즉시 매수 조건 체크
        
        Args:
            trade_id (int): 거래 ID
        """
        try:
            self.logger.log_with_context('info', f'v8.0 신규 계획 ID {trade_id} 즉시 매수 조건 체크')
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT planned_entry_price, checklist_score, signal_confidence_multiplier
                    FROM trades 
                    WHERE trade_id = ? AND status = 'PLANNED'
                ''', (trade_id,))
                
                result = cursor.fetchone()
            
            if not result:
                self.logger.log_with_context('info', 'v8.0 즉시 매수 조건 체크 대상 계획 없음')
                return
            
            planned_entry_price, checklist_score, signal_multiplier = result
            
            # 진입가가 0이면 매수 금지 상태
            if planned_entry_price == 0:
                self.logger.log_with_context('info', 'v8.0 진입가 0 - 매수 금지 상태')
                return
            
            # 현재 가격 확인
            orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
            if not orderbook:
                return
            
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 즉시 매수 조건 확인 (±1% 범위)
            entry_range = planned_entry_price * 0.01
            price_diff = abs(current_price - planned_entry_price)
            
            if price_diff <= entry_range:
                self.logger.log_with_context(
                    'info',
                    'v8.0 즉시 매수 조건 만족!',
                    planned_price=f'{planned_entry_price:,.0f}원',
                    current_price=f'{current_price:,.0f}원',
                    price_diff=f'{price_diff:,.0f}원',
                    allowed_range=f'{entry_range:,.0f}원',
                    checklist_score=f'{checklist_score:.1f}/5.5',
                    signal_multiplier=f'{signal_multiplier:.1f}'
                )
                
                # 매수 실행
                success = self._execute_buy_order_v8(trade_id, planned_entry_price)
                if success:
                    self.logger.log_with_context('info', f'v8.0 매도 완료 후 즉시 매수 성공! (거래 ID: {trade_id})')
                else:
                    self.logger.log_with_context('warning', f'v8.0 매도 완료 후 즉시 매수 실패 (거래 ID: {trade_id})')
            else:
                self.logger.log_with_context(
                    'info',
                    'v8.0 즉시 매수 조건 미달성',
                    price_diff=f'{price_diff:,.0f}원',
                    allowed_range=f'{entry_range:,.0f}원',
                    note='정기 모니터링에서 재확인 예정'
                )
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 즉시 매수 조건 체크 중 오류: {e}')

    def save_trade_plan_v8(self, trade_plan: Dict) -> Optional[int]:
        """
        v8.0 거래 계획 저장: 확률론적 정보 + 학습 시스템 연동
        
        Args:
            trade_plan (Dict): 거래 계획
            
        Returns:
            Optional[int]: 저장된 거래 ID 또는 None
        """
        try:
            if not trade_plan or 'entry_price' not in trade_plan:
                self.logger.log_with_context('warning', '유효한 v8.0 거래 계획이 아닙니다')
                return None
            
            # 포지션 상태 재확인
            balances = self._api_call_wrapper(self.upbit_client.get_balances)
            
            if balances:
                xrp_balance = 0
                for balance in balances:
                    if balance['currency'] == "XRP":
                        xrp_balance = float(balance['balance'])
                        break
                
                has_position = xrp_balance > 0.0001
                
                if has_position:
                    # XRP 보유 중 - 포지션 관리 모드
                    return self._update_position_management_v8(trade_plan)
                else:
                    # XRP 미보유 - 신규 진입 계획 모드
                    return self._create_new_entry_plan_v8(trade_plan)
            else:
                self.logger.log_with_context('error', '잔고 정보 조회 실패')
                return None
                    
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 거래 계획 저장 중 오류: {e}')
            return None

    def _create_new_entry_plan_v8(self, trade_plan: Dict) -> Optional[int]:
        """
        v8.0 XRP 미보유일 때: 확률론적 정보 포함 신규 진입 계획 생성
        
        Args:
            trade_plan (Dict): 거래 계획
            
        Returns:
            Optional[int]: 거래 ID 또는 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 1단계: 모든 기존 계획/활성 거래 정리
                cursor.execute("UPDATE trades SET status = 'CANCELLED' WHERE status IN ('PLANNED', 'ACTIVE')")
                cancelled_count = cursor.rowcount
                
                # 2단계: v8.0 새로운 진입 계획 저장
                plan_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # v8.0 확률론적 필드들
                checklist_score = trade_plan.get('checklist_score', 0.0)
                signal_confidence_multiplier = trade_plan.get('signal_confidence_multiplier', 0.0)
                calculated_position_ratio = trade_plan.get('calculated_position_ratio', 0.0)
                checklist_breakdown = json.dumps(trade_plan.get('checklist_breakdown', {}), ensure_ascii=False)
                
                # v8.0 XRP 전문가 필드들
                wick_defense_active = trade_plan.get('wick_defense_active', True)
                energy_compression_detected = trade_plan.get('energy_compression_detected', False)
                xrp_pattern_type = trade_plan.get('xrp_pattern_type', 'NONE')
                
                # v8.0 학습 시스템 연동
                lessons_applied = self.get_current_lessons_for_strategy_v8()[:500]  # 요약본만 저장
                
                cursor.execute('''
                    INSERT INTO trades (
                        asset_ticker, status, plan_timestamp,
                        planned_entry_price, planned_target_price, planned_stop_loss,
                        entry_reason, target_reason, stop_loss_reason,
                        checklist_score, checklist_breakdown, signal_confidence_multiplier,
                        calculated_position_ratio, wick_defense_active,
                        energy_compression_detected, xrp_pattern_type, lessons_applied
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'XRP', 'PLANNED', plan_timestamp,
                    trade_plan['entry_price'], trade_plan['target_price'], trade_plan['stop_loss_price'],
                    trade_plan['entry_reason'], trade_plan['target_reason'], trade_plan['stop_loss_reason'],
                    checklist_score, checklist_breakdown, signal_confidence_multiplier,
                    calculated_position_ratio, wick_defense_active,
                    energy_compression_detected, xrp_pattern_type, lessons_applied
                ))
                
                new_trade_id = cursor.lastrowid
                conn.commit()
                
                if cancelled_count > 0:
                    self.logger.log_with_context('info', f'기존 계획 {cancelled_count}개 정리 완료')
                
                self.logger.log_with_context(
                    'info',
                    f'v8.0 새로운 진입 계획 저장 완료',
                    trade_id=new_trade_id,
                    checklist_score=f'{checklist_score:.1f}/5.5',
                    signal_multiplier=f'{signal_confidence_multiplier:.1f}',
                    wick_defense='활성화' if wick_defense_active else '비활성화',
                    entry_price=f'{trade_plan["entry_price"]:,.0f}원',
                    target_price=f'{trade_plan["target_price"]:,.0f}원'
                )
                
                return new_trade_id
                
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 신규 진입 계획 생성 중 오류: {e}')
            return None

    def start_automated_trading_v8(self) -> None:
        """
        v8.0 자동화된 거래 시스템 시작 (상태 관리 + API 최적화 + 학습 시스템 통합)
        """
        self.logger.log_with_context('info', 'OMNI-XRP v8.0 확률론적 접근 + XRP 전문가 + 학습 시스템 자동화 시작')
        
        # 시스템 시작 시 포지션 검증 및 기존 계획 정리
        self.validate_and_cleanup_existing_plans_v8()
        
        # 1. 현재 상황에 맞는 초기 분석 주기 설정
        self.logger.log_with_context('info', 'v8.0 시스템 시작 - 초기 분석 주기 설정')
        
        market_data = self.get_optimized_market_data()
        if market_data:
            position_status = market_data.get('position_status', {})
            market_regime = self._analyze_market_regime_v8(market_data)
            
            # 초기 주기 계산 및 즉시 적용
            initial_interval, mode_desc = self._get_dynamic_analysis_interval_v8(position_status, market_regime)
            
            # 최초 스케줄 등록
            self.current_analysis_interval = initial_interval
            schedule.every(initial_interval).minutes.do(self.run_strategy_analysis_v8).tag('strategy_analysis')
            
            self.logger.log_with_context('info', f'v8.0 초기 분석 주기 설정: {mode_desc}')
            next_run = datetime.now() + timedelta(minutes=initial_interval)
            self.logger.log_with_context('info', f'첫 번째 정규 분석: {next_run.strftime("%H:%M:%S")}')
        else:
            # 실패 시 기본값
            self.current_analysis_interval = 30
            schedule.every(30).minutes.do(self.run_strategy_analysis_v8).tag('strategy_analysis')
            self.logger.log_with_context('warning', 'v8.0 초기 데이터 수집 실패 - 30분 기본 주기로 시작')
        
        # 2. 5분마다 주기 재평가 스케줄 등록
        schedule.every(5).minutes.do(self._check_and_update_analysis_interval_v8).tag('interval_check')
        
        # 3. 첫 전략 분석 즉시 실행
        self.logger.log_with_context('info', 'v8.0 첫 전략 분석 즉시 실행')
        self.run_strategy_analysis_v8()
        
        # 메인 루프: 4초마다 가격 감시 + 스케줄 실행 (API 최적화)
        self.logger.log_with_context('info', 'v8.0 메인 루프 시작 - 4초 주기 모니터링 (API 최적화 적용)')
        
        while True:
            try:
                # 1. v8.0 상태 관리 기반 가격 감시
                self._monitor_price_with_state_management_v8()
                
                # 2. 스케줄 확인 및 실행
                schedule.run_pending()
                
                # 4초 대기 (API 최적화)
                time.sleep(4)
                
            except KeyboardInterrupt:
                self.logger.log_with_context('info', '사용자 중단 - v8.0 시스템 종료')
                break
            except Exception as e:
                self.logger.log_with_context('error', f'v8.0 메인 루프 오류: {e}')
                time.sleep(4)

    def _monitor_price_with_state_management_v8(self) -> None:
        """
        v8.0 상태 관리 기반 가격 감시 + 급변동 감지 + 위꼬리 방어 통합
        """
        try:
            # 상태 확인 - IDLE 또는 DEFENDING 상태에서만 실행
            current_state, _ = self.state_manager.get_state()
            if current_state not in [SystemState.IDLE, SystemState.DEFENDING]:
                return  # 다른 작업 중이므로 모니터링 스킵
            
            # 현재 가격 확인 (API 최적화 적용)
            orderbook = self._api_call_wrapper(pyupbit.get_orderbook, ticker="KRW-XRP")
            if not orderbook:
                return
            
            current_price = float(orderbook['orderbook_units'][0]['ask_price'])
            
            # 급변동 감지
            is_spike, change_pct, spike_type = self._detect_price_spike_v8(current_price)
            
            if is_spike and not self._is_emergency_cooldown_active_v8():
                # 🚨 급변동 발생 - 즉시 분석 실행
                self.logger.log_with_context(
                    'info',
                    f'v8.0 {spike_type} 트리거 발동 ({change_pct:+.2f}%) - 즉시 전략 재분석 시작'
                )
                self._emergency_strategy_analysis_v8(current_price, change_pct, spike_type)
                self.last_emergency_time = time.time()  # 쿨다운 시작
            elif is_spike and self._is_emergency_cooldown_active_v8():
                self.logger.log_with_context('debug', f'v8.0 {spike_type} 감지되었으나 쿨다운 중 - 무시')
            
            # v8.0 모니터링 (상태 기반)
            if current_state == SystemState.IDLE:
                self.monitor_active_trades_v8()
                self._monitor_planned_trades_v8()
            # DEFENDING 상태에서는 위꼬리 방어 시스템이 자동으로 처리됨
            
        except Exception as e:
            self.logger.log_with_context('error', f'v8.0 상태 관리 기반 가격 감시 중 오류: {e}')

def main_v8():
    """
    v8.0 메인 실행 함수
    """
    try:
        print("🎯 OMNI-XRP v8.0 고도화된 확률론적 + 학습 시스템 시작")
        print("⚡ 실행 주기: 가격감시 4초 | 전략분석 동적주기")
        print("🚀 v8.0 혁신 기능:")
        print("   • API 호출 최적화 (80% 감소 - 리샘플링)")
        print("   • 고도화된 위꼬리 방어 (60초 유예 + 재확인)")
        print("   • 분리된 학습 시스템 (회고.md + 교훈.md)")
        print("   • 전역 상태 관리 (충돌 방지)")
        print("   • 성능 추적 및 모니터링")
        print("   • 설정 파일 분리 (config.json)")
        print("🚨 급변동 감지: 0.7% 이상 (3분 쿨다운)")
        
        # OMNI-XRP v8.0 시스템 초기화
        omni_system = OMNIXRPSystemV8()
        
        # 현재 상태 확인
        status = omni_system.get_trading_status_v8()
        if status:
            omni_system.logger.log_with_context('info', f'v8.0 현재 시스템 상태', status=str(status))
        
        # v8.0 자동화 거래 시작
        omni_system.start_automated_trading_v8()
        
    except KeyboardInterrupt:
        print("🛑 사용자 중단 - OMNI-XRP v8.0 시스템 종료")
    except Exception as e:
        print(f"❌ v8.0 메인 실행 중 오류: {e}")

if __name__ == "__main__":
    import sys
    
    # 명령줄 인자 처리
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            system = OMNIXRPSystemV8()
            system.show_system_status_v8()
        elif sys.argv[1] == "config":
            # 설정 파일 생성/확인
            config_manager = ConfigurationManager()
            print(f"✅ 설정 파일 확인/생성 완료: {config_manager.config_path}")
        else:
            print("사용법: python omni_xrp_v8.py [status|config]")
    else:
        main_v8()