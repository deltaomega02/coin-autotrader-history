# core/market_analyzer.py
# "Phase 1: Gemini 2.5 Pro로 20개 코인 RAW 데이터 분석 - AI 자율 판단"

import pandas as pd
import json
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, List
from datetime import datetime  
from data.upbit_client import UpbitClient
from data.indicators import TechnicalIndicators
from config.settings import settings  
from ai.gpt_client import get_gpt_client

class MarketAnalyzer:
    
    def __init__(self):
        self.upbit = UpbitClient()
        self.indicators = TechnicalIndicators()
        self.gpt = get_gpt_client()
    
    def analyze_market_condition(self) -> Dict[str, Any]:
        print("📊 Phase 1: Gemini 2.5 Pro 자율 분석 시작...")
        
        # 1. BTC 데이터 수집
        btc_data = self._get_btc_raw_data()
        if not btc_data:
            return {
                "action": "wait",
                "reason": "BTC 데이터 수집 실패",
                "wait_minutes": 30
            }
        
        # 2. 상위 20개 코인 병렬 데이터 수집
        print("   ⚡ 20개 코인 병렬 데이터 수집 시작...")
        altcoin_data = self._get_top_20_altcoins_parallel()
        
        if not altcoin_data:
            return {
                "action": "wait",
                "reason": "알트코인 데이터 수집 실패",
                "wait_minutes": 30
            }
        
        # 3. 시장 데이터 구성
        market_data = {
            "btc_data": btc_data,
            "altcoin_count": len(altcoin_data),
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"   📈 BTC: {btc_data.get('current_price', 0):,.0f}원")
        print(f"   🎯 수집 완료: {len(altcoin_data)}개 코인")
        
        # 4. Gemini 2.5 Pro에게 순수 데이터로 자율 분석 요청
        print("\n🤖 Gemini 2.5 Pro 자율 판단 (점수 기준 없음)...")
        result = self.gpt.analyze_market_phase1(
            market_data, 
            altcoin_data,
            None
        )
        
        if result.get('error'):
            print(f"❌ Gemini 분석 실패: {result['error']}")
            return {
                "action": "wait",
                "reason": f"AI 분석 실패: {result['error']}",
                "wait_minutes": 60
            }
        
        # 5. 결과 해석 및 출력
        self._display_analysis_result(result)
        
        return result

    def _get_top_20_altcoins_parallel(self) -> Dict[str, Any]:
        try:
            start_time = datetime.now()
            
            # 상위 20개 코인 티커 가져오기 (거래량 기준)
            top_coins = self.upbit.get_top_20_coins()
            
            if not top_coins:
                print("❌ 상위 코인 조회 실패")
                return {}
            
            # BTC 제외
            top_coins = [t for t in top_coins if t != "KRW-BTC"][:20]
            
            print(f"   📋 대상 코인: {len(top_coins)}개")
            
            # 병렬 처리를 위한 ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ticker = {
                    executor.submit(self._collect_single_coin_data, ticker): ticker 
                    for ticker in top_coins
                }
                
                altcoin_data = {}
                completed = 0
                
                for future in concurrent.futures.as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    completed += 1
                    
                    try:
                        coin_data = future.result(timeout=10)
                        if coin_data:
                            altcoin_data[ticker] = coin_data
                            
                            if completed % 5 == 0:
                                print(f"      ⚡ 수집 진행: {completed}/{len(top_coins)}")
                                
                    except Exception as e:
                        print(f"      ⚠️ {ticker} 수집 실패: {e}")
                        continue
            
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"   ✅ 병렬 수집 완료: {len(altcoin_data)}개 ({elapsed:.1f}초)")
            
            # 거래량 기준으로 정렬 (signal_score 제거)
            sorted_coins = sorted(
                altcoin_data.items(),
                key=lambda x: x[1].get('volume_24h_krw', 0),
                reverse=True
            )
            
            # 상위 거래량 코인 출력
            print("\n   📊 거래량 상위 5개:")
            for ticker, data in sorted_coins[:5]:
                volume = data.get('volume_24h_krw', 0) / 1e9  # 억원 단위
                print(f"      {ticker.replace('KRW-', '')}: {volume:.1f}억원")
            
            return dict(sorted_coins)
            
        except Exception as e:
            print(f"❌ 병렬 데이터 수집 오류: {e}")
            return {}
    
    def _collect_single_coin_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """단일 코인의 순수 데이터 수집 (점수 계산 없음)"""
        try:
            current_price = self.upbit.get_current_price(ticker)
            if not current_price:
                return None
            
            # 다중 타임프레임 데이터 수집
            market_data = self.upbit.get_market_data(
                ticker, 
                ["minute5", "minute15", "minute60", "minute240"]
            )
            
            coin_data = {
                "ticker": ticker,
                "current_price": current_price,
                "timestamp": datetime.now().isoformat()
            }
            
            # 각 타임프레임별 순수 지표 데이터
            for interval, data in market_data.items():
                if interval == "ticker" or not data:
                    continue
                    
                try:
                    df = pd.DataFrame(data)
                    if df.empty:
                        continue
                    
                    # 순수 지표 계산 (점수 없음)
                    indicators = self.indicators.calculate_all_indicators(df)
                    
                    # 24시간 거래량 계산
                    if interval == "minute60" and len(df) >= 24:
                        volume_24h = df['volume'].tail(24).sum() * current_price
                        coin_data['volume_24h_krw'] = volume_24h
                        
                        # 24시간 변화율
                        change_24h = ((df.iloc[-1]['close'] - df.iloc[-24]['close']) / df.iloc[-24]['close'] * 100)
                        coin_data['change_24h'] = change_24h
                    
                    coin_data[f"{interval}_data"] = {
                        "ohlcv": data[-10:],
                        "indicators": indicators,  # 순수 지표만
                        "divergences": indicators.get('divergences', {}),
                        "volume_ratio": indicators.get('volume_ratio', 1.0),
                        "price_momentum": indicators.get('price_momentum', {})
                    }
                except Exception as e:
                    continue
            
            return coin_data
                    
        except Exception as e:
            return None

    def _get_btc_raw_data(self) -> Dict[str, Any]:
        """BTC 순수 데이터 수집"""
        try:
            print("   🔍 BTC 데이터 수집...")
            
            btc_ticker = "KRW-BTC"
            current_price = self.upbit.get_current_price(btc_ticker)
            
            market_data = self.upbit.get_market_data(
                btc_ticker, 
                ["minute15", "minute60", "minute240", "day"]
            )
            
            btc_data = {
                "ticker": btc_ticker,
                "current_price": current_price,
                "timestamp": datetime.now().isoformat()
            }
            
            for interval, data in market_data.items():
                if interval == "ticker" or not data:
                    continue
                    
                try:
                    df = pd.DataFrame(data)
                    # 순수 지표 계산
                    indicators = self.indicators.calculate_all_indicators(df)
                    
                    btc_data[f"{interval}_data"] = {
                        "ohlcv": data[-20:],
                        "indicators": indicators,  # 순수 지표만
                        "divergences": indicators.get('divergences', {})
                    }
                except Exception as e:
                    print(f"   ⚠️ {interval} 지표 계산 오류: {e}")
                    continue
            
            return btc_data
            
        except Exception as e:
            print(f"❌ BTC 데이터 수집 오류: {e}")
            return {}

    def _display_analysis_result(self, result: Dict[str, Any]):
            """Gemini 자율 판단 결과 출력"""
            action = result.get('action', 'wait')
            
            if action == 'proceed':
                selected = result.get('selected_coin', '')
                # final_decision 딕셔너리에서 confidence_level과 reasoning 추출
                final_decision = result.get('final_decision', {})
                confidence = final_decision.get('confidence_level', 0)
                reasoning = final_decision.get('reasoning', '')
                
                print(f"\n✅ 거래 진행 결정 (Gemini 자율 판단)")
                print(f"   🎯 선정 코인: {selected}")
                print(f"   🔮 신뢰도: {confidence}%")
                print(f"   💡 판단 근거: {reasoning[:100]}...") # reasoning을 출력하도록 수정
                
                # 세부 분석 내용 (analysis 키 확인)
                analysis = result.get('analysis') # .get()으로 안전하게 접근
                if analysis and isinstance(analysis, dict):
                    key_indicators = analysis.get('key_indicators')
                    
                    if key_indicators:
                        print(f"\n   📊 핵심 지표:")
                        # key_indicators가 딕셔너리인지 문자열인지 확인 후 처리
                        if isinstance(key_indicators, dict):
                            for indicator, value in list(key_indicators.items())[:5]:
                                print(f"       • {indicator}: {value}")
                        elif isinstance(key_indicators, str):
                            print(f"       • {key_indicators}")

            else: # action == 'wait'
                final_decision = result.get('final_decision', {})
                wait_minutes = final_decision.get('wait_minutes', 30)
                reason = final_decision.get('wait_reason', '적합한 기회 없음')
                
                print(f"\n⏸️ 거래 대기 ({wait_minutes}분)")
                print(f"   📝 사유: {reason}")
                
                # 시장 상황
                market_assessment = result.get('market_assessment', {})
                market_overview = market_assessment.get('market_overview')
                if market_overview:
                    print(f"   📈 시장: {market_overview}")
                
                print(f"   💡 Gemini가 더 나은 기회 탐색 중...")

    def get_market_regime(self) -> str:
        """시장 추세 판단 (순수 데이터 기반)"""
        try:
            btc_data = self._get_btc_raw_data()
            if not btc_data:
                return "UNKNOWN"
            
            h1_data = btc_data.get('minute60_data', {})
            indicators = h1_data.get('indicators', {})
            
            # 순수 지표 값들
            adx = indicators.get('adx', 0)
            price = btc_data.get('current_price', 0)
            sma_50 = indicators.get('sma_50', price)
            sma_200 = indicators.get('sma_200', price)
            rsi = indicators.get('rsi_14', 50)
            
            # 한국 시간대
            current_hour = datetime.now().hour
            is_korean_peak = (9 <= current_hour <= 11) or (20 <= current_hour <= 23)
            
            # 단순 추세 분류 (점수 없음)
            if adx > 25:
                if price > sma_50 > sma_200 and rsi > 55:
                    regime = "BULL_TREND"
                elif price < sma_50 < sma_200 and rsi < 45:
                    regime = "BEAR_TREND"
                else:
                    regime = "SIDEWAYS"
            else:
                regime = "SIDEWAYS"
            
            if is_korean_peak and regime == "SIDEWAYS":
                regime = "KOREAN_ACTIVE"
            
            print(f"📊 시장 상태: {regime} (ADX: {adx:.1f}, RSI: {rsi:.1f})")
            
            return regime
            
        except Exception as e:
            print(f"❌ 시장 추세 판단 오류: {e}")
            return "UNKNOWN"