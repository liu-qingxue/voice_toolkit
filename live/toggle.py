"""
live 切换脚本。
向守护进程的命令文件写入 toggle，等待结果并输出。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import CFG

LOCK = Path(CFG.lock_file)
RESULT = Path(CFG.result_file)
CMD = Path(str(LOCK) + "_cmd")


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
        except Exception:
            pass
        print(f"[live] daemon 启动失败:\n{err or '(超时)'}", file=sys.stderr, flush=True)
        return False

    if proc.poll() is not None:
        err = proc.stderr.read().decode() if proc.stderr else ""
        LOCK.unlink(missing_ok=True)
        print(f"[live] daemon 启动后即退出:\n{err}", file=sys.stderr, flush=True)
        return False

    return True


def toggle():
    if not LOCK.exists():
        if not _start_daemon():
            sys.exit(1)
        time.sleep(0.5)

    try:
        pid = int(LOCK.read_text().strip())
    except (ValueError, FileNotFoundError):
        LOCK.unlink(missing_ok=True)
        print("[live] 锁文件损坏", file=sys.stderr)
        sys.exit(1)

    # 检查守护进程是否存活
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        LOCK.unlink(missing_ok=True)
        print("[live] daemon 已退出", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        pass

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
            print("[live] 结果文件损坏", file=sys.stderr)
            RESULT.unlink(missing_ok=True)
            sys.exit(1)
        print(text, end="", flush=True)
        RESULT.unlink(missing_ok=True)


if __name__ == "__main__":
    toggle()
