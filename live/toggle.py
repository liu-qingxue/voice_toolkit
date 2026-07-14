"""
live 切换脚本。
向守护进程的命令文件写入 toggle，等待结果并输出。
"""
import json
import os
import fcntl
import subprocess
import sys
import time
from pathlib import Path
import logging

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import log
from config import CFG

logger=logging.getLogger("live/toggle.py")

LOCK = CFG.lock_file
RESULT = CFG.result_file
CMD = CFG.cannel_cmd

def _daemon_alive() -> bool:
    """检查守护进程是否持有排他锁"""
    try:
        fd = os.open(str(LOCK), os.O_RDONLY)
    except FileNotFoundError as e:
        logger.error(f"未找到锁: {e}")
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        # 拿到共享锁 → 没有排他锁持有者 → daemon 已死
        os.close(fd)
        return False
    except BlockingIOError as e:
        # 拿不到共享锁 → 排他锁被持有 → daemon 活着
        logger.info(f"拿不到共享锁,排他锁被持有: {e}")
        os.close(fd)
        return True


def _start_daemon() -> bool:
    daemon_script = ROOT / "live" / "main_daemon.py"
    proc = subprocess.Popen(
        [sys.executable, str(daemon_script)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(50):
        time.sleep(0.1)
        if LOCK.exists():
            break

    if not LOCK.exists():
        proc.kill()
        proc.wait()
        err = ""
        try:
            err = proc.stderr.read(4096).decode()
        except Exception as e:
            logger.error(e)
        logger.error(f"daemon 启动失败:\n{err or '(超时)'}")
        return False

    if proc.poll() is not None:
        err = proc.stderr.read().decode() if proc.stderr else ""
        LOCK.unlink(missing_ok=True)
        logger.error(f"daemon启动后即退出:\n{err}")
        return False

    return True


def toggle():
    if not _daemon_alive():
        if not _start_daemon():
            sys.exit(1)
        time.sleep(0.5)

    RESULT.unlink(missing_ok=True)
    CMD.write_text("toggle")

    for _ in range(50):
        if RESULT.exists():
            break
        time.sleep(0.1)
    else:
        return

    if RESULT.exists():
        try:
            result = json.loads(RESULT.read_text())
            text = result["text"]
        except (json.JSONDecodeError, KeyError):
            logger.error("结果文件损坏")
            RESULT.unlink(missing_ok=True)
            sys.exit(1)
        test_head = text[1:21]
        logger.info(f"转录结束,结果文件的头: {test_head}")
        print(text, end="", flush=True)

        RESULT.unlink(missing_ok=True)


if __name__ == "__main__":
    toggle()
