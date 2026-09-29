#!/usr/bin/env python3
# update_db.py
# METIS-F 포지션 DB 수동 수정 스크립트
# Bybit 실제 체결 내역 기반으로 잘못 저장된 데이터 수정

import sqlite3
from pathlib import Path
from datetime import datetime

# DB 경로 (프로젝트 구조에 맞게 조정)
DB_PATH = Path(__file__).parent / "database" / "metis_futures.db"

# Bybit 실제 체결 내역 (2026-02-02 12:49:09)
# Contracts: BTCUSDT
# Qty: 0.011
# Entry Price: 76,624.00
# Exit Price: 75,695.10
# Trade Type: Close Short
# Closed P&L: +9.3394 USDT (Win)
# Opening Fee: 0.4635752 USDT
# Closing Fee: 0.45795536 USDT
# Funding Fee: -0.0431 USDT (지불)

CORRECT_DATA = {
    "exit_price": 75695.10,
    "exit_reason": "STOP_LOSS",  # 트레일링 스탑 (서버 SL 체결)
    "realized_pnl": 9.3394,  # Bybit Closed P&L (수수료 차감 후)
    "entry_fee": 0.4635752,
    "exit_fee": 0.45795536,
    "total_fee": 0.92153056,  # entry + exit
    "funding_fee": -0.0431,  # 지불 (음수)
}

# 수정 대상 포지션 UUID (부분 매칭)
TARGET_UUID_PREFIX = "94709fd5"  # 로그에서 확인: 94709fd5-225d-47cc-b71e-2d16c4bb443d


def get_target_position(conn, uuid_prefix):
    """
    UUID prefix로 수정 대상 포지션 조회
    """
    cursor = conn.execute("""
        SELECT id, position_uuid, direction, entry_price, entry_quantity, 
               leverage, exit_price, realized_pnl, realized_pnl_percentage,
               entry_fee, exit_fee, total_fee, exit_reason
        FROM futures_positions
        WHERE position_uuid LIKE ?
        ORDER BY exit_timestamp DESC
        LIMIT 1
    """, (f"{uuid_prefix}%",))
    return cursor.fetchone()


