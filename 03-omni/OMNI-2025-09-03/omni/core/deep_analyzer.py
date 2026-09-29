# core/deep_analyzer.py 
# "Phase 2: 선정된 TOP 3 코인에 대한 심층 분석을 수행하여 최종 1개 코인을 선정하는 파일"

from typing import Dict, Any, List, Optional
from datetime import datetime
from data.upbit_client import UpbitClient
from data.indicators import TechnicalIndicators
from ai.gpt_client import get_gpt_client
from core.reflector import Reflector
import pandas as pd
import numpy as np
import json

class DeepAnalyzer:

    # "DeepAnalyzer 클래스를 초기화하고 필요한 클라이언트들을 생성하는 메서드" (인자: self)
    def __init__(self):
        self.upbit = UpbitClient()
        self.indicators = TechnicalIndicators()
        self.gpt = get_gpt_client()
        self.reflector = Reflector()
    
    # "TOP 3 후보 코인을 GPT-5 단일 추론으로 심층 분석하는 메서드" (인자: self, top_3_tickers)
    def analyze_candidates(self, top_3_tickers: List[str]) -> Dict[str, Any]:
        print(f"🔍 Phase 2: GPT-5 심층 분석 - {top_3_tickers}")

        memory = self.reflector.get_recent_memory(limit=5)
        has_memory = bool(memory.get('long_term', '').strip() or memory.get('short_term', '').strip())
        
        if has_memory:
            print("🧠 과거 알트코인 거래 경험을 참고합니다")
        else:
            print("순수 데이터 기반 심층 분석 모드")

        candidates_raw_data = {}
        
        for ticker in top_3_tickers:
            print(f"   📊 {ticker} 상세 데이터 수집 중...")
            raw_data = self._get_detailed_raw_data(ticker)
            
            if raw_data:
                candidates_raw_data[ticker] = raw_data
                print(f"   ✅ {ticker} 데이터 수집 완료")
            else:
                print(f"   ❌ {ticker} 데이터 수집 실패")
        
        if len(candidates_raw_data) < 2:
            return {
                "error": f"분석 가능한 후보가 {len(candidates_raw_data)}개뿐 (최소 2개 필요)",
                "available_candidates": list(candidates_raw_data.keys())
            }

        print("🤖 GPT-5 통합 다중 관점 분석 시작...")
        
        final_decision = self.gpt.analyze_deep_phase2_unified(
            candidates_raw_data,
            memory if has_memory else None
        )
        
        if not final_decision or final_decision.get('error'):
            return {"error": f"GPT-5 분석 실패: {final_decision.get('error', '알 수 없는 오류')}"}

        self._display_analysis_result(final_decision, has_memory)
        
        return final_decision
    
    # "개별 코인의 상세 원시 데이터를 수집하는 메서드" (인자: self, ticker)
    def _get_detailed_raw_data(self, ticker: str) -> Optional[Dict[str, Any]]:

        try:
            market_data = self.upbit.get_market_data(
                ticker, 
                ["minute5", "minute15", "minute60", "minute240", "day"]
            )

            current_price = self.upbit.get_current_price(ticker)
            if not current_price:
                return None

            raw_data = {
                "ticker": ticker,
                "current_price": float(current_price),
                "timestamp": datetime.now().isoformat()
            }

            for interval, data in market_data.items():
                if interval == "ticker" or not data:
                    continue
                
                df = pd.DataFrame(data)
                if df.empty:
                    continue
                
                # 순수 기술 지표
                indicators = self.indicators.calculate_indicators(df)
                
                # 최근 캔들 데이터
                recent_candles = data[-20:] if len(data) >= 20 else data
                
                # 캔들 패턴 감지
                candle_patterns = self._detect_candle_patterns(df)
                
                # 거래량 프로파일
                volume_profile = self._calculate_volume_profile(df)
                
                raw_data[f"{interval}_analysis"] = {
                    "candles": recent_candles,
                    "indicators": indicators,
                    "patterns": candle_patterns,
                    "volume_profile": volume_profile
                }
            
            # 호가창 데이터
            try:
                orderbook = self._get_orderbook_data(ticker)
                if orderbook:
                    raw_data["orderbook"] = orderbook
            except:
                pass
            
            # 최근 체결 데이터
            try:
                recent_trades = self._get_recent_trades(ticker)
                if recent_trades:
                    raw_data["recent_trades"] = recent_trades
            except:
                pass

            return self._convert_numpy_types(raw_data)
            
        except Exception as e:
            print(f"Error getting raw data for {ticker}: {e}")
            return None
    
    # "캔들스틱 패턴을 감지하여 패턴 정보를 반환하는 메서드" (인자: self, df)
    def _detect_candle_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:

        patterns = []
        
        if len(df) < 3:
            return patterns
        
        try:
            # 최근 5개 캔들로 패턴 감지
            recent = df.tail(5)
            
            for i in range(len(recent) - 1, -1, -1):
                candle = recent.iloc[i]
                pattern_info = {
                    "index": i - len(recent),  # -5, -4, -3, -2, -1
                    "patterns": []
                }
                
                open_price = candle['open']
                close = candle['close']
                high = candle['high']
                low = candle['low']
                
                body = abs(close - open_price)
                full_range = high - low
                
                if full_range == 0:
                    continue
                
                # Doji
                if body / full_range < 0.1:
                    pattern_info["patterns"].append("doji")
                
                # Hammer / Hanging Man
                upper_shadow = high - max(open_price, close)
                lower_shadow = min(open_price, close) - low
                
                if lower_shadow > body * 2 and upper_shadow < body * 0.5:
                    if close > open_price:
                        pattern_info["patterns"].append("hammer")
                    else:
                        pattern_info["patterns"].append("hanging_man")
                
                # Shooting Star / Inverted Hammer
                if upper_shadow > body * 2 and lower_shadow < body * 0.5:
                    if close < open_price:
                        pattern_info["patterns"].append("shooting_star")
                    else:
                        pattern_info["patterns"].append("inverted_hammer")
                
                # Engulfing patterns (2개 캔들 필요)
                if i > 0:
                    prev_candle = recent.iloc[i-1]
                    prev_body = abs(prev_candle['close'] - prev_candle['open'])
                    
                    # Bullish Engulfing
                    if (prev_candle['close'] < prev_candle['open'] and 
                        close > open_price and
                        open_price <= prev_candle['close'] and 
                        close >= prev_candle['open']):
                        pattern_info["patterns"].append("bullish_engulfing")
                    
                    # Bearish Engulfing
                    if (prev_candle['close'] > prev_candle['open'] and 
                        close < open_price and
                        open_price >= prev_candle['close'] and 
                        close <= prev_candle['open']):
                        pattern_info["patterns"].append("bearish_engulfing")
                
                if pattern_info["patterns"]:
                    patterns.append(pattern_info)
            
        except Exception as e:
            print(f"Pattern detection error: {e}")
        
        return patterns
    
    # "거래량 프로파일을 계산하여 원시 데이터로 반환하는 메서드" (인자: self, df)
    def _calculate_volume_profile(self, df: pd.DataFrame) -> Dict[str, Any]:

        profile = {}
        
        try:
            if len(df) < 5:
                return profile
            
            volumes = df['volume'].values
            prices = df['close'].values
            
            # 최근 거래량 vs 평균
            recent_vol = volumes[-3:].mean() if len(volumes) >= 3 else volumes[-1]
            avg_vol = volumes.mean()
            
            profile["recent_volume"] = float(recent_vol)
            profile["average_volume"] = float(avg_vol)
            profile["volume_ratio"] = float(recent_vol / avg_vol) if avg_vol > 0 else 1.0
            
            # 가격별 거래량 분포
            if len(df) >= 20:
                price_levels = np.percentile(prices, [20, 40, 60, 80])
                volume_distribution = []
                
                for i in range(len(price_levels) + 1):
                    if i == 0:
                        mask = prices <= price_levels[0]
                    elif i == len(price_levels):
                        mask = prices > price_levels[-1]
                    else:
                        mask = (prices > price_levels[i-1]) & (prices <= price_levels[i])
                    
                    level_volume = volumes[mask].sum() if mask.any() else 0
                    volume_distribution.append({
                        "level": i,
                        "volume": float(level_volume),
                        "percentage": float(level_volume / volumes.sum() * 100) if volumes.sum() > 0 else 0
                    })
                
                profile["distribution"] = volume_distribution
            
            # 거래량 추세
            if len(volumes) >= 10:
                recent_trend = volumes[-5:].mean()
                older_trend = volumes[-10:-5].mean()
                
                if older_trend > 0:
                    trend_ratio = (recent_trend - older_trend) / older_trend
                    profile["volume_trend"] = "increasing" if trend_ratio > 0.1 else "decreasing" if trend_ratio < -0.1 else "stable"
                    profile["trend_strength"] = float(abs(trend_ratio))
            
        except Exception as e:
            print(f"Volume profile error: {e}")
        
        return profile
    
    # "호가창 데이터를 수집하는 선택적 메서드" (인자: self, ticker)
    def _get_orderbook_data(self, ticker: str) -> Optional[Dict[str, Any]]:

        try:

            if hasattr(self.upbit, 'get_orderbook'):
                orderbook = self.upbit.get_orderbook(ticker)
                
                if orderbook:
                    return {
                        "bid_ask_spread": float(orderbook.get('ask_price', 0) - orderbook.get('bid_price', 0)),
                        "bid_volume": float(orderbook.get('total_bid_volume', 0)),
                        "ask_volume": float(orderbook.get('total_ask_volume', 0)),
                        "bid_ask_ratio": float(orderbook.get('bid_volume', 0) / max(orderbook.get('ask_volume', 1), 1)),
                        "timestamp": orderbook.get('timestamp', datetime.now().isoformat())
                    }
        except:
            pass
        
        return None
    
    # "최근 체결 데이터를 수집하는 선택적 메서드" (인자: self, ticker, limit)
    def _get_recent_trades(self, ticker: str, limit: int = 20) -> Optional[List[Dict]]:

        try:
            if hasattr(self.upbit, 'get_recent_trades'):
                trades = self.upbit.get_recent_trades(ticker, limit)
                
                if trades:
                    buy_volume = sum(t['volume'] for t in trades if t.get('ask_bid') == 'BID')
                    sell_volume = sum(t['volume'] for t in trades if t.get('ask_bid') == 'ASK')
                    
                    return {
                        "trade_count": len(trades),
                        "buy_volume": float(buy_volume),
                        "sell_volume": float(sell_volume),
                        "buy_sell_ratio": float(buy_volume / max(sell_volume, 1)),
                        "avg_trade_size": float(sum(t['volume'] for t in trades) / len(trades))
                    }
        except:
            pass
        
        return None
    
    # "numpy 타입을 Python 기본 타입으로 재귀적으로 변환하는 메서드" (인자: self, obj)
    def _convert_numpy_types(self, obj):
        if isinstance(obj, dict):
            return {key: self._convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif pd.isna(obj):
            return None
        else:
            return obj
    
    # "GPT-5 분석 결과를 포맷팅하여 출력하는 메서드" (인자: self, result, has_memory)
    def _display_analysis_result(self, result: Dict[str, Any], has_memory: bool):

        action = result.get('action', 'wait')
        final_selection = result.get('final_selection', {})
        
        selected_coin = final_selection.get('selected_coin', '')
        confidence = final_selection.get('confidence_score', 0)
        reasoning = final_selection.get('selection_rationale', '')
        
        print(f"\n🎯 GPT-5 통합 분석 결과:")
        print(f"   💰 선정 코인: {selected_coin if selected_coin else 'None'}")
        print(f"   📊 신뢰도: {confidence:.0f}/100")
        print(f"   🎬 결정: {action.upper()}")
        
        if action == 'wait':
            wait_reason = final_selection.get('wait_reason', '더 좋은 기회 대기')
            print(f"   ⏸️  대기 사유: {wait_reason}")
            print(f"   🔄 30분 후 Phase 1부터 재시작 권장")
        else:
            # 주요 분석 포인트
            perspectives = result.get('multi_perspective_analysis', {})
            if perspectives:
                print(f"\n📊 다중 관점 분석 요약:")
                
                # 각 관점별 점수
                for perspective, analysis in perspectives.items():
                    if isinstance(analysis, dict):
                        score = analysis.get('score', 0)
                        insight = analysis.get('key_insight', '')
                        print(f"   • {perspective}: {score}/100")
                        if insight:
                            print(f"     → {insight[:80]}...")
            
            # 선정 근거
            if reasoning:
                print(f"\n💡 선정 근거:")
                print(f"   {reasoning[:200]}...")
            
            # 메모리 활용 여부
            if has_memory:
                memory_influence = final_selection.get('memory_influence', '')
                if memory_influence:
                    print(f"\n🧠 경험 활용:")
                    print(f"   {memory_influence[:150]}...")
        
        # 리스크 정보
        risk_factors = final_selection.get('risk_factors', [])
        if risk_factors:
            print(f"\n⚠️  주요 리스크:")
            for risk in risk_factors[:3]:
                print(f"   • {risk}")
        
        print(f"\n" + "="*70)