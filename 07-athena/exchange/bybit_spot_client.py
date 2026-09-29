"""Bybit Spot 클라이언트 (pybit 공식 라이브러리 기반).

pybit가 HMAC SHA256 인증, 시그니처, RECV_WINDOW 등 자동 처리.
직접 구현보다 안정적 (V5 API 변경 시 라이브러리 업데이트로 대응).

설치: pip install pybit
"""

from typing import Dict, Any, Optional, List

from config import BYBIT, ATHENA, get_logger

logger = get_logger("bybit_spot")


class BybitSpotError(Exception):
    pass


class BybitSpotClient:
    """Bybit V5 Spot via pybit.unified_trading.HTTP."""

    def __init__(self):
        self._session = None
        try:
            from pybit.unified_trading import HTTP
            self._session = HTTP(
                testnet=BYBIT.USE_TESTNET,
                api_key=BYBIT.API_KEY or None,
                api_secret=BYBIT.SECRET or None,
            )
            mode = "TESTNET" if BYBIT.USE_TESTNET else "MAINNET"
            authed = "✓auth" if BYBIT.API_KEY else "✗noauth"
            logger.info(f"Bybit Spot 초기화 완료 — {mode} {authed}")
        except ImportError as e:
            logger.error(f"pybit 미설치: {e} — pip install pybit")
        except Exception as e:
            logger.error(f"Bybit Spot 초기화 실패: {e}")

    # ────────────────────────────────────────
    # 시세 / 캔들
    # ────────────────────────────────────────

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """현재 시세."""
        if not self._session:
            return {}
        try:
            r = self._session.get_tickers(category="spot", symbol=symbol)
            items = r.get("result", {}).get("list", [])
            return items[0] if items else {}
        except Exception as e:
            logger.error(f"get_ticker {symbol}: {e}")
            return {}

    def get_kline(self, symbol: str, interval: str = "240",
                  limit: int = 200) -> List[Dict[str, Any]]:
        """OHLCV. interval: 1, 5, 15, 60, 240, D"""
        if not self._session:
            return []
        try:
            r = self._session.get_kline(
                category="spot",
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            raw = r.get("result", {}).get("list", [])
            # 오래된 순 정렬
            candles = []
            for item in reversed(raw):
                candles.append({
                    "timestamp": int(item[0]),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                    "turnover": float(item[6]),
                })
            return candles
        except Exception as e:
            logger.error(f"get_kline {symbol}: {e}")
            return []

    def get_orderbook(self, symbol: str, limit: int = 25) -> Dict[str, Any]:
        if not self._session:
            return {}
        try:
            r = self._session.get_orderbook(category="spot", symbol=symbol, limit=limit)
            return r.get("result", {})
        except Exception as e:
            logger.error(f"get_orderbook {symbol}: {e}")
            return {}

    # ────────────────────────────────────────
    # 잔고
    # ────────────────────────────────────────

    def get_wallet_balance(self) -> Dict[str, float]:
        """Unified Account 자산별 잔고.

        Returns:
            {"USDT": 1230.5, "BTC": 0.012, ...}
        """
        if not self._session or not BYBIT.API_KEY:
            return {}
        try:
            r = self._session.get_wallet_balance(accountType="UNIFIED")
            wallets = r.get("result", {}).get("list", [])
            if not wallets:
                return {}

            balances = {}
            for coin in wallets[0].get("coin", []):
                wallet_balance = float(coin.get("walletBalance", 0) or 0)
                if wallet_balance > 0:
                    balances[coin["coin"]] = wallet_balance
            return balances
        except Exception as e:
            logger.error(f"get_wallet_balance: {e}")
            return {}

    def get_portfolio_value_usdt(self) -> Dict[str, Any]:
        """전체 포트폴리오 USD 가치 + 비중.

        Returns:
            {
              "total_usdt": float,
              "weights": {"BTC": 0.40, ...},
              "values": {"BTC": 492.6, ...},
            }
        """
        balances = self.get_wallet_balance()
        if not balances:
            return {"total_usdt": 0, "weights": {}, "values": {}}

        values = {}
        total = 0.0
        for asset, amount in balances.items():
            if asset == "USDT":
                value = amount
            else:
                symbol = ATHENA.SYMBOLS.get(asset)
                if not symbol:
                    continue  # 모르는 자산 (BNB, etc.) 무시
                ticker = self.get_ticker(symbol)
                price = float(ticker.get("lastPrice", 0) or 0)
                value = amount * price

            values[asset] = value
            total += value

        weights = {a: (v / total if total > 0 else 0) for a, v in values.items()}
        return {
            "total_usdt": total,
            "weights": weights,
            "values": values,
        }

    # ────────────────────────────────────────
    # 주문
    # ────────────────────────────────────────

    def place_market_buy(self, symbol: str, quote_qty: float) -> Dict[str, Any]:
        """Spot 시장가 매수 (USDT 금액 기준).

        Bybit Spot Buy with marketUnit=quoteCoin: qty가 USDT 금액.
        UNIFIED 계정에서 spot 명시: isLeverage=0 (margin 아님).
        """
        if not self._session or not BYBIT.API_KEY:
            raise BybitSpotError("API 키 없음 (인증 필요)")
        try:
            r = self._session.place_order(
                category="spot",
                symbol=symbol,
                side="Buy",
                orderType="Market",
                qty=str(quote_qty),
                marketUnit="quoteCoin",
                isLeverage=0,  # UTA spot (margin X)
            )
            return r.get("result", {})
        except Exception as e:
            raise BybitSpotError(f"매수 실패 {symbol} ${quote_qty}: {e}")

    def place_market_sell(self, symbol: str, base_qty: float) -> Dict[str, Any]:
        """Spot 시장가 매도 (BASE 수량 기준)."""
        if not self._session or not BYBIT.API_KEY:
            raise BybitSpotError("API 키 없음 (인증 필요)")
        try:
            r = self._session.place_order(
                category="spot",
                symbol=symbol,
                side="Sell",
                orderType="Market",
                qty=str(base_qty),
                marketUnit="baseCoin",
                isLeverage=0,  # UTA spot
            )
            return r.get("result", {})
        except Exception as e:
            raise BybitSpotError(f"매도 실패 {symbol} {base_qty}: {e}")

    def get_order_history(self, symbol: Optional[str] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
        if not self._session or not BYBIT.API_KEY:
            return []
        try:
            params = {"category": "spot", "limit": limit}
            if symbol:
                params["symbol"] = symbol
            r = self._session.get_order_history(**params)
            return r.get("result", {}).get("list", [])
        except Exception as e:
            logger.error(f"get_order_history: {e}")
            return []


bybit_spot = BybitSpotClient()
