# data/upbit_client.py - ENHANCED VERSION WITH ORDERBOOK FIX
# "업비트 API 클라이언트 - 정확한 응답 처리 및 에러 핸들링"

import pyupbit
import time
import pandas as pd
from typing import Dict, List, Optional, Any
from config.settings import settings
import json

class UpbitClient:

    def __init__(self):
        # 속성 먼저 초기화 (중요!)
        self.public_client = None
        self.private_client = None
        self.last_request_time = 0
        self.request_count = 0

        # API 초기화
        if settings.UPBIT_ACCESS_KEY and settings.UPBIT_SECRET_KEY:
            try:
                self.private_client = pyupbit.Upbit(
                    settings.UPBIT_ACCESS_KEY, 
                    settings.UPBIT_SECRET_KEY
                )
                print("✅ 업비트 개인 API 초기화 성공")
                
                # API 연결 테스트
                self._test_api_connection()
                
            except Exception as e:
                print(f"❌ 업비트 개인 API 초기화 실패: {e}")
                self.private_client = None
        else:
            print("⚠️ 업비트 API 키 없음 - 공개 API만 사용")
    
    def _test_api_connection(self):
        """API 연결 테스트"""
        try:
            # 잔고 조회로 테스트
            balances = self.get_balances()
            if balances is not None:
                krw_balance = self.get_balance("KRW")
                print(f"   API 테스트 성공 - KRW 잔고: {krw_balance:,.0f}원")
            else:
                print("   ⚠️ API 테스트 실패")
        except Exception as e:
            print(f"   ⚠️ API 테스트 오류: {e}")
    
    def _rate_limit(self):
        """Rate limiting"""
        current_time = time.time()
        if current_time - self.last_request_time < 0.1:  # 100ms
            time.sleep(0.1 - (current_time - self.last_request_time))
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    # ==================== 계좌 관련 ====================
    
    def get_balances(self) -> List[Dict]:
        """전체 잔고 조회 - 업비트 응답 그대로 반환"""
        if not self.private_client:
            return []
        
        try:
            self._rate_limit()
            balances = self.private_client.get_balances()
            
            if balances:
                # 업비트 응답 형식 그대로 반환
                return balances
            return []
            
        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return []
    
    def get_balance(self, currency: str = "KRW") -> float:
        """특정 통화 잔고 조회"""
        if not self.private_client:
            return 0.0
        
        try:
            self._rate_limit()
            balances = self.private_client.get_balances()
            
            if not balances:
                return 0.0
            
            for balance in balances:
                if balance.get('currency') == currency:
                    # balance + locked 합계
                    available = float(balance.get('balance', 0))
                    locked = float(balance.get('locked', 0))
                    return available  # 사용 가능한 잔고만 반환
            
            return 0.0
            
        except Exception as e:
            print(f"❌ {currency} 잔고 조회 실패: {e}")
            return 0.0
    
    def get_coin_balance(self, ticker: str) -> Dict[str, float]:
        """코인 잔고 상세 조회"""
        currency = ticker.replace("KRW-", "")
        
        if not self.private_client:
            return {"balance": 0.0, "locked": 0.0, "avg_buy_price": 0.0}
        
        try:
            self._rate_limit()
            balances = self.private_client.get_balances()
            
            for balance in balances:
                if balance.get('currency') == currency:
                    return {
                        "balance": float(balance.get('balance', 0)),
                        "locked": float(balance.get('locked', 0)),
                        "avg_buy_price": float(balance.get('avg_buy_price', 0)),
                        "unit_currency": balance.get('unit_currency', 'KRW')
                    }
            
            return {"balance": 0.0, "locked": 0.0, "avg_buy_price": 0.0}
            
        except Exception as e:
            print(f"❌ {ticker} 잔고 조회 실패: {e}")
            return {"balance": 0.0, "locked": 0.0, "avg_buy_price": 0.0}
    
    # ==================== 주문 관련 ====================
    
    def buy_market_order(self, ticker: str, amount: float) -> Optional[str]:
        """시장가 매수 - UUID 반환"""
        if not self.private_client:
            return None
        
        try:
            self._rate_limit()
            
            # 최소 주문 금액 체크
            if amount < 5000:
                print(f"❌ 최소 주문 금액 미달: {amount:,.0f}원 < 5,000원")
                return None
            
            print(f"   📤 시장가 매수 요청: {ticker} / {amount:,.0f}원")
            
            result = self.private_client.buy_market_order(ticker, amount)
            
            if result and isinstance(result, dict):
                uuid = result.get('uuid')
                if uuid:
                    print(f"   ✅ 주문 접수: {uuid}")
                    return uuid
                else:
                    print(f"   ❌ UUID 없음: {result}")
            
            return None
            
        except Exception as e:
            print(f"❌ 시장가 매수 실패: {e}")
            if hasattr(e, 'response'):
                print(f"   응답: {e.response.text if hasattr(e.response, 'text') else e.response}")
            return None
    
    def sell_market_order(self, ticker: str, volume: float) -> Optional[str]:
        """시장가 매도 - UUID 반환"""
        if not self.private_client:
            return None
        
        try:
            self._rate_limit()
            
            print(f"   📤 시장가 매도 요청: {ticker} / {volume:.8f}개")
            
            result = self.private_client.sell_market_order(ticker, volume)
            
            if result and isinstance(result, dict):
                uuid = result.get('uuid')
                if uuid:
                    print(f"   ✅ 주문 접수: {uuid}")
                    return uuid
                else:
                    print(f"   ❌ UUID 없음: {result}")
            
            return None
            
        except Exception as e:
            print(f"❌ 시장가 매도 실패: {e}")
            if hasattr(e, 'response'):
                print(f"   응답: {e.response.text if hasattr(e.response, 'text') else e.response}")
            return None
    
    def buy_limit_order(self, ticker: str, price: float, volume: float) -> Optional[str]:
        """지정가 매수"""
        if not self.private_client:
            return None
        
        try:
            self._rate_limit()
            
            # 호가 단위 조정
            price = self._adjust_price_unit(price)
            
            print(f"   📤 지정가 매수 요청: {ticker} / {volume:.8f}개 @ {price:,.0f}원")
            
            result = self.private_client.buy_limit_order(ticker, price, volume)
            
            if result and isinstance(result, dict):
                uuid = result.get('uuid')
                if uuid:
                    print(f"   ✅ 주문 접수: {uuid}")
                    return uuid
            
            return None
            
        except Exception as e:
            print(f"❌ 지정가 매수 실패: {e}")
            return None
    
    def sell_limit_order(self, ticker: str, price: float, volume: float) -> Optional[str]:
        """지정가 매도"""
        if not self.private_client:
            return None
        
        try:
            self._rate_limit()
            
            # 호가 단위 조정
            price = self._adjust_price_unit(price)
            
            print(f"   📤 지정가 매도 요청: {ticker} / {volume:.8f}개 @ {price:,.0f}원")
            
            result = self.private_client.sell_limit_order(ticker, price, volume)
            
            if result and isinstance(result, dict):
                uuid = result.get('uuid')
                if uuid:
                    print(f"   ✅ 주문 접수: {uuid}")
                    return uuid
            
            return None
            
        except Exception as e:
            print(f"❌ 지정가 매도 실패: {e}")
            return None
    
    def cancel_order(self, uuid: str) -> bool:
        """주문 취소"""
        if not self.private_client:
            return False
        
        try:
            self._rate_limit()
            
            result = self.private_client.cancel_order(uuid)
            
            if result:
                print(f"   ✅ 주문 취소 성공: {uuid}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ 주문 취소 실패: {e}")
            return False
    
    # ==================== 주문 조회 ====================
    
    def get_order_status(self, uuid: str) -> Optional[Dict]:
        """주문 상태 조회 - 업비트 응답 그대로 반환"""
        if not self.private_client:
            return None
        
        try:
            self._rate_limit()
            
            order = self.private_client.get_order(uuid)
            
            if order:
                # 주요 필드 확인
                state = order.get('state', 'unknown')
                side = order.get('side', '')
                executed_volume = float(order.get('executed_volume', 0))
                
                # 디버깅용 출력 (필요시)
                if state in ['done', 'cancel']:
                    print(f"   📋 주문 상태: {state} ({side})")
                    if executed_volume > 0:
                        print(f"      체결량: {executed_volume:.8f}")
                
                return order
            
            return None
            
        except Exception as e:
            # 주문을 찾을 수 없는 경우는 에러 출력 안함
            if "주문을 찾을 수 없습니다" not in str(e):
                print(f"❌ 주문 조회 실패: {e}")
            return None
    
    def get_order_history(self, ticker: str = None, state: str = 'done', limit: int = 100) -> List[Dict]:
        """주문 내역 조회"""
        if not self.private_client:
            return []
        
        try:
            self._rate_limit()
            
            # pyupbit의 get_order 메서드 사용
            orders = []
            
            # 체결 완료 주문 조회
            if state == 'done':
                # market 파라미터로 특정 마켓만 조회 가능
                if ticker:
                    result = self.private_client.get_order(ticker, state='done')
                else:
                    # 전체 마켓 조회는 지원 안함
                    result = []
            else:
                result = []
            
            if result and isinstance(result, list):
                return result[:limit]
            
            return []
            
        except Exception as e:
            print(f"❌ 주문 내역 조회 실패: {e}")
            return []
    
    # ==================== 시세 관련 ====================
    
    def get_current_price(self, ticker: str) -> Optional[float]:
        """현재가 조회"""
        try:
            self._rate_limit()
            
            price = pyupbit.get_current_price(ticker)
            
            if price:
                return float(price)
            
            return None
            
        except Exception as e:
            print(f"❌ {ticker} 현재가 조회 실패: {e}")
            return None
    
    def get_orderbook(self, ticker: str) -> Optional[Dict]:
        """호가 정보 조회 - ✅ 수정됨: pyupbit은 dict를 직접 반환"""
        try:
            self._rate_limit()
            
            orderbook = pyupbit.get_orderbook(ticker)
            
            # ✅ 수정: dict를 직접 반환 (list가 아님!)
            if orderbook and isinstance(orderbook, dict):
                return orderbook
            
            return None
            
        except Exception as e:
            print(f"❌ {ticker} 호가 조회 실패: {e}")
            return None
    
    def get_market_data(self, ticker: str, intervals: List[str] = None) -> Dict:
        """시장 데이터 조회"""
        if intervals is None:
            intervals = ["minute5", "minute60", "minute240", "day"]
        
        market_data = {"ticker": ticker}
        
        for interval in intervals:
            self._rate_limit()
            try:
                df = pyupbit.get_ohlcv(ticker, interval=interval, count=200)
                if df is not None and not df.empty:
                    # DataFrame을 딕셔너리 리스트로 변환
                    market_data[interval] = df.to_dict('records')
                else:
                    market_data[interval] = []
            except Exception as e:
                print(f"❌ {ticker} {interval} 데이터 실패: {e}")
                market_data[interval] = []
        
        return market_data
    
    # ==================== 유틸리티 ====================
    
    def _adjust_price_unit(self, price: float) -> float:
        """업비트 호가 단위로 가격 조정"""
        if price >= 2000000:
            return float(int(price / 1000) * 1000)
        elif price >= 1000000:
            return float(int(price / 500) * 500)
        elif price >= 500000:
            return float(int(price / 100) * 100)
        elif price >= 100000:
            return float(int(price / 50) * 50)
        elif price >= 10000:
            return float(int(price / 10) * 10)
        elif price >= 1000:
            return float(int(price / 5) * 5)
        elif price >= 100:
            return float(int(price))
        elif price >= 10:
            return round(price, 1)
        elif price >= 1:
            return round(price, 2)
        else:
            return round(price, 4)
    
    def get_top_20_coins(self) -> List[str]:
        """거래량 상위 20개 코인 조회"""
        try:
            self._rate_limit()
            
            # KRW 마켓 전체 티커
            tickers = pyupbit.get_tickers(fiat="KRW")
            
            if not tickers:
                print("❌ KRW 마켓 조회 실패")
                return []

            # BTC 제외
            tickers = [t for t in tickers if t != "KRW-BTC"]
            
            volumes = {}
            
            # 거래대금 계산
            print("📊 거래량 상위 20개 코인 선정 중...")
            
            for i, ticker in enumerate(tickers, 1):
                if i % 20 == 0:
                    print(f"   처리 중... {i}/{len(tickers)}")
                
                self._rate_limit()
                
                try:
                    # 하루 거래대금
                    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
                    if df is not None and not df.empty:
                        volume_krw = df.iloc[-1]['volume'] * df.iloc[-1]['close']
                        volumes[ticker] = volume_krw
                except:
                    continue
            
            if not volumes:
                print("❌ 거래량 데이터 없음")
                return []

            # 거래대금 기준 정렬
            sorted_tickers = sorted(volumes.items(), key=lambda x: x[1], reverse=True)
            
            # 상위 20개 선택
            top_20 = [ticker for ticker, _ in sorted_tickers[:20]]
            
            print(f"\n✅ 거래량 상위 20개 코인:")
            for i, (ticker, volume) in enumerate(sorted_tickers[:20], 1):
                coin = ticker.replace("KRW-", "")
                volume_billion = volume / 1e9
                print(f"   {i:2d}. {coin:6s}: {volume_billion:6.1f}억원")
            
            return top_20
            
        except Exception as e:
            print(f"❌ 상위 20개 코인 조회 오류: {e}")
            return []
    
    def verify_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            # 공개 API 테스트
            btc_price = self.get_current_price("KRW-BTC")
            if not btc_price:
                print("❌ 공개 API 연결 실패")
                return False
            
            print(f"✅ 공개 API 연결 성공 (BTC: {btc_price:,.0f}원)")

            # 개인 API 테스트
            if self.private_client:
                krw_balance = self.get_balance("KRW")
                print(f"✅ 개인 API 연결 성공 (잔고: {krw_balance:,.0f}원)")
                
                # 보유 코인 확인
                balances = self.get_balances()
                coins = [b['currency'] for b in balances if b['currency'] != 'KRW' and float(b.get('balance', 0)) > 0]
                if coins:
                    print(f"   보유 코인: {', '.join(coins)}")
            else:
                print("⚠️ 개인 API 미설정")
            
            return True
            
        except Exception as e:
            print(f"❌ 연결 확인 실패: {e}")
            return False
    
    def get_transaction_history(self, ticker: str = None, days: int = 7) -> List[Dict]:
        """거래 체결 내역 조회 (완료된 거래)"""
        if not self.private_client:
            return []
        
        try:
            # pyupbit는 체결 내역 직접 조회 API가 없음
            # 대신 완료된 주문 내역에서 추출
            orders = self.get_order_history(ticker=ticker, state='done', limit=100)
            
            transactions = []
            for order in orders:
                if order.get('state') == 'done':
                    transactions.append({
                        'uuid': order.get('uuid'),
                        'side': order.get('side'),
                        'market': order.get('market'),
                        'price': float(order.get('price', 0)),
                        'volume': float(order.get('executed_volume', 0)),
                        'funds': float(order.get('executed_funds', 0)),
                        'fee': float(order.get('paid_fee', 0)),
                        'created_at': order.get('created_at'),
                        'trades_count': order.get('trades_count', 0)
                    })
            
            return transactions
            
        except Exception as e:
            print(f"❌ 체결 내역 조회 실패: {e}")
            return []