# data/upbit_client.py
# "업비트 거래소 API와 통신하여 시장 데이터 조회 및 거래를 실행하는 클라이언트 파일"

import pyupbit
import time
import pandas as pd
from typing import Dict, List, Optional
from config.settings import settings

class UpbitClient:

    # "업비트 API 클라이언트를 초기화하고 공개/개인 API를 설정하는 메서드" (인자: self)
    def __init__(self):
        self.public_client = None  

        if settings.UPBIT_ACCESS_KEY and settings.UPBIT_SECRET_KEY:
            try:
                self.private_client = pyupbit.Upbit(
                    settings.UPBIT_ACCESS_KEY, 
                    settings.UPBIT_SECRET_KEY
                )
                print("✅ 업비트 개인 API 클라이언트 초기화 성공")
            except Exception as e:
                print(f"❌ 업비트 개인 API 클라이언트 초기화 실패: {e}")
                self.private_client = None
        else:
            print("⚠️ 업비트 API 키가 없어 공개 API만 사용")
            self.private_client = None
        
        self.last_request_time = 0
        self.request_count = 0
    
    # "API 호출 속도를 제한하여 제한 초과를 방지하는 메서드" (인자: self)
    def _rate_limit(self):
        current_time = time.time()
        if current_time - self.last_request_time < 0.125:
            time.sleep(0.125 - (current_time - self.last_request_time))
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    # "거래대금 상위 20개 코인 목록을 조회하는 메서드 (최적화 버전)" (인자: self)
    def get_top_20_coins(self) -> List[str]:
        """프랙탈 분석에 최적화된 상위 20개 코인 선정"""
        try:
            self._rate_limit()
            tickers = pyupbit.get_tickers(fiat="KRW")
            
            if not tickers:
                print("❌ KRW 마켓 티커 조회 실패")
                return []

            self._rate_limit()
            ticker_data = pyupbit.get_current_price(tickers)
            
            if not ticker_data:
                print("❌ 티커 현재가 정보 조회 실패")
                return []

            volumes = {}

            # 거래대금 계산
            for ticker in tickers:
                self._rate_limit()
                try:
                    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
                    if df is not None and not df.empty:
                        volume_24h = df.iloc[-1]['volume'] * df.iloc[-1]['close']
                        volumes[ticker] = volume_24h
                except Exception as e:
                    print(f"⚠️ {ticker} 거래량 조회 실패: {e}")
                    continue
            
            if not volumes:
                print("❌ 유효한 거래량 데이터 없음")
                return []

            # 거래대금 기준 상위 10개 선정
            sorted_tickers = sorted(volumes.items(), key=lambda x: x[1], reverse=True)
            
            # BTC 제외하고 상위 20개 선정
            top_20 = []
            for ticker, volume in sorted_tickers:
                if ticker != "KRW-BTC":  # BTC는 별도로 분석하므로 제외
                    top_20.append(ticker)
                    if len(top_20) >= 20:  # 20개로 제한
                        break
            
            print(f"✅ 상위 {len(top_20)}개 알트코인 조회 완료")
            print(f"   선정 코인: {', '.join([t.replace('KRW-', '') for t in top_20[:5]])}...")
            
            return top_20
            
        except Exception as e:
            print(f"❌ 상위 10개 코인 조회 중 오류: {e}")
            return []
    
    # "거래대금 상위 20개 코인 목록을 조회하는 메서드" (인자: self)
    def get_top_20_coins(self) -> List[str]:
        """기존 호환성을 위해 유지되는 메서드"""
        try:
            self._rate_limit()
            tickers = pyupbit.get_tickers(fiat="KRW")
            
            if not tickers:
                print("❌ KRW 마켓 티커 조회 실패")
                return []

            self._rate_limit()
            ticker_data = pyupbit.get_current_price(tickers)
            
            if not ticker_data:
                print("❌ 티커 현재가 정보 조회 실패")
                return []

            volumes = {}

            for ticker in tickers:
                self._rate_limit()
                try:
                    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
                    if df is not None and not df.empty:
                        volume_24h = df.iloc[-1]['volume'] * df.iloc[-1]['close']
                        volumes[ticker] = volume_24h
                except Exception as e:
                    print(f"⚠️ {ticker} 거래량 조회 실패: {e}")
                    continue
            
            if not volumes:
                print("❌ 유효한 거래량 데이터 없음")
                return []

            sorted_tickers = sorted(volumes.items(), key=lambda x: x[1], reverse=True)
            top_30 = [ticker for ticker, _ in sorted_tickers[:100]]
            
            print(f"✅ 상위 {len(top_30)}개 코인 조회 완료")
            return top_30
            
        except Exception as e:
            print(f"❌ 상위 20개 코인 조회 중 오류: {e}")
            return []
    
    # "유동성과 시장 관심도가 높은 핵심 코인 필터링 메서드" (인자: self, tickers)
    def filter_high_liquidity_coins(self, tickers: List[str]) -> List[str]:
        """유동성과 시장 관심도가 높은 코인만 필터링"""
        filtered = []
        
        for ticker in tickers:
            try:
                self._rate_limit()
                df = pyupbit.get_ohlcv(ticker, interval="minute60", count=24)
                
                if df is not None and not df.empty:
                    # 24시간 평균 거래대금
                    avg_volume_krw = (df['volume'] * df['close']).mean()
                    
                    # 최소 거래대금 기준 (예: 10억원)
                    if avg_volume_krw > 1_000_000_000:
                        filtered.append(ticker)
                        
            except Exception as e:
                continue
        
        return filtered[:10]  # 최대 10개로 제한
    
    # "특정 코인의 다양한 시간대별 OHLCV 데이터를 수집하는 메서드" (인자: self, ticker, intervals)
    def get_market_data(self, ticker: str, intervals: List[str] = None) -> Dict:
        if intervals is None:
            intervals = ["minute5", "minute60", "minute240", "day"]
        
        market_data = {"ticker": ticker}
        
        for interval in intervals:
            self._rate_limit()
            try:
                df = pyupbit.get_ohlcv(ticker, interval=interval, count=200)
                if df is not None and not df.empty:
                    market_data[interval] = df.to_dict('records')
                else:
                    market_data[interval] = []
            except Exception as e:
                print(f"❌ {ticker} {interval} 데이터 조회 실패: {e}")
                market_data[interval] = []
        
        return market_data
    
    # "특정 코인의 현재가를 조회하는 메서드" (인자: self, ticker)
    def get_current_price(self, ticker: str) -> Optional[float]:
        self._rate_limit()
        try:
            price = pyupbit.get_current_price(ticker)
            if price:
                return round(float(price), 8)
            return None
        except Exception as e:
            print(f"❌ {ticker} 현재가 조회 실패: {e}")
            return None
    
    # "호가창 데이터를 조회하는 메서드" (인자: self, ticker)
    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """호가창 정보 조회 (Phase 2 심층 분석용)"""
        self._rate_limit()
        try:
            orderbook = pyupbit.get_orderbook(ticker)
            if orderbook and len(orderbook) > 0:
                ob = orderbook[0]
                return {
                    'ask_price': float(ob['orderbook_units'][0]['ask_price']),
                    'bid_price': float(ob['orderbook_units'][0]['bid_price']),
                    'total_ask_size': float(ob['total_ask_size']),
                    'total_bid_size': float(ob['total_bid_size']),
                    'timestamp': ob['timestamp']
                }
            return None
        except Exception as e:
            print(f"⚠️ {ticker} 호가창 조회 실패: {e}")
            return None
    
    # "최근 체결 내역을 조회하는 메서드" (인자: self, ticker, count)
    def get_recent_trades(self, ticker: str, count: int = 20) -> Optional[List[Dict]]:
        """최근 체결 내역 조회 (Phase 2 심층 분석용)"""
        self._rate_limit()
        try:
            trades = pyupbit.get_ticks(ticker, count=count)
            if trades:
                return [
                    {
                        'ask_bid': trade['ask_bid'],
                        'volume': float(trade['trade_volume']),
                        'price': float(trade['trade_price']),
                        'timestamp': trade['timestamp']
                    }
                    for trade in trades
                ]
            return None
        except Exception as e:
            print(f"⚠️ {ticker} 체결 내역 조회 실패: {e}")
            return None
    
    # "지정가 매수 주문을 실행하는 메서드" (인자: self, ticker, price, volume)
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> Optional[str]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return None
        
        try:
            result = self.private_client.buy_limit_order(ticker, price, volume)
            if result and 'uuid' in result:
                print(f"✅ 지정가 매수 주문 성공: {result['uuid']}")
                return result['uuid']
            else:
                print(f"❌ 지정가 매수 주문 실패: 응답 없음")
                return None
        except Exception as e:
            print(f"❌ 지정가 매수 주문 실패: {e}")
            return None
    
    # "지정가 매도 주문을 실행하는 메서드" (인자: self, ticker, price, volume)
    def sell_limit_order(self, ticker: str, price: float, volume: float) -> Optional[str]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return None
        
        try:
            result = self.private_client.sell_limit_order(ticker, price, volume)
            if result and 'uuid' in result:
                print(f"✅ 지정가 매도 주문 성공: {result['uuid']}")
                return result['uuid']
            else:
                print(f"❌ 지정가 매도 주문 실패: 응답 없음")
                return None
        except Exception as e:
            print(f"❌ 지정가 매도 주문 실패: {e}")
            return None
    
    # "시장가 매수 주문을 실행하는 메서드" (인자: self, ticker, price)
    def buy_market_order(self, ticker: str, price: float) -> Optional[str]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return None
        
        try:
            result = self.private_client.buy_market_order(ticker, price)
            if result and 'uuid' in result:
                print(f"✅ 시장가 매수 주문 성공: {result['uuid']}")
                return result['uuid']
            else:
                print(f"❌ 시장가 매수 주문 실패: 응답 없음")
                return None
        except Exception as e:
            print(f"❌ 시장가 매수 주문 실패: {e}")
            return None
    
    # "시장가 매도 주문을 실행하는 메서드" (인자: self, ticker, volume)
    def sell_market_order(self, ticker: str, volume: float) -> Optional[str]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return None
        
        try:
            result = self.private_client.sell_market_order(ticker, volume)
            if result and 'uuid' in result:
                print(f"✅ 시장가 매도 주문 성공: {result['uuid']}")
                return result['uuid']
            else:
                print(f"❌ 시장가 매도 주문 실패: 응답 없음")
                return None
        except Exception as e:
            print(f"❌ 시장가 매도 주문 실패: {e}")
            return None
    
    # "미체결 주문을 취소하는 메서드" (인자: self, order_id)
    def cancel_order(self, order_id: str) -> bool:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return False
        
        try:
            result = self.private_client.cancel_order(order_id)
            if result:
                print(f"✅ 주문 취소 성공: {order_id}")
                return True
            else:
                print(f"❌ 주문 취소 실패: {order_id}")
                return False
        except Exception as e:
            print(f"❌ 주문 취소 실패 ({order_id}): {e}")
            return False
    
    # "특정 주문의 상태와 체결 정보를 조회하는 메서드" (인자: self, order_id)
    def get_order_status(self, order_id: str) -> Optional[Dict]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return None
        
        try:
            order_info = self.private_client.get_order(order_id)
            
            if not order_info:
                print(f"⚠️ 주문 정보 없음: {order_id}")
                return None

            state = order_info.get('state', 'unknown')
            print(f"📋 주문 상태 조회: {order_id} - {state}")
            
            return order_info
            
        except Exception as e:
            print(f"❌ 주문 상태 조회 실패 ({order_id}): {e}")
            return None
    
    # "특정 통화의 잔고를 조회하는 메서드" (인자: self, currency)
    def get_balance(self, currency: str = "KRW") -> float:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return 0.0
        
        try:
            balances = self.private_client.get_balances()
            if not balances:
                print("❌ 잔고 정보 조회 실패")
                return 0.0
            
            for balance in balances:
                if balance.get('currency') == currency:
                    balance_amount = float(balance.get('balance', 0))
                    print(f"💰 {currency} 잔고: {balance_amount:,.0f}")
                    return balance_amount
            
            print(f"⚠️ {currency} 잔고 정보 없음")
            return 0.0
            
        except Exception as e:
            print(f"❌ {currency} 잔고 조회 실패: {e}")
            return 0.0
    
    # "전체 보유 자산 목록을 조회하는 메서드" (인자: self)
    def get_balances(self) -> List[Dict]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return []
        
        try:
            balances = self.private_client.get_balances()
            if balances:
                print(f"📊 전체 잔고 조회 완료: {len(balances)}개 통화")
                return balances
            else:
                print("⚠️ 잔고 정보 없음")
                return []
        except Exception as e:
            print(f"❌ 전체 잔고 조회 실패: {e}")
            return []
    
    # "주문 내역을 조회하는 메서드" (인자: self, ticker, state, limit)
    def get_order_history(self, ticker: str = None, state: str = 'done', limit: int = 100) -> List[Dict]:
        if not self.private_client:
            print("❌ Private client가 초기화되지 않음")
            return []
        
        try:
            orders = self.private_client.get_orders(
                market=ticker,
                state=state,
                page=1,
                limit=limit,
                order_by='desc'
            )
            
            if orders:
                print(f"📋 주문 내역 조회 완료: {len(orders)}개")
                return orders
            else:
                print("📋 주문 내역 없음")
                return []
                
        except Exception as e:
            print(f"❌ 주문 내역 조회 실패: {e}")
            return []
    
    # "API 연결 상태를 확인하는 메서드" (인자: self)
    def verify_connection(self) -> bool:
        try:
            btc_price = self.get_current_price("KRW-BTC")
            if not btc_price:
                print("❌ 공개 API 연결 실패")
                return False
            
            print(f"✅ 공개 API 연결 성공 (BTC: {btc_price:,.0f}원)")

            if self.private_client:
                krw_balance = self.get_balance("KRW")
                print(f"✅ 개인 API 연결 성공 (KRW 잔고: {krw_balance:,.0f}원)")
            else:
                print("⚠️ 개인 API 키 미설정 (조회 전용 모드)")
            
            return True
            
        except Exception as e:
            print(f"❌ 연결 확인 실패: {e}")
            return False