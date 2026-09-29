#!/usr/bin/env python3
"""
HERMES Clean Protocol
======================
1. 모든 열린 포지션 시장가 청산
2. DB 활성 포지션 정리
3. 상태 확인
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import setup_logging, get_logger, TRADING
from exchange.bybit_client import bybit_client
from database.db_manager import db_manager

setup_logging()
logger = get_logger("clean_protocol")


def main():
    print("=" * 60)
    print("HERMES Clean Protocol")
    print("=" * 60)

    # 1. Bybit 포지션 확인 및 청산
    print("\n[1] Bybit 포지션 확인...")
    closed_count = 0

    for symbol in TRADING.SYMBOLS:
        pos = bybit_client.get_position(symbol)
        if pos and pos.get("size", 0) > 0:
            side = pos.get("side", "")
            size = pos["size"]
            entry = pos.get("entry_price", 0)
            pnl = pos.get("unrealized_pnl", 0)

            print(f"  ⚠ {symbol}: {side} {size}개 진입${entry:.2f} 미실현PnL=${pnl:.2f}")

            # 시장가 청산
            direction = "LONG" if side == "Buy" else "SHORT"
            close_side = "Sell" if direction == "LONG" else "Buy"

            try:
                result = bybit_client.place_market_order(
                    symbol=symbol,
                    side=close_side,
                    qty=size,
                    reduce_only=True,
                )
                if result and result.get("order_id"):
                    print(f"  ✓ {symbol} 청산 완료: {result['order_id']}")
                    closed_count += 1
                else:
                    print(f"  ✗ {symbol} 청산 실패: {result}")
            except Exception as e:
                print(f"  ✗ {symbol} 청산 에러: {e}")
        else:
            print(f"  ✓ {symbol}: 포지션 없음")

    # 2. DB 활성 포지션 정리
    print(f"\n[2] DB 활성 포지션 정리...")
    active = db_manager.get_active_positions()

    if active:
        for pos in active:
            uuid = pos["position_uuid"]
            sym = pos.get("symbol", "?")
            direction = pos.get("direction", "?")
            print(f"  DB 활성: {sym} {direction} UUID={uuid[:8]}...")

            # 강제 청산 처리
            try:
                db_manager.close_position(
                    position_uuid=uuid,
                    exit_price=0,
                    exit_reason="CLEAN_PROTOCOL",
                    realized_pnl=0,
                    realized_pnl_percentage=0,
                    exit_fee=0,
                )
                print(f"  ✓ DB 청산 완료: {uuid[:8]}...")
            except Exception as e:
                print(f"  ✗ DB 청산 실패: {e}")
    else:
        print("  ✓ 활성 포지션 없음")

    # 3. 최종 상태 확인
    print(f"\n[3] 최종 상태 확인...")
    wallet = bybit_client.get_wallet_balance()
    balance = wallet.get("available_balance", 0)
    print(f"  잔고: ${balance:.2f}")

    remaining = db_manager.get_active_positions()
    print(f"  DB 활성 포지션: {len(remaining)}개")

    for symbol in TRADING.SYMBOLS:
        pos = bybit_client.get_position(symbol)
        has = pos and pos.get("size", 0) > 0
        print(f"  Bybit {symbol}: {'포지션 있음 ⚠' if has else '없음 ✓'}")

    print(f"\n  Bybit 청산: {closed_count}건")
    print(f"  DB 정리: {len(active) if active else 0}건")

    print("\n" + "=" * 60)
    print("Clean Protocol 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
