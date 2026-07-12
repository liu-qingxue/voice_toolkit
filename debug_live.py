"""
隔离调试：启动守护进程，分离 stderr，逐步发命令。
用法:
  python3 debug_live.py start    # 启动
  python3 debug_live.py toggle   # 发切换命令
  python3 debug_live.py check    # 检查状态
  python3 debug_live.py stop     # 停止
"""
import os, sys, time, json, subprocess, signal
from pathlib import Path

LOCK = Path("/tmp/live_transcriber.lock")
CMD = Path("/tmp/live_transcriber.lock_cmd")
RESULT = Path("/tmp/live_transcriber_result.json")
ROOT = Path(__file__).resolve().parent

def cmd_start():
    if LOCK.exists():
        print("已有守护进程在运行")
        return
    daemon = ROOT / "live" / "main_daemon.py"
    proc = subprocess.Popen(
        [sys.executable, str(daemon)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=open("/tmp/live_daemon_stderr.log", "w"),
    )
    # 等 LOCK
    for _ in range(50):
        if LOCK.exists():
            break
        time.sleep(0.1)
    if LOCK.exists():
        print(f"守护进程已启动 (pid={LOCK.read_text().strip()})")
    else:
        print("启动超时")

def cmd_toggle():
    if not LOCK.exists():
        print("守护进程未运行")
        return
    RESULT.unlink(missing_ok=True)
    CMD.write_text("toggle")
    print("toggle 命令已发送")
    # 等结果
    for _ in range(50):
        if RESULT.exists():
            break
        time.sleep(0.1)
    else:
        print("（无结果，可能是开始录音）")
        return
    if RESULT.exists():
        data = json.loads(RESULT.read_text())
        print(f"转录结果: {data['text']}")
        RESULT.unlink()

def cmd_check():
    if LOCK.exists():
        pid = int(LOCK.read_text().strip())
        alive = os.kill(pid, 0) is None
        print(f"LOCK 存在, pid={pid}, 存活={alive}")
    else:
        print("LOCK 不存在")
    print(f"CMD 文件: {'存在' if CMD.exists() else '不存在'}")
    print(f"RESULT 文件: {'存在' if RESULT.exists() else '不存在'}")
    if RESULT.exists():
        print(f"  内容: {RESULT.read_text()[:200]}")

def cmd_stop():
    if LOCK.exists():
        pid = int(LOCK.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        LOCK.unlink(missing_ok=True)
        print(f"已发送 SIGTERM 给 {pid}")
    print("--- daemon stderr ---")
    try:
        print(open("/tmp/live_daemon_stderr.log").read()[-2000:])
    except:
        pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    {"start": cmd_start, "toggle": cmd_toggle, "check": cmd_check, "stop": cmd_stop}[sys.argv[1]]()
