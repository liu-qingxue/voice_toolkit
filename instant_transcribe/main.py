import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ..config.config import CONFIG  

ROOT = Path(__file__).resolve().parent.parent # 总项目目录
LOCK = Path(CONFIG["live"]["lock_file"])
STATUS = Path(str(LOCK) + "_status")

RESULT = Path(CONFIG["live"]["result_file"])


def _start_daemon() -> bool:
    daemon_script = ROOT / "instant_transcribe" / "daemon.py"
    proc = subprocess.Popen(
        [sys.executable, str(daemon_script)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # 等 LOCK 最多 5s
    for _ in range(50):
        time.sleep(0.1)
        if LOCK.exists():
            break

    # 这里默认了 LOCK 文件 与 daemon 进程相绑定
    if not LOCK.exists():
        """错误处理：daemon 启动失败或无显示器环境"""
        proc.kill()
        proc.wait()
        err = ""
        try:
            err = proc.stderr.read(4096).decode()
        except Exception:
            pass
        print(f"[live] daemon 启动失败:\n{err or '(超时无输出，可能是无显示器环境)'}", file=sys.stderr, flush=True)
        return False
    elif LOCK.exists():
        if proc.poll() is not None:
            err = proc.stderr.read().decode() if proc.stderr else ""
            LOCK.unlink(missing_ok=True)
            print(f"[live] daemon 启动后即退出:\n{err}", file=sys.stderr, flush=True)
            return False
        elif proc.poll() is None:
        # 防止 LOKE 未被及时清理影响下一次启动(启动失败了,但 LOCK 还在，下一次启动又失败了，就死循环了)
            return True



def toggle():
    if not LOCK.exists():
        lock_fd = open("/tmp/live_transcriber_daemon.lock", "w")
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if not LOCK.exists():
                if not _start_daemon():
                    sys.exit(1)
                time.sleep(0.5)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    is_recording = False
    try:
        is_recording = STATUS.exists() and STATUS.read_text().strip() == "recording"
    except Exception:
        pass

    try:
        pid = int(LOCK.read_text().strip())
    except (ValueError, FileNotFoundError):
        LOCK.unlink(missing_ok=True)
        print("[live] 锁文件损坏", file=sys.stderr)
        sys.exit(1)

    try:
        os.kill(pid, signal.SIGUSR1)
    except ProcessLookupError:
        LOCK.unlink(missing_ok=True)
        STATUS.unlink(missing_ok=True)
        print("[live] daemon 已退出", file=sys.stderr)
        sys.exit(1)

    if is_recording:
        for _ in range(1200):
            if RESULT.exists():
                break
            time.sleep(0.1)
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
        else:
            print("[live] 转录超时", file=sys.stderr)
            sys.exit(1)
    else:
        pass


if __name__ == "__main__":
    toggle()
