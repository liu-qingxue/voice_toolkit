# log.py
import logging
import sys
from pathlib import Path

# 硬编码日志文件路径（按需修改）
LOG_FILE = Path("/tmp/live_transcriber.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),          # 终端也保留
    ],
)