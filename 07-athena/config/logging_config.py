"""로깅 설정. HERMES 패턴 재활용."""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging(level=logging.INFO):
    """로거 셋업: 콘솔 + 일별 로테이션 파일 (14일 보관)."""
    root = logging.getLogger()
    root.setLevel(level)

    # 중복 핸들러 방지
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # 파일 (일별 로테이션)
    fh = TimedRotatingFileHandler(
        LOG_DIR / "athena.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
