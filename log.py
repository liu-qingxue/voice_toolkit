# log.py
import logging
import os
import sys
from pathlib import Path

def _default_log_file() -> Path:
    """日志文件路径(按需修改): Linux /tmp; Windows %LOCALAPPDATA%\voice_toolkit"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "voice_toolkit" / "live_transcriber.log"
    return Path("/tmp/live_transcriber.log")

LOG_FILE = _default_log_file()
LOG_FILE.parent.mkdir(parents= True, exist_ok= True)
# LOG_FILE.unlink(missing_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),          # 终端也保留
    ],
)