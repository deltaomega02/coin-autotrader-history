# data/database.py
# "거래 내역과 결과를 SQLite 데이터베이스에 저장하고 관리하는 데이터베이스 파일"

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from config.settings import settings


class TradeDatabase:

    # "TradeDatabase 클래스를 초기화하고 DB를 설정하는 메서드" (인자: self)
    def __init__(self):
        self.db_path = settings.DB_PATH
        self.init_db()
    
    # "데이터베이스와 테이블을 초기화하고 필요한 컬럼을 추가하는 메서드" (인자: self)
    def init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trade_log (
                    -- 기본 정보
                    trade_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    coin_ticker TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    
                    -- 계획 가격 정보
                    entry_price REAL,
                    target_price REAL,
                    stop_loss_price REAL,
                    
                    -- 실제 거래 정보
                    actual_entry_price REAL,
                    actual_exit_price REAL,
                    exit_timestamp TEXT,
                    
                    -- 거래량 및 수수료
                    executed_amount REAL DEFAULT 0,
                    actual_volume REAL DEFAULT 0,
                    exit_volume REAL DEFAULT 0,
                    entry_fee REAL DEFAULT 0,
                    exit_fee REAL DEFAULT 0,
                    
                    -- 손익 정보
                    profit_loss REAL,
                    profit_rate REAL,
                    
                    -- 거래 근거 및 컨텍스트
                    entry_reason TEXT,
                    target_reason TEXT,
                    stop_loss_reason TEXT,
                    market_data TEXT,
                    gpt_context TEXT
                )
            ''')

            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON trade_log(timestamp DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON trade_log(status)')
    
    # "거래 계획과 GPT 컨텍스트를 DB에 저장하는 메서드" (인자: self, trade_data, gpt_context)
    def insert_trade_plan(self, trade_data: Dict[str, Any], gpt_context: Dict[str, Any] = None) -> str:
        trade_id = f"TRADE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        context_json = json.dumps(gpt_context) if gpt_context else None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO trade_log 
                (trade_id, timestamp, coin_ticker, entry_price, target_price, 
                stop_loss_price, entry_reason, target_reason, stop_loss_reason, 
                market_data, gpt_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_id,
                datetime.now().isoformat(),
                trade_data.get('coin_ticker'),
                trade_data.get('entry_price'),
                trade_data.get('target_price'),
                trade_data.get('stop_loss_price'),
                trade_data.get('entry_reason'),
                trade_data.get('target_reason'),
                trade_data.get('stop_loss_reason'),
                json.dumps(trade_data.get('market_data', {})),
                context_json
            ))
        
        return trade_id
    
    # "거래 결과를 DB에 업데이트하는 메서드" (인자: self, trade_id, result_data)
    def update_trade_result(self, trade_id: str, result_data: Dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            update_fields = []
            values = []
            
            for field in ['status', 'actual_entry_price', 'actual_exit_price',
                        'exit_timestamp', 'profit_loss', 'profit_rate',
                        'entry_fee', 'exit_fee', 'executed_amount', 
                        'exit_volume', 'actual_volume']:
                if field in result_data:
                    update_fields.append(f"{field} = ?")
                    values.append(result_data[field])
            
            if update_fields:
                values.append(trade_id)
                query = f"UPDATE trade_log SET {', '.join(update_fields)} WHERE trade_id = ?"
                conn.execute(query, values)
                print(f"🔧 DB 업데이트: {trade_id} - {len(update_fields)}개 필드")
    
    # "최근 거래 내역을 조회하는 메서드" (인자: self, limit)
    def get_recent_trades(self, limit: int = 5) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM trade_log 
                ORDER BY timestamp DESC LIMIT ?
            ''', (limit,))
            
            columns = [description[0] for description in cursor.description]
            trades = []
            for row in cursor.fetchall():
                trade_dict = dict(zip(columns, row))
                if trade_dict.get('market_data'):
                    try:
                        trade_dict['market_data'] = json.loads(trade_dict['market_data'])
                    except json.JSONDecodeError:
                        pass
                if trade_dict.get('gpt_context'):
                    try:
                        trade_dict['gpt_context'] = json.loads(trade_dict['gpt_context'])
                    except json.JSONDecodeError:
                        pass
                trades.append(trade_dict)
            
            return trades
    
    # "수수료 정보를 포함한 거래를 조회하는 메서드" (인자: self, trade_id)
    def get_trade_with_fees(self, trade_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT trade_id, coin_ticker, status,
                       entry_price, actual_entry_price, target_price, stop_loss_price,
                       actual_exit_price, profit_loss, profit_rate,
                       entry_fee, exit_fee, executed_amount, actual_volume, exit_volume,
                       timestamp, exit_timestamp
                FROM trade_log 
                WHERE trade_id = ?
            ''', (trade_id,))
            
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row))
            return None
    
    # "수수료를 포함한 전체 거래 통계를 계산하는 메서드" (인자: self)
    def get_statistics_with_fees(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT COUNT(*) as total_trades,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_trades,
                    SUM(CASE WHEN status = 'COMPLETED' AND profit_loss > 0 THEN 1 ELSE 0 END) as profitable_trades,
                    AVG(CASE WHEN status = 'COMPLETED' THEN profit_rate ELSE NULL END) as avg_profit_rate,
                    SUM(CASE WHEN status = 'COMPLETED' THEN profit_loss ELSE NULL END) as total_profit_loss,
                    SUM(CASE WHEN status = 'COMPLETED' THEN entry_fee + COALESCE(exit_fee, 0) ELSE NULL END) as total_fees
                FROM trade_log
                WHERE status != 'CANCELLED'  
            ''')
            
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                stats = dict(zip(columns, row))

                if stats['completed_trades'] and stats['completed_trades'] > 0:
                    stats['win_rate'] = (stats['profitable_trades'] / stats['completed_trades']) * 100
                else:
                    stats['win_rate'] = 0

                for key in ['avg_profit_rate', 'total_profit_loss', 'total_fees']:
                    if stats[key] is None:
                        stats[key] = 0
                
                return stats
            
            return {
                'total_trades': 0,
                'completed_trades': 0,
                'profitable_trades': 0,
                'win_rate': 0,
                'avg_profit_rate': 0,
                'total_profit_loss': 0,
                'total_fees': 0
            }
    
    # "거래 정보와 GPT 컨텍스트를 함께 조회하는 메서드" (인자: self, trade_id)
    def get_trade_with_context(self, trade_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT trade_id, coin_ticker, status,
                    entry_price, actual_entry_price, target_price, stop_loss_price,
                    actual_exit_price, profit_loss, profit_rate,
                    entry_fee, exit_fee, executed_amount, actual_volume, exit_volume,
                    timestamp, exit_timestamp, entry_reason, target_reason, stop_loss_reason,
                    gpt_context
                FROM trade_log 
                WHERE trade_id = ?
            ''', (trade_id,))
            
            row = cursor.fetchone()
            if row:
                columns = [description[0] for description in cursor.description]
                trade_data = dict(zip(columns, row))

                if trade_data.get('gpt_context'):
                    try:
                        trade_data['gpt_context'] = json.loads(trade_data['gpt_context'])
                    except json.JSONDecodeError:
                        trade_data['gpt_context'] = None
                
                return trade_data
            return None