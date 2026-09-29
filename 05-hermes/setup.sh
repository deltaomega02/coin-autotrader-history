#!/bin/bash
# HERMES 설치 스크립트
# 사용법: 파일 전부 홈 디렉터리에 업로드 후 실행
# chmod +x setup.sh && ./setup.sh

set -e

echo "=== HERMES 설치 시작 ==="

# 디렉터리 생성
echo "[1/5] 디렉터리 생성..."
mkdir -p ~/hermes-trading/{config,core,exchange,database,ai,backtest,utils,logs}

# 파일 이동
echo "[2/5] 파일 이동..."

mv ~/main.py ~/hermes-trading/
mv ~/requirements.txt ~/hermes-trading/
mv ~/README.md ~/hermes-trading/ 2>/dev/null || true

mv ~/config__init__.py ~/hermes-trading/config/__init__.py
mv ~/settings.py ~/hermes-trading/config/settings.py
mv ~/parameters.py ~/hermes-trading/config/parameters.py
mv ~/logging_config.py ~/hermes-trading/config/logging_config.py

mv ~/core__init__.py ~/hermes-trading/core/__init__.py
mv ~/signal_engine.py ~/hermes-trading/core/signal_engine.py
mv ~/regime_engine.py ~/hermes-trading/core/regime_engine.py
mv ~/risk_manager.py ~/hermes-trading/core/risk_manager.py
mv ~/position_manager.py ~/hermes-trading/core/position_manager.py
mv ~/websocket_watcher.py ~/hermes-trading/core/websocket_watcher.py
mv ~/technical_analysis.py ~/hermes-trading/core/technical_analysis.py

mv ~/exchange__init__.py ~/hermes-trading/exchange/__init__.py
mv ~/bybit_client.py ~/hermes-trading/exchange/bybit_client.py
mv ~/bybit_websocket.py ~/hermes-trading/exchange/bybit_websocket.py

mv ~/database__init__.py ~/hermes-trading/database/__init__.py
mv ~/db_manager.py ~/hermes-trading/database/db_manager.py
mv ~/schema.sql ~/hermes-trading/database/schema.sql

mv ~/ai__init__.py ~/hermes-trading/ai/__init__.py
mv ~/gemini_client.py ~/hermes-trading/ai/gemini_client.py
mv ~/prompts.py ~/hermes-trading/ai/prompts.py

mv ~/backtest__init__.py ~/hermes-trading/backtest/__init__.py
mv ~/optimizer.py ~/hermes-trading/backtest/optimizer.py

mv ~/utils__init__.py ~/hermes-trading/utils/__init__.py
mv ~/telegram_bot.py ~/hermes-trading/utils/telegram_bot.py

# .env 복사
echo "[3/5] 환경변수 복사..."
cp ~/metis-futures/.env ~/hermes-trading/.env
echo "  metis-futures/.env → hermes-trading/.env 복사 완료"
echo "  ※ nano ~/hermes-trading/.env 에서 BYBIT_USE_TESTNET=false 확인"

# 가상환경
echo "[4/5] 가상환경 생성..."
cd ~/hermes-trading
python3 -m venv hermes
source hermes/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install optuna -q
echo "  가상환경: ~/hermes-trading/hermes/"

# 완료
echo "[5/5] 설치 완료!"
echo ""
echo "=== 실행 방법 ==="
echo "cd ~/hermes-trading && source hermes/bin/activate"
echo "nohup python3 -u main.py > ./logs/hermes.out 2>&1 &"
echo "tail -f ./logs/hermes.out"
