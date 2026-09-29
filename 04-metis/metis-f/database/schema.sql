-- database/schema.sql
-- METIS-F 데이터베이스 스키마
-- 포지션 히스토리, 중간 점검, 펀딩비 기록

-- 포지션 히스토리 테이블
CREATE TABLE IF NOT EXISTS futures_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uuid TEXT UNIQUE NOT NULL,
    
    -- 포지션 정보
    direction TEXT NOT NULL CHECK(direction IN ('LONG', 'SHORT')),
    leverage INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    entry_quantity REAL NOT NULL,
    entry_timestamp TEXT NOT NULL,
    
    -- 목표/손절
    stop_loss_price REAL NOT NULL,
    take_profit_price REAL NOT NULL,
    liquidation_price REAL NOT NULL,
    
    -- AI 분석
    confidence_score INTEGER NOT NULL,
    ai_reason TEXT,
    strategy_json TEXT,
    
    -- 청산 결과
    status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'CLOSED', 'LIQUIDATED')),
    exit_price REAL,
    exit_timestamp TEXT,
    exit_reason TEXT CHECK(exit_reason IN ('TAKE_PROFIT', 'STOP_LOSS', 'AI_EXIT', 'LIQUIDATION', 'DEAD_MANS_SWITCH', NULL)),
    
    -- 손익 및 수수료
    realized_pnl REAL,
    realized_pnl_percentage REAL,
    entry_fee REAL DEFAULT 0,
    exit_fee REAL DEFAULT 0,
    total_fee REAL DEFAULT 0,
    
    created_at TEXT DEFAULT (datetime('now'))
);

-- 중간 점검 로그
CREATE TABLE IF NOT EXISTS position_rechecks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uuid TEXT NOT NULL,
    recheck_timestamp TEXT NOT NULL,
    
    current_price REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    unrealized_pnl_percentage REAL NOT NULL,
    
    ai_decision TEXT NOT NULL CHECK(ai_decision IN ('HOLD', 'MODIFY', 'EXIT')),
    modifications_json TEXT,
    ai_reason TEXT,
    
    FOREIGN KEY (position_uuid) REFERENCES futures_positions(position_uuid)
);

-- 펀딩비 기록
CREATE TABLE IF NOT EXISTS funding_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uuid TEXT NOT NULL,
    funding_time TEXT NOT NULL,
    funding_rate REAL NOT NULL,
    funding_fee REAL NOT NULL,
    
    FOREIGN KEY (position_uuid) REFERENCES futures_positions(position_uuid)
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_positions_status ON futures_positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_created ON futures_positions(created_at);
CREATE INDEX IF NOT EXISTS idx_rechecks_position ON position_rechecks(position_uuid);
CREATE INDEX IF NOT EXISTS idx_funding_position ON funding_history(position_uuid);