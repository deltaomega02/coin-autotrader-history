# validation.py - OMNI-XRP v8.0 리샘플링 검증 도구
# 5분봉 리샘플링 결과와 실제 시간대별 데이터 비교 검증

import os
import json
import time
import pandas as pd
import pandas_ta as ta
import pyupbit
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple
import numpy as np

# 환경 변수 로드
load_dotenv()

class ResamplingValidator:
    """리샘플링 검증 클래스"""
    
    def __init__(self):
        """검증기 초기화"""
        self.results = {}
        self.tolerance = 0.001  # 허용 오차 (0.1%)
        
    def fetch_actual_data(self, interval: str, count: int) -> Optional[pd.DataFrame]:
        """
        실제 시간대별 데이터 가져오기
        
        Args:
            interval (str): 시간 간격 ('minute60', 'minute240', 'day')
            count (int): 가져올 개수
            
        Returns:
            Optional[pd.DataFrame]: 실제 데이터 또는 None
        """
        try:
            print(f"📥 실제 {interval} 데이터 수집 중...")
            data = pyupbit.get_ohlcv("KRW-XRP", interval=interval, count=count)
            
            if data is None or len(data) == 0:
                print(f"❌ {interval} 데이터 수집 실패")
                return None
            
            print(f"✅ {interval} 데이터 수집 완료: {len(data)}개")
            return data
            
        except Exception as e:
            print(f"❌ {interval} 데이터 수집 중 오류: {e}")
            return None
    
    def fetch_5min_data_and_resample(self, count_5m: int) -> Dict[str, pd.DataFrame]:
        """
        5분봉 데이터를 가져와서 리샘플링
        
        Args:
            count_5m (int): 5분봉 데이터 개수
            
        Returns:
            Dict[str, pd.DataFrame]: 리샘플링된 데이터들
        """
        try:
            print(f"📥 5분봉 데이터 수집 중... ({count_5m}개)")
            df_5m = pyupbit.get_ohlcv("KRW-XRP", interval="minute5", count=count_5m)
            
            if df_5m is None or len(df_5m) == 0:
                print("❌ 5분봉 데이터 수집 실패")
                return {}
            
            print(f"✅ 5분봉 데이터 수집 완료: {len(df_5m)}개")
            
            # 인덱스가 datetime이 아닌 경우 변환
            if not isinstance(df_5m.index, pd.DatetimeIndex):
                df_5m.index = pd.to_datetime(df_5m.index)
            
            resampled = {'5m': df_5m}
            
            # 15분봉 리샘플링
            print("🔄 15분봉 리샘플링 중...")
            df_15m = df_5m.resample('15min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['15m'] = df_15m
            print(f"✅ 15분봉 리샘플링 완료: {len(df_15m)}개")
            
            # 1시간봉 리샘플링
            print("🔄 1시간봉 리샘플링 중...")
            df_1h = df_5m.resample('1h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['1h'] = df_1h
            print(f"✅ 1시간봉 리샘플링 완료: {len(df_1h)}개")
            
            # 4시간봉 리샘플링
            print("🔄 4시간봉 리샘플링 중...")
            df_4h = df_5m.resample('4h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['4h'] = df_4h
            print(f"✅ 4시간봉 리샘플링 완료: {len(df_4h)}개")
            
            # 일봉 리샘플링
            print("🔄 일봉 리샘플링 중...")
            df_day = df_5m.resample('1D').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            resampled['day'] = df_day
            print(f"✅ 일봉 리샘플링 완료: {len(df_day)}개")
            
            return resampled
            
        except Exception as e:
            print(f"❌ 5분봉 리샘플링 중 오류: {e}")
            return {}
    
    def compare_ohlcv_data(self, actual: pd.DataFrame, resampled: pd.DataFrame, 
                          timeframe: str) -> Dict:
        """
        OHLCV 데이터 비교
        
        Args:
            actual (pd.DataFrame): 실제 데이터
            resampled (pd.DataFrame): 리샘플링된 데이터
            timeframe (str): 시간프레임
            
        Returns:
            Dict: 비교 결과
        """
        try:
            print(f"🔍 {timeframe} OHLCV 데이터 비교 중...")
            
            result = {
                'timeframe': timeframe,
                'actual_count': len(actual),
                'resampled_count': len(resampled),
                'comparison_results': {},
                'max_differences': {},
                'overall_match': True
            }
            
            # 시간 인덱스 정렬 및 공통 시간대 추출
            actual_sorted = actual.sort_index()
            resampled_sorted = resampled.sort_index()
            
            # 공통 시간대 찾기 (최근 데이터 위주)
            common_times = actual_sorted.index.intersection(resampled_sorted.index)
            
            if len(common_times) == 0:
                result['error'] = '공통 시간대가 없음'
                result['overall_match'] = False
                return result
            
            # 최근 50개 시간대만 비교 (너무 많으면 시간 오래 걸림)
            common_times = common_times[-50:]
            
            actual_common = actual_sorted.loc[common_times]
            resampled_common = resampled_sorted.loc[common_times]
            
            result['compared_count'] = len(common_times)
            
            # 각 컬럼별 비교
            columns = ['open', 'high', 'low', 'close', 'volume']
            
            for col in columns:
                if col in actual_common.columns and col in resampled_common.columns:
                    # 절대 차이 계산
                    diff = np.abs(actual_common[col] - resampled_common[col])
                    
                    # 상대 차이 계산 (0으로 나누기 방지)
                    actual_values = actual_common[col]
                    rel_diff = np.where(actual_values != 0, diff / np.abs(actual_values), 0)
                    
                    max_abs_diff = diff.max()
                    max_rel_diff = rel_diff.max()
                    
                    # 허용 오차 내인지 확인
                    is_match = max_rel_diff < self.tolerance
                    
                    result['comparison_results'][col] = {
                        'max_absolute_diff': float(max_abs_diff),
                        'max_relative_diff': float(max_rel_diff),
                        'max_relative_diff_pct': float(max_rel_diff * 100),
                        'is_match': is_match,
                        'mismatched_count': int((rel_diff >= self.tolerance).sum())
                    }
                    
                    result['max_differences'][col] = float(max_rel_diff * 100)
                    
                    if not is_match:
                        result['overall_match'] = False
                        print(f"⚠️  {col}: 최대 차이 {max_rel_diff*100:.4f}%")
                    else:
                        print(f"✅ {col}: 일치 (최대 차이 {max_rel_diff*100:.6f}%)")
            
            return result
            
        except Exception as e:
            print(f"❌ {timeframe} OHLCV 비교 중 오류: {e}")
            return {'timeframe': timeframe, 'error': str(e), 'overall_match': False}
    
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """
        기술적 지표 계산
        
        Args:
            df (pd.DataFrame): 가격 데이터
            
        Returns:
            Dict: 계산된 지표들
        """
        try:
            indicators = {}
            
            # 데이터 타입 변환 및 정리
            df_clean = df.copy()
            for col in ['open', 'high', 'low', 'close']:
                if col in df_clean.columns:
                    df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').astype('float64')
            
            if 'volume' in df_clean.columns:
                df_clean['volume'] = pd.to_numeric(df_clean['volume'], errors='coerce').astype('float64')
                df_clean['volume'] = df_clean['volume'].fillna(0)
            
            # 무효한 값 제거
            df_clean = df_clean.dropna(subset=['open', 'high', 'low', 'close'])
            
            if len(df_clean) < 20:
                return {}
            
            # 이동평균선
            indicators['sma_20'] = ta.sma(df_clean['close'], length=20).iloc[-1]
            indicators['sma_60'] = ta.sma(df_clean['close'], length=60).iloc[-1] if len(df_clean) >= 60 else None
            indicators['ema_12'] = ta.ema(df_clean['close'], length=12).iloc[-1]
            indicators['ema_26'] = ta.ema(df_clean['close'], length=26).iloc[-1] if len(df_clean) >= 26 else None
            
            # RSI
            rsi = ta.rsi(df_clean['close'], length=14)
            indicators['rsi'] = rsi.iloc[-1] if rsi is not None and len(rsi) > 0 else None
            
            # MACD
            macd = ta.macd(df_clean['close'], fast=12, slow=26, signal=9)
            if macd is not None and len(macd) > 0:
                indicators['macd_line'] = macd['MACD_12_26_9'].iloc[-1]
                indicators['macd_signal'] = macd['MACDs_12_26_9'].iloc[-1]
                indicators['macd_histogram'] = macd['MACDh_12_26_9'].iloc[-1]
            
            # 볼린저 밴드
            bbands = ta.bbands(df_clean['close'], length=20, std=2)
            if bbands is not None and len(bbands) > 0:
                indicators['bb_upper'] = bbands['BBU_20_2.0'].iloc[-1]
                indicators['bb_middle'] = bbands['BBM_20_2.0'].iloc[-1]
                indicators['bb_lower'] = bbands['BBL_20_2.0'].iloc[-1]
            
            # ATR
            atr = ta.atr(df_clean['high'], df_clean['low'], df_clean['close'], length=14)
            indicators['atr'] = atr.iloc[-1] if atr is not None and len(atr) > 0 else None
            
            # 거래량 이동평균
            if 'volume' in df_clean.columns and df_clean['volume'].sum() > 0:
                volume_sma = ta.sma(df_clean['volume'], length=20)
                indicators['volume_sma_20'] = volume_sma.iloc[-1] if volume_sma is not None and len(volume_sma) > 0 else None
            
            return indicators
            
        except Exception as e:
            print(f"❌ 지표 계산 중 오류: {e}")
            return {}
    
    def compare_indicators(self, actual_df: pd.DataFrame, resampled_df: pd.DataFrame, 
                          timeframe: str) -> Dict:
        """
        기술적 지표 비교
        
        Args:
            actual_df (pd.DataFrame): 실제 데이터
            resampled_df (pd.DataFrame): 리샘플링된 데이터
            timeframe (str): 시간프레임
            
        Returns:
            Dict: 지표 비교 결과
        """
        try:
            print(f"📊 {timeframe} 기술적 지표 비교 중...")
            
            actual_indicators = self.calculate_indicators(actual_df)
            resampled_indicators = self.calculate_indicators(resampled_df)
            
            result = {
                'timeframe': timeframe,
                'indicator_comparisons': {},
                'overall_match': True
            }
            
            # 공통 지표들 비교
            common_indicators = set(actual_indicators.keys()) & set(resampled_indicators.keys())
            
            for indicator in common_indicators:
                actual_val = actual_indicators[indicator]
                resampled_val = resampled_indicators[indicator]
                
                if actual_val is None or resampled_val is None:
                    continue
                
                # pandas의 NaN 체크
                if pd.isna(actual_val) or pd.isna(resampled_val):
                    continue
                
                # 상대 차이 계산
                if actual_val != 0:
                    rel_diff = abs(actual_val - resampled_val) / abs(actual_val)
                else:
                    rel_diff = abs(resampled_val)
                
                is_match = rel_diff < self.tolerance
                
                result['indicator_comparisons'][indicator] = {
                    'actual_value': float(actual_val),
                    'resampled_value': float(resampled_val),
                    'relative_diff_pct': float(rel_diff * 100),
                    'is_match': is_match
                }
                
                if not is_match:
                    result['overall_match'] = False
                    print(f"⚠️  {indicator}: 차이 {rel_diff*100:.4f}% (실제: {actual_val:.4f}, 리샘플링: {resampled_val:.4f})")
                else:
                    print(f"✅ {indicator}: 일치 (차이 {rel_diff*100:.6f}%)")
            
            return result
            
        except Exception as e:
            print(f"❌ {timeframe} 지표 비교 중 오류: {e}")
            return {'timeframe': timeframe, 'error': str(e), 'overall_match': False}
    
    def run_validation(self) -> Dict:
        """
        전체 검증 실행
        
        Returns:
            Dict: 전체 검증 결과
        """
        print("="*80)
        print("🎯 OMNI-XRP v8.0 리샘플링 검증 시작")
        print("="*80)
        
        validation_results = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'tolerance_pct': self.tolerance * 100,
            'timeframe_results': {},
            'overall_success': True
        }
        
        try:
            # 1. 5분봉 데이터 수집 및 리샘플링 (4일치 = 1152개)
            count_5m = 1152  # 5분 * 12 * 24 * 4 = 4일
            resampled_data = self.fetch_5min_data_and_resample(count_5m)
            
            if not resampled_data:
                validation_results['error'] = '5분봉 데이터 수집 또는 리샘플링 실패'
                validation_results['overall_success'] = False
                return validation_results
            
            # 2. 각 시간프레임별 검증
            validation_configs = [
                ('1h', 'minute60', 96),    # 1시간봉 4일치
                ('4h', 'minute240', 24),   # 4시간봉 4일치
                ('day', 'day', 10)         # 일봉 10일치
            ]
            
            for timeframe, api_interval, count in validation_configs:
                print(f"\n{'='*60}")
                print(f"🔍 {timeframe.upper()} 시간프레임 검증")
                print(f"{'='*60}")
                
                # 실제 데이터 수집
                actual_data = self.fetch_actual_data(api_interval, count)
                
                if actual_data is None:
                    validation_results['timeframe_results'][timeframe] = {
                        'error': '실제 데이터 수집 실패',
                        'success': False
                    }
                    validation_results['overall_success'] = False
                    continue
                
                resampled_df = resampled_data.get(timeframe)
                if resampled_df is None or len(resampled_df) == 0:
                    validation_results['timeframe_results'][timeframe] = {
                        'error': '리샘플링된 데이터 없음',
                        'success': False
                    }
                    validation_results['overall_success'] = False
                    continue
                
                # OHLCV 데이터 비교
                ohlcv_result = self.compare_ohlcv_data(actual_data, resampled_df, timeframe)
                
                # 기술적 지표 비교
                indicators_result = self.compare_indicators(actual_data, resampled_df, timeframe)
                
                # 결과 통합
                timeframe_result = {
                    'ohlcv_comparison': ohlcv_result,
                    'indicators_comparison': indicators_result,
                    'success': ohlcv_result['overall_match'] and indicators_result['overall_match']
                }
                
                validation_results['timeframe_results'][timeframe] = timeframe_result
                
                if not timeframe_result['success']:
                    validation_results['overall_success'] = False
                
                # 요약 출력
                ohlcv_status = "✅ 통과" if ohlcv_result['overall_match'] else "❌ 실패"
                indicators_status = "✅ 통과" if indicators_result['overall_match'] else "❌ 실패"
                
                print(f"\n📊 {timeframe.upper()} 검증 결과:")
                print(f"   OHLCV 데이터: {ohlcv_status}")
                print(f"   기술적 지표: {indicators_status}")
                
                # 대기 (API 제한 고려)
                time.sleep(1)
            
            # 3. 최종 결과 출력
            self._print_final_results(validation_results)
            
            return validation_results
            
        except Exception as e:
            print(f"❌ 검증 실행 중 치명적 오류: {e}")
            validation_results['error'] = str(e)
            validation_results['overall_success'] = False
            return validation_results
    
    def _print_final_results(self, results: Dict) -> None:
        """
        최종 검증 결과 출력
        
        Args:
            results (Dict): 검증 결과
        """
        print("\n" + "="*80)
        print("📈 OMNI-XRP v8.0 리샘플링 검증 최종 결과")
        print("="*80)
        
        overall_status = "🎉 성공" if results['overall_success'] else "❌ 실패"
        print(f"전체 결과: {overall_status}")
        print(f"허용 오차: {results['tolerance_pct']}%")
        print(f"검증 시간: {results['timestamp']}")
        
        if 'timeframe_results' in results:
            print(f"\n📊 시간프레임별 상세 결과:")
            
            for timeframe, result in results['timeframe_results'].items():
                if 'error' in result:
                    print(f"   {timeframe.upper()}: ❌ {result['error']}")
                    continue
                
                success_status = "✅ 성공" if result['success'] else "❌ 실패"
                print(f"   {timeframe.upper()}: {success_status}")
                
                # OHLCV 상세 정보
                ohlcv = result.get('ohlcv_comparison', {})
                if 'max_differences' in ohlcv:
                    max_diff = max(ohlcv['max_differences'].values()) if ohlcv['max_differences'] else 0
                    print(f"      OHLCV 최대 차이: {max_diff:.6f}%")
                
                # 지표 상세 정보
                indicators = result.get('indicators_comparison', {})
                if 'indicator_comparisons' in indicators:
                    indicator_count = len(indicators['indicator_comparisons'])
                    matched_count = sum(1 for comp in indicators['indicator_comparisons'].values() if comp.get('is_match', False))
                    print(f"      지표 일치율: {matched_count}/{indicator_count}")
        
        print("\n💡 검증 해석:")
        if results['overall_success']:
            print("   🎉 모든 시간프레임에서 리샘플링이 정확하게 작동합니다!")
            print("   ✅ OMNI-XRP v8.0의 API 최적화 리샘플링 기능을 안전하게 사용할 수 있습니다.")
        else:
            print("   ⚠️  일부 시간프레임에서 차이가 발견되었습니다.")
            print("   🔧 리샘플링 로직을 점검하거나 허용 오차를 조정해야 할 수 있습니다.")
        
        print("="*80)
    
    def save_results_to_file(self, results: Dict, filename: str = None) -> str:
        """
        검증 결과를 파일로 저장
        
        Args:
            results (Dict): 검증 결과
            filename (str): 파일명 (None이면 자동 생성)
            
        Returns:
            str: 저장된 파일 경로
        """
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"validation_results_{timestamp}.json"
            
            # numpy 타입을 Python 기본 타입으로 변환
            def convert_numpy_types(obj):
                if isinstance(obj, dict):
                    return {key: convert_numpy_types(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
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
            
            results_clean = convert_numpy_types(results)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results_clean, f, indent=2, ensure_ascii=False)
            
            print(f"📄 검증 결과 저장: {filename}")
            return filename
            
        except Exception as e:
            print(f"❌ 결과 저장 실패: {e}")
            return ""

def main():
    """메인 실행 함수"""
    try:
        print("🚀 OMNI-XRP v8.0 리샘플링 검증기")
        print("5분봉 → 1시간/4시간/일봉 리샘플링 정확도 검증")
        print("실제 업비트 데이터와 비교하여 차이점 분석\n")
        
        # 검증 실행
        validator = ResamplingValidator()
        results = validator.run_validation()
        
        # 결과 파일 저장
        if results:
            saved_file = validator.save_results_to_file(results)
            if saved_file:
                print(f"\n📄 상세 결과는 {saved_file}에서 확인할 수 있습니다.")
        
        # 최종 상태 반환
        if results.get('overall_success', False):
            print("\n🎉 검증 완료: 리샘플링이 정확하게 작동합니다!")
            return 0
        else:
            print("\n⚠️  검증 완료: 일부 문제가 발견되었습니다.")
            return 1
            
    except KeyboardInterrupt:
        print("\n🛑 사용자 중단")
        return 1
    except Exception as e:
        print(f"\n❌ 검증 중 오류: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)