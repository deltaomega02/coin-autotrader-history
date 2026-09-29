# database/db_manager.py
# SQLite CRUD 및 통계 쿼리
# 포지션, 중간 점검, 펀딩비 기록 관리

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from config import get_logger

logger = get_logger("db_manager")

DB_PATH = Path(__file__).parent / "metis_futures.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DBManager:
    """
    SQLite 데이터베이스 매니저
    
    포지션, 중간 점검, 펀딩비 기록 CRUD
    """
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """데이터베이스 초기화"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            with open(SCHEMA_PATH, "r") as f:
                conn.executescript(f.read())
            conn.commit()
            logger.info(f"데이터베이스 초기화 완료: {self.db_path}")
        finally:
            if conn:
                conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """커넥션 반환"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ========== Position CRUD ==========
    
    def create_position(
        self,
        direction: str,
        leverage: int,
        entry_price: float,
        entry_quantity: float,
        stop_loss_price: float,
        take_profit_price: float,
        liquidation_price: float,
        confidence_score: int,
        ai_reason: str = "",
        strategy_json: str = "",
        entry_fee: float = 0
    ) -> str:
        """
        새 포지션 생성
        
        Args:
            direction: 포지션 방향 (LONG | SHORT)
            leverage: 레버리지 배수
            entry_price: 진입가
            entry_quantity: 진입 수량
            stop_loss_price: 손절가
            take_profit_price: 익절가
            liquidation_price: 청산가
            confidence_score: AI 확신도
            ai_reason: AI 판단 근거
            strategy_json: 전략 JSON
            entry_fee: 진입 수수료
        
        Returns:
            position_uuid
        """
        position_uuid = str(uuid.uuid4())
        entry_timestamp = datetime.now().isoformat()
        
        conn = None
        try:
            conn = self._get_connection()
            conn.execute("""
                INSERT INTO futures_positions (
                    position_uuid, direction, leverage, entry_price, entry_quantity,
                    entry_timestamp, stop_loss_price, take_profit_price, liquidation_price,
                    confidence_score, ai_reason, strategy_json, status, entry_fee
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            """, (
                position_uuid, direction, leverage, entry_price, entry_quantity,
                entry_timestamp, stop_loss_price, take_profit_price, liquidation_price,
                confidence_score, ai_reason, strategy_json, entry_fee
            ))
            conn.commit()
            logger.info(f"포지션 생성: {position_uuid[:8]}... {direction} {leverage}x 수수료={entry_fee:.4f}")
            return position_uuid
        finally:
            if conn:
                conn.close()
    
    def get_active_position(self) -> Optional[Dict[str, Any]]:
        """활성 포지션 조회"""
        conn = None
        try:
            conn = self._get_connection()
            row = conn.execute("""
                SELECT * FROM futures_positions WHERE status = 'ACTIVE' LIMIT 1
            """).fetchone()
            
            if row:
                return dict(row)
            return None
        finally:
            if conn:
                conn.close()
    
    def close_position(
        self,
        position_uuid: str,
        exit_price: float,
        exit_reason: str,
        realized_pnl: float,
        realized_pnl_percentage: float,
        exit_fee: float = 0
    ) -> bool:
        """
        포지션 청산 기록
        
        Args:
            position_uuid: 포지션 UUID
            exit_price: 청산가
            exit_reason: 청산 사유
            realized_pnl: 실현 손익 (수수료 차감 후)
            realized_pnl_percentage: 실현 손익률
            exit_fee: 청산 수수료
        
        Returns:
            성공 여부
        """
        exit_timestamp = datetime.now().isoformat()
        
        conn = None
        try:
            conn = self._get_connection()
            
            # 진입 수수료 조회
            row = conn.execute("""
                SELECT entry_fee FROM futures_positions WHERE position_uuid = ?
            """, (position_uuid,)).fetchone()
            
            entry_fee = row["entry_fee"] if row else 0
            total_fee = entry_fee + exit_fee
            
            conn.execute("""
                UPDATE futures_positions SET
                    status = 'CLOSED',
                    exit_price = ?,
                    exit_timestamp = ?,
                    exit_reason = ?,
                    realized_pnl = ?,
                    realized_pnl_percentage = ?,
                    exit_fee = ?,
                    total_fee = ?
                WHERE position_uuid = ?
            """, (
                exit_price, exit_timestamp, exit_reason,
                realized_pnl, realized_pnl_percentage,
                exit_fee, total_fee,
                position_uuid
            ))
            conn.commit()
            
            logger.info(
                f"포지션 청산: {position_uuid[:8]}... {exit_reason} "
                f"PnL={realized_pnl:.2f} 총수수료={total_fee:.4f}"
            )
            return True
        finally:
            if conn:
                conn.close()
    
    def update_position_targets(
        self,
        position_uuid: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None
    ) -> bool:
        """손절/익절가 수정"""
        updates = []
        params = []
        
        if stop_loss_price is not None:
            updates.append("stop_loss_price = ?")
            params.append(stop_loss_price)
        
        if take_profit_price is not None:
            updates.append("take_profit_price = ?")
            params.append(take_profit_price)
        
        if not updates:
            return False
        
        params.append(position_uuid)
        
        conn = None
        try:
            conn = self._get_connection()
            conn.execute(f"""
                UPDATE futures_positions SET {', '.join(updates)}
                WHERE position_uuid = ?
            """, params)
            conn.commit()
            return True
        finally:
            if conn:
                conn.close()
    
    # ========== Recheck Log ==========
    
    def log_recheck(
        self,
        position_uuid: str,
        current_price: float,
        unrealized_pnl: float,
        unrealized_pnl_percentage: float,
        ai_decision: str,
        ai_reason: str = "",
        modifications_json: str = ""
    ) -> int:
        """중간 점검 로그 기록"""
        recheck_timestamp = datetime.now().isoformat()
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                INSERT INTO position_rechecks (
                    position_uuid, recheck_timestamp, current_price,
                    unrealized_pnl, unrealized_pnl_percentage,
                    ai_decision, ai_reason, modifications_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position_uuid, recheck_timestamp, current_price,
                unrealized_pnl, unrealized_pnl_percentage,
                ai_decision, ai_reason, modifications_json
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            if conn:
                conn.close()
    
    def get_recheck_count(self, position_uuid: str) -> int:
        """
        특정 포지션의 중간 점검 횟수 조회
        
        Args:
            position_uuid: 포지션 UUID
        
        Returns:
            중간 점검 횟수
        """
        conn = None
        try:
            conn = self._get_connection()
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM position_rechecks
                WHERE position_uuid = ?
            """, (position_uuid,)).fetchone()
            return row["cnt"] if row else 0
        finally:
            if conn:
                conn.close()
    
    def get_last_recheck(self, position_uuid: str) -> Optional[Dict[str, Any]]:
        """
        직전 중간 점검 기록 조회

        Args:
            position_uuid: 포지션 UUID

        Returns:
            직전 점검 딕셔너리 (없으면 None)
            {current_price, unrealized_pnl_percentage, ai_decision, recheck_timestamp}
        """
        conn = None
        try:
            conn = self._get_connection()
            row = conn.execute("""
                SELECT current_price, unrealized_pnl_percentage, ai_decision, recheck_timestamp
                FROM position_rechecks
                WHERE position_uuid = ?
                ORDER BY id DESC LIMIT 1
            """, (position_uuid,)).fetchone()
            return dict(row) if row else None
        finally:
            if conn:
                conn.close()

    def get_peak_pnl(self, position_uuid: str) -> float:
        """
        해당 포지션의 중간 점검 중 최고 PnL 조회

        Args:
            position_uuid: 포지션 UUID

        Returns:
            최고 미실현 수익률 (점검 기록 없으면 0.0)
        """
        conn = None
        try:
            conn = self._get_connection()
            row = conn.execute("""
                SELECT MAX(unrealized_pnl_percentage) as peak
                FROM position_rechecks
                WHERE position_uuid = ?
            """, (position_uuid,)).fetchone()
            return float(row["peak"]) if row and row["peak"] is not None else 0.0
        finally:
            if conn:
                conn.close()

    # ========== Funding History ==========
    
    def log_funding(
        self,
        position_uuid: str,
        funding_rate: float,
        funding_fee: float
    ) -> int:
        """펀딩비 기록"""
        funding_time = datetime.now().isoformat()
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                INSERT INTO funding_history (
                    position_uuid, funding_time, funding_rate, funding_fee
                ) VALUES (?, ?, ?, ?)
            """, (position_uuid, funding_time, funding_rate, funding_fee))
            conn.commit()
            return cursor.lastrowid
        finally:
            if conn:
                conn.close()
    
    def get_total_funding_fee(self, position_uuid: str) -> float:
        """포지션의 누적 펀딩비 조회"""
        conn = None
        try:
            conn = self._get_connection()
            row = conn.execute("""
                SELECT COALESCE(SUM(funding_fee), 0) as total
                FROM funding_history
                WHERE position_uuid = ?
            """, (position_uuid,)).fetchone()
            return row["total"] if row else 0
        finally:
            if conn:
                conn.close()
    
    # ========== Statistics ==========
    
    def get_trade_stats(self, days: int = 7) -> Dict[str, Any]:
        """거래 통계 조회"""
        conn = None
        try:
            conn = self._get_connection()
            total = conn.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl_percentage) as avg_pnl_pct,
                    SUM(total_fee) as total_fees
                FROM futures_positions
                WHERE status = 'CLOSED'
                AND created_at >= datetime('now', ?)
            """, (f'-{days} days',)).fetchone()
            
            return {
                "total_trades": total["total_trades"] or 0,
                "wins": total["wins"] or 0,
                "losses": total["losses"] or 0,
                "win_rate": (total["wins"] / total["total_trades"] * 100) if total["total_trades"] else 0,
                "total_pnl": total["total_pnl"] or 0,
                "avg_pnl_pct": total["avg_pnl_pct"] or 0,
                "total_fees": total["total_fees"] or 0
            }
        finally:
            if conn:
                conn.close()
    
    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """최근 거래 내역"""
        conn = None
        try:
            conn = self._get_connection()
            rows = conn.execute("""
                SELECT * FROM futures_positions
                WHERE status = 'CLOSED'
                ORDER BY exit_timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
            
            return [dict(row) for row in rows]
        finally:
            if conn:
                conn.close()


# 싱글톤 인스턴스
db_manager = DBManager()