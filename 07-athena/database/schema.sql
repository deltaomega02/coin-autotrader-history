-- ATHENA SQLite 스키마

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cycle_id TEXT NOT NULL,             -- UUID per OODA cycle
    paper_mode INTEGER NOT NULL,        -- 1=paper, 0=live

    -- AI 출력 (JSON 문자열)
    analyst_json TEXT,
    risk_json TEXT,
    manager_json TEXT,

    -- 핵심 메타
    confidence INTEGER,
    risk_score INTEGER,
    regime TEXT,

    -- 입력 컨텍스트 hash (캐싱 추적)
    input_hash TEXT
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cycle_id TEXT NOT NULL,             -- decisions.cycle_id 참조

    asset TEXT NOT NULL,
    side TEXT NOT NULL,                 -- Buy/Sell
    value_usdt REAL NOT NULL,
    qty REAL,
    price REAL,

    paper_mode INTEGER NOT NULL,
    order_id TEXT,                      -- Bybit order_id (실전)
    error TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cycle_id TEXT,

    total_value_usdt REAL NOT NULL,
    btc_weight REAL,
    eth_weight REAL,
    sol_weight REAL,
    usdt_weight REAL,

    weights_json TEXT,                  -- 전체 비중 JSON
    values_json TEXT                    -- 자산별 USD 가치 JSON
);

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,

    weekly_pnl_usdt REAL,
    weekly_pnl_pct REAL,

    reflection_json TEXT NOT NULL
);

-- DCA 누적 매수 대기 (자산별)
-- 일별 매수액 < min_order_usdt면 여기 누적 → 도달 시 매수
CREATE TABLE IF NOT EXISTS dca_pending (
    asset TEXT PRIMARY KEY,
    pending_usdt REAL NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL
);

-- 평단가 추적 (자산별)
CREATE TABLE IF NOT EXISTS cost_basis (
    asset TEXT PRIMARY KEY,             -- BTC / ETH / SOL
    total_qty REAL NOT NULL DEFAULT 0,  -- 누적 보유 수량
    total_cost_usdt REAL NOT NULL DEFAULT 0,  -- 누적 매수 USD
    avg_cost_usdt REAL NOT NULL DEFAULT 0,    -- 평균 매입가
    last_updated TEXT NOT NULL,
    realized_pnl_usdt REAL NOT NULL DEFAULT 0  -- 매도 시 실현 손익 누적
);

CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_executions_cycle ON executions(cycle_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON portfolio_snapshots(timestamp);