def get_latest_closed_position(conn):
    """
    가장 최근 CLOSED 포지션 조회 (폴백용)
    """
    cursor = conn.execute("""
        SELECT id, position_uuid, direction, entry_price, entry_quantity, 
               leverage, exit_price, realized_pnl, realized_pnl_percentage,
               entry_fee, exit_fee, total_fee, exit_reason
        FROM futures_positions
        WHERE status = 'CLOSED'
        ORDER BY exit_timestamp DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def calculate_pnl_percentage(entry_price, exit_price, quantity, direction, leverage):
    """손익률 계산"""
    if direction == "LONG":
        pnl = (exit_price - entry_price) * quantity
    else:  # SHORT
        pnl = (entry_price - exit_price) * quantity
    
    margin_used = (quantity * entry_price) / leverage
    pnl_pct = (pnl / margin_used) * 100 if margin_used > 0 else 0
    return pnl_pct


def main():
    if not DB_PATH.exists():
        print(f"[ERROR] DB 파일 없음: {DB_PATH}")
        print("DB 경로를 확인하세요. 현재 경로:")
        print(f"  - {DB_PATH}")
        print("\n다른 경로 시도:")
        alt_paths = [
            Path(__file__).parent / "metis_futures.db",
            Path(__file__).parent.parent / "database" / "metis_futures.db",
            Path.home() / "metis-futures" / "database" / "metis_futures.db",
        ]
        for p in alt_paths:
            if p.exists():
                print(f"  [FOUND] {p}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("=" * 60)
    print("METIS-F DB 수정 스크립트")
    print("=" * 60)
    print(f"\n[대상] 2026-02-02 12:49 체결 - 펀딩비 누락 수정")
    print(f"[원인] 펀딩비 조회 API 오류 (SETTLEMENT 타입 미인식)")
    
    # 수정 대상 포지션 조회
    position = get_target_position(conn, TARGET_UUID_PREFIX)
    
    if not position:
        print(f"\n[INFO] UUID prefix '{TARGET_UUID_PREFIX}'로 검색 실패, 최근 CLOSED 포지션 조회")
        position = get_latest_closed_position(conn)
    
    if not position:
        print("[ERROR] 수정할 포지션이 없습니다.")
        conn.close()
        return
    
    pos_id = position["id"]
    pos_uuid = position["position_uuid"]
    
    print(f"\n[수정 대상 포지션]")
    print(f"  ID: {pos_id}")
    print(f"  UUID: {pos_uuid}")
    print(f"  방향: {position['direction']}")
    print(f"  진입가: {position['entry_price']:,.2f}")
    print(f"  수량: {position['entry_quantity']}")
    print(f"  레버리지: {position['leverage']}x")
    
    print(f"\n[현재 DB 값 (잘못된 값)]")
    print(f"  청산가: {position['exit_price']:,.2f}")
    print(f"  실현 PnL: {position['realized_pnl']:.4f} USDT")
    print(f"  PnL%: {position['realized_pnl_percentage']:.2f}%")
    print(f"  청산 사유: {position['exit_reason']}")
    print(f"  진입 수수료: {position['entry_fee']:.6f}")
    print(f"  청산 수수료: {position['exit_fee']:.6f}  <-- 문제: 실제는 0.4224")
    print(f"  총 수수료: {position['total_fee']:.6f}")
    
    # 손익률 재계산 (순손익 기준)
    margin_used = (position["entry_quantity"] * position["entry_price"]) / position["leverage"]
    net_pnl_pct = (CORRECT_DATA["realized_pnl"] / margin_used) * 100 if margin_used > 0 else 0
    
    print(f"\n[수정할 값 (Bybit 실제 체결)]")
    print(f"  청산가: {CORRECT_DATA['exit_price']:,.2f}")
    print(f"  실현 PnL: {CORRECT_DATA['realized_pnl']:.4f} USDT")
    print(f"  PnL%: {net_pnl_pct:.2f}%")
    print(f"  청산 사유: {CORRECT_DATA['exit_reason']}")
    print(f"  진입 수수료: {CORRECT_DATA['entry_fee']:.6f}")
    print(f"  청산 수수료: {CORRECT_DATA['exit_fee']:.6f}  <-- 수정됨")
    print(f"  총 수수료: {CORRECT_DATA['total_fee']:.6f}")
    
    print(f"\n[펀딩비 차이]")
    print(f"  기존 펀딩비: 0.0000")
    print(f"  실제 펀딩비: {CORRECT_DATA['funding_fee']:.4f} USDT")
    print(f"  차이: {CORRECT_DATA['funding_fee']:.4f} USDT (누락분)")
    
    print("\n" + "-" * 60)
    confirm = input("위 내용으로 DB를 수정하시겠습니까? (y/N): ")
    
    if confirm.lower() != 'y':
        print("[취소] 수정하지 않았습니다.")
        conn.close()
        return
    
    # DB 업데이트
    try:
        conn.execute("""
            UPDATE futures_positions SET
                exit_price = ?,
                exit_reason = ?,
                realized_pnl = ?,
                realized_pnl_percentage = ?,
                entry_fee = ?,
                exit_fee = ?,
                total_fee = ?
            WHERE id = ?
        """, (
            CORRECT_DATA["exit_price"],
            CORRECT_DATA["exit_reason"],
            CORRECT_DATA["realized_pnl"],
            round(net_pnl_pct, 2),
            CORRECT_DATA["entry_fee"],
            CORRECT_DATA["exit_fee"],
            CORRECT_DATA["total_fee"],
            pos_id
        ))
        
        # 펀딩비 기록 확인 (이 거래는 펀딩비 0)
        existing_funding = conn.execute("""
            SELECT id FROM funding_history WHERE position_uuid = ?
        """, (pos_uuid,)).fetchone()
        
        if existing_funding:
            conn.execute("""
                UPDATE funding_history SET funding_fee = ?
                WHERE position_uuid = ?
            """, (CORRECT_DATA["funding_fee"], pos_uuid))
            print("[펀딩비] 기존 기록 업데이트")
        elif CORRECT_DATA["funding_fee"] != 0:
            conn.execute("""
                INSERT INTO funding_history (position_uuid, funding_time, funding_rate, funding_fee)
                VALUES (?, ?, 0, ?)
            """, (pos_uuid, datetime.now().isoformat(), CORRECT_DATA["funding_fee"]))
            print("[펀딩비] 새 기록 추가")
        
        conn.commit()
        print("\n[완료] DB 수정 성공!")
        
        # 수정 결과 확인
        updated = conn.execute("""
            SELECT exit_price, realized_pnl, realized_pnl_percentage, 
                   entry_fee, exit_fee, total_fee, exit_reason
            FROM futures_positions WHERE id = ?
        """, (pos_id,)).fetchone()
        
        print(f"\n[수정 후 확인]")
        print(f"  청산가: {updated['exit_price']:,.2f}")
        print(f"  실현 PnL: {updated['realized_pnl']:.4f} USDT")
        print(f"  PnL%: {updated['realized_pnl_percentage']:.2f}%")
        print(f"  청산 사유: {updated['exit_reason']}")
        print(f"  진입 수수료: {updated['entry_fee']:.6f}")
        print(f"  청산 수수료: {updated['exit_fee']:.6f}")
        print(f"  총 수수료: {updated['total_fee']:.6f}")
        
    except Exception as e:
        print(f"[ERROR] DB 수정 실패: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    main()