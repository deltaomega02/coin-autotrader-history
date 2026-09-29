"""Bybit 잔고 확인 (Spot + Futures + Funding 계정 모두).

사용:
  pip install pybit python-dotenv
  cd ~/ATHENA
  python3 check_balance.py

ATHENA용 USDT (Spot)가 얼마 있는지 확인.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 로드 (현재 디렉토리)
load_dotenv(Path(__file__).parent / ".env")

API_KEY = os.getenv("BYBIT_API_KEY", "")
SECRET = os.getenv("BYBIT_SECRET", "")
USE_TESTNET = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"


def main():
    if not API_KEY:
        print("❌ BYBIT_API_KEY 미설정")
        return

    print(f"🔌 Bybit 연결 중... ({'TESTNET' if USE_TESTNET else 'MAINNET'})")
    print(f"   API: {API_KEY[:6]}...{API_KEY[-4:]}")
    print()

    try:
        from pybit.unified_trading import HTTP
    except ImportError:
        print("❌ pybit 미설치")
        print("   해결: pip install pybit python-dotenv")
        return

    session = HTTP(
        testnet=USE_TESTNET,
        api_key=API_KEY,
        api_secret=SECRET,
    )

    # ─ UNIFIED 계정 (Spot + Derivatives 통합) ─
    print("━━━ UNIFIED Account (Spot + Derivatives) ━━━")
    try:
        r = session.get_wallet_balance(accountType="UNIFIED")
        wallets = r.get("result", {}).get("list", [])

        if not wallets:
            print("  잔고 없음")
        else:
            for wallet in wallets:
                total_equity = float(wallet.get("totalEquity", 0))
                total_avail = float(wallet.get("totalAvailableBalance", 0) or 0)
                total_used = float(wallet.get("totalInitialMargin", 0) or 0)

                print(f"  💰 총 자산  ${total_equity:,.2f}")
                print(f"  ✅ 가용     ${total_avail:,.2f}")
                if total_used > 0:
                    print(f"  🔒 사용 중  ${total_used:,.2f} (포지션/주문)")
                print()
                print("  자산별:")

                coins = wallet.get("coin", [])
                for coin in coins:
                    sym = coin["coin"]
                    bal = float(coin.get("walletBalance", 0) or 0)
                    if bal <= 0:
                        continue

                    usd_value = float(coin.get("usdValue", 0) or 0)
                    available = float(coin.get("availableToWithdraw", 0) or 0)

                    print(f"    {sym:8} {bal:>14.6f}  (≈ ${usd_value:,.2f}, 출금가능 {available:.6f})")
    except Exception as e:
        print(f"  ❌ UNIFIED 조회 실패: {e}")

    # ─ FUND 계정 (Funding/Spot 입출금용) ─
    print()
    print("━━━ FUND Account (입출금 지갑) ━━━")
    try:
        r = session.get_wallet_balance(accountType="FUND")
        wallets = r.get("result", {}).get("list", [])
        if not wallets:
            print("  잔고 없음")
        else:
            for wallet in wallets:
                coins = wallet.get("coin", [])
                has_balance = False
                for coin in coins:
                    sym = coin["coin"]
                    bal = float(coin.get("walletBalance", 0) or 0)
                    if bal <= 0:
                        continue
                    has_balance = True
                    print(f"    {sym:8} {bal:>14.6f}")
                if not has_balance:
                    print("  잔고 없음")
    except Exception as e:
        print(f"  ❌ FUND 조회 실패 (또는 비활성): {e}")

    # ─ Spot 시세 (참고) ─
    print()
    print("━━━ 시세 (참고) ━━━")
    try:
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            r = session.get_tickers(category="spot", symbol=sym)
            items = r.get("result", {}).get("list", [])
            if items:
                price = float(items[0].get("lastPrice", 0))
                print(f"  {sym}: ${price:,.2f}")
    except Exception as e:
        print(f"  ❌ 시세 조회 실패: {e}")

    print()
    print("━━━ ATHENA 가동 가이드 ━━━")
    print()
    print("ATHENA는 UNIFIED 계정의 USDT를 사용합니다.")
    print("  - USDT 가용 잔고가 $50+ 권장 (DCA 시작)")
    print("  - $5 미만이면 매수 정지됨")
    print()
    print("자금 이동 (Bybit 앱):")
    print("  - FUND → UNIFIED 계정 이동")
    print("  - 또는 Futures 포지션 청산 후 Spot/UNIFIED로 이동")


if __name__ == "__main__":
    main()
