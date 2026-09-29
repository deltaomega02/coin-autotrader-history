# data/database.py
# "거래 내역과 결과를 SQLite 데이터베이스에 저장하고 관리하는 데이터베이스 파일"
# [V14 업데이트: 2-Target Scaling Out 전략 지원]

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
        print("📌 TradeDatabase 초기화 완료 (V14: 2-Target 전략 지원)")
    
    # "데이터베이스와 테이블을 초기화하고 필요한 컬럼을 추가하는 메서드" (인자: self)
    def init_db(self):
        """
        [V14 업데이트: 2-Target Scaling Out 전략을 위한 스키마 확장]
        - target_price → target_price_1, target_price_2로 분리
        - 분할 익절 추적 컬럼 추가
        """
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trade_log (
                    -- 기본 정보
                    trade_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    coin_ticker TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    
                    -- 계획 가격 정보 [V14: 2개 목표가로 확장]
                    entry_price REAL,
                    target_price_1 REAL,        -- 1차 목표가 (70% 청산용)
                    target_price_2 REAL,        -- 2차 목표가 (30% 추격용)
                    stop_loss_price REAL,
                    target_split_ratio REAL DEFAULT 0.7,  -- 1차 청산 비율
                    
                    -- 실제 거래 정보
                    actual_entry_price REAL,
                    actual_exit_price REAL,     -- 최종 평균 청산가
                    exit_timestamp TEXT,
                    
                    -- 거래량 및 수수료
                    executed_amount REAL DEFAULT 0,
                    actual_volume REAL DEFAULT 0,
                    exit_volume REAL DEFAULT 0,
                    entry_fee REAL DEFAULT 0,
                    exit_fee REAL DEFAULT 0,
                    
                    -- [V14: 분할 익절 추적]
                    target_1_reached_time TEXT,      -- 1차 목표 도달 시각
                    target_1_exit_price REAL,        -- 1차 청산 평균가
                    target_1_exit_volume REAL,       -- 1차 청산 물량
                    target_2_exit_price REAL,        -- 2차 청산 평균가
                    target_2_exit_volume REAL,       -- 2차 청산 물량
                    breakeven_stop_moved BOOLEAN DEFAULT 0,  -- 본절 손절 이동 여부
                    
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
        """
        [V14 업데이트: 2개의 목표가를 저장]
        """
        trade_id = f"TRADE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        context_json = json.dumps(gpt_context) if gpt_context else None
        
        # V14: target_price_1, target_price_2 분리 저장
        target_1 = trade_data.get('target_price_1') or trade_data.get('target_price')  # 호환성
        target_2 = trade_data.get('target_price_2')
        split_ratio = trade_data.get('target_split_ratio', 0.7)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO trade_log 
                (trade_id, timestamp, coin_ticker, entry_price, 
                 target_price_1, target_price_2, stop_loss_price, target_split_ratio,
                 entry_reason, target_reason, stop_loss_reason, 
                 market_data, gpt_context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_id,
                datetime.now().isoformat(),
                trade_data.get('coin_ticker'),
                trade_data.get('entry_price'),
                target_1,
                target_2,
                trade_data.get('stop_loss_price'),
                split_ratio,
                trade_data.get('entry_reason'),
                trade_data.get('target_reason'),
                trade_data.get('stop_loss_reason'),
                json.dumps(trade_data.get('market_data', {})),
                context_json
            ))
        
        print(f"💾 새 거래 계획 저장: {trade_id}")
        print(f"   🎯 1차 목표: {target_1:,.0f}원 ({split_ratio*100:.0f}% 청산)")
        if target_2:
            print(f"   🚀 2차 목표: {target_2:,.0f}원 ({(1-split_ratio)*100:.0f}% 추격)")
        return trade_id
    
    # "거래 결과를 DB에 업데이트하는 메서드" (인자: self, trade_id, result_data)
    def update_trade_result(self, trade_id: str, result_data: Dict[str, Any]):
        """
        [V14 업데이트: 분할 익절 정보 추가 업데이트]
        """
        with sqlite3.connect(self.db_path) as conn:
            update_fields = []
            values = []
            
            # 기존 필드
            for field in ['status', 'actual_entry_price', 'actual_exit_price',
                        'exit_timestamp', 'profit_loss', 'profit_rate',
                        'entry_fee', 'exit_fee', 'executed_amount', 
                        'exit_volume', 'actual_volume']:
                if field in result_data:
                    update_fields.append(f"{field} = ?")
                    values.append(result_data[field])
            
            # V14: 분할 익절 필드
            for field in ['target_1_reached_time', 'target_1_exit_price', 'target_1_exit_volume',
                        'target_2_exit_price', 'target_2_exit_volume', 'breakeven_stop_moved']:
                if field in result_data:
                    update_fields.append(f"{field} = ?")
                    values.append(result_data[field])
            
            if update_fields:
                values.append(trade_id)
                query = f"UPDATE trade_log SET {', '.join(update_fields)} WHERE trade_id = ?"
                conn.execute(query, values)
                
                # 로그 출력 개선
                stage_info = ""
                if 'target_1_exit_volume' in result_data:
                    stage_info = " [1차 청산]"
                elif 'target_2_exit_volume' in result_data:
                    stage_info = " [2차 청산]"
                print(f"🔧 DB 업데이트: {trade_id}{stage_info} - {len(update_fields)}개 필드")
    
    # "최근 거래 내역을 조회하는 메서드" (인자: self, limit)
    def get_recent_trades(self, limit: int = 5) -> List[Dict]:
        """
        [수정됨: 이전 거래 기록을 조회하지 않고 빈 리스트 반환]
        """
        print(f"   ℹ️ 이전 거래 조회 비활성화 - 빈 리스트 반환 (요청: {limit}개)")
        return []
    
    # "수수료 정보를 포함한 거래를 조회하는 메서드" (인자: self, trade_id)
    def get_trade_with_fees(self, trade_id: str) -> Optional[Dict]:
        """
        [수정됨: 개별 거래 조회 비활성화 - None 반환]
        단, 현재 진행 중인 거래는 TradeExecutor에서 메모리에 보관
        """
        print(f"   ℹ️ 개별 거래 조회 비활성화 - None 반환 (ID: {trade_id})")
        return None
    
    # "수수료를 포함한 전체 거래 통계를 계산하는 메서드" (인자: self)
    def get_statistics_with_fees(self) -> Dict[str, Any]:
        """
        [수정됨: 통계 조회 비활성화 - 모든 값을 0으로 반환]
        """
        print("   ℹ️ 거래 통계 조회 비활성화 - 기본값 반환")
        
        return {
            'total_trades': 0,
            'completed_trades': 0,
            'profitable_trades': 0,
            'win_rate': 0.0,
            'avg_profit_rate': 0.0,
            'total_profit_loss': 0.0,
            'total_fees': 0.0
        }
    
    # "거래 정보와 GPT 컨텍스트를 함께 조회하는 메서드" (인자: self, trade_id)
    def get_trade_with_context(self, trade_id: str) -> Optional[Dict]:
        """
        [수정됨: GPT 컨텍스트 조회 비활성화 - None 반환]
        """
        print(f"   ℹ️ GPT 컨텍스트 조회 비활성화 - None 반환 (ID: {trade_id})")
        return None
    
    # "특정 거래 ID로 거래 정보를 조회하는 메서드" (인자: self, trade_id)
    def get_trade_by_id(self, trade_id: str) -> Optional[Dict]:
        """
        [추가됨: Reflector에서 참조하는 메서드 - 비활성화]
        """
        print(f"   ℹ️ 거래 ID 조회 비활성화 - None 반환 (ID: {trade_id})")
        return None
    
    def get_trade(self, trade_id: str) -> Optional[Dict]:
        """
        특정 거래 ID로 거래 정보 조회 (V14: 분할 익절 데이터 포함)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM trade_log WHERE trade_id = ?
            """, (trade_id,))
            
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            
            return None