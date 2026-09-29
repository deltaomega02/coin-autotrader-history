"""ATHENA Health Check.

cron으로 매시간 실행 (또는 6시간마다).
ATHENA 프로세스 살아있나 확인 + 죽었으면 텔레그램 알림.

cron 설정:
  crontab -e
  # 매시간 5분마다 체크
  5 * * * * YOUR_INSTALL_DIR/athena/bin/python3 YOUR_INSTALL_DIR/health_check.py >> YOUR_INSTALL_DIR/health.log 2>&1
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests

# .env 로드
load_dotenv(Path(__file__).parent / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 미설정")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram 실패: {e}")


def is_athena_running() -> bool:
    """ATHENA main.py 프로세스 살아있나 (systemd 또는 nohup 무관)."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ATHENA/main.py"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip()
    except Exception:
        return False


def check_log_freshness() -> dict:
    """로그 마지막 업데이트 시각 (얼마나 오래 전).

    log가 30분 이상 안 갱신되면 = 멈췄을 가능성.
    """
    log_path = Path(__file__).parent / "output.log"
    if not log_path.exists():
        return {"exists": False}

    try:
        mtime = log_path.stat().st_mtime
        age_minutes = (datetime.now().timestamp() - mtime) / 60
        return {
            "exists": True,
            "age_minutes": round(age_minutes, 1),
            "size_mb": round(log_path.stat().st_size / 1024 / 1024, 2),
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. 프로세스 살아있나
    running = is_athena_running()

    # 2. 로그 신선도
    log_info = check_log_freshness()

    # 3. 정상이면 조용히 종료 (스팸 X)
    if running and log_info.get("age_minutes", 9999) < 30:
        # 정상 — 매일 한 번만 "alive" 알림 (옵션)
        # send_telegram(f"✅ ATHENA OK ({now})")
        print(f"[{now}] ATHENA OK (log {log_info['age_minutes']}m ago)")
        return

    # 4. 문제 발생 — 알림
    if not running:
        msg = f"🚨 ATHENA 프로세스 죽음 ({now})\n로그 마지막: {log_info.get('age_minutes', '?')}분 전"
        send_telegram(msg)
        print(msg)

        # systemd면 자동 재시작 — 그냥 알림만
        # nohup이면 수동 재시작 필요

    elif log_info.get("age_minutes", 0) >= 30:
        msg = (
            f"⚠️ ATHENA 프로세스는 살아있지만 로그 멈춤 ({now})\n"
            f"마지막 로그: {log_info['age_minutes']}분 전\n"
            f"확인 필요 (멈춤 가능)"
        )
        send_telegram(msg)
        print(msg)


if __name__ == "__main__":
    main()
