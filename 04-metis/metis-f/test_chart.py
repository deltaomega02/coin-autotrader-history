# test_chart.py
# 차트 생성 테스트 - 실제 운영과 동일한 방식으로 차트 생성

import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from config import setup_logging, get_logger
from core.data_fetcher import data_fetcher
from core.chart_generator import generate_candlestick_chart

setup_logging()
logger = get_logger("test_chart")


def main():
    """차트 생성 테스트 - 운영 환경과 동일한 방식"""
    print("=" * 50)
    print("METIS-F 차트 생성 테스트")
    print("=" * 50)
    
    # 1. 데이터 수집 (운영과 동일한 메서드 사용)
    print("\n[1] data_fetcher.collect_all_data() 호출 중...")
    
    try:
        data = data_fetcher.collect_all_data()
        
        df = data["dataframe"]
        indicators = data["indicators"]
        futures = data["futures"]
        trend = data["trend_analysis"]
        
        print(f"    타임프레임: {data['timeframe']}")
        print(f"    캔들 수: {data['candle_count']}")
        print(f"    기간: {df.index[0]} ~ {df.index[-1]}")
        
    except Exception as e:
        print(f"ERROR: 데이터 수집 실패 - {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 2. 수집된 데이터 확인
    print("\n[2] 수집된 데이터 확인...")
    print(f"    현재가: {futures['last_price']:,.2f} USDT")
    print(f"    RSI: {indicators['rsi']:.1f}")
    print(f"    EMA 20: {indicators['ema']['ema_20']:,.2f}")
    print(f"    EMA 50: {indicators['ema']['ema_50']:,.2f}")
    print(f"    MACD: {indicators['macd']['macd']:.2f}")
    print(f"    추세: {trend['trend']} (강도: {trend['strength']})")
    print(f"    펀딩비: {futures['funding_rate_pct']:.4f}%")
    
    # 3. 차트 생성 (운영과 동일한 메서드 사용)
    print("\n[3] generate_candlestick_chart() 호출 중...")
    
    try:
        chart_bytes = generate_candlestick_chart(df)
        print(f"    생성된 이미지 크기: {len(chart_bytes):,} bytes")
        
    except Exception as e:
        print(f"ERROR: 차트 생성 실패 - {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. 파일 저장
    print("\n[4] 파일 저장 중...")
    
    output_dir = Path(__file__).parent / "logs"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_chart_{timestamp}.png"
    filepath = output_dir / filename
    
    with open(filepath, "wb") as f:
        f.write(chart_bytes)
    
    # 5. 결과 출력
    print("\n" + "=" * 50)
    print("차트 생성 완료!")
    print("=" * 50)
    print(f"\n저장 경로: {filepath.absolute()}")
    print(f"파일 크기: {len(chart_bytes):,} bytes")


if __name__ == "__main__":
    main()