"""
live 切换脚本。
向守护进程的命令文件写入 toggle，根据 daemon 的 state 决定本次该"开始录音"还是"等待转录结果"。

跨平台说明:
- Linux:   fcntl 排他锁探测 daemon 死活(沿用旧机制)
- Windows: daemon 用 PID 文件互斥, 这里读 PID + OpenProcess 探测进程存活
- state 文件(idle/recording/transcribing)由 daemon 维护, 解决了旧版
  "无条件空等 5s、长录音转录结果丢失"的问题:
    idle/空         → 本次 toggle = 开始录音, 立即返回
    recording       → 本次 toggle = 停止录音并转录, 等待结果出现
    transcribing    → daemon 会忽略本次 toggle, 立即返回
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import CFG

logger = logging.getLogger("live/toggle.py")

LOCK = CFG.lock_file
RESULT = CFG.result_file
CMD = CFG.cannel_cmd
STATE = CFG.state_file

# 等待转录结果的最长秒数(录音上限内的音频都该完成, 超时视为异常)
_WAIT_RESULT_SEC = 120.0

# ── 平台相关: fcntl(Linux) / PID 文件探测(Windows) ──────────
try:
    import fcntl  # Linux: POSIX 文件锁
except ImportError:
    fcntl = None  # Windows: 无 fcntl 模块, 走 PID 探测


def _win_pid_alive(pid: int) -> bool:
    """Windows 进程存活探测。
    ⚠️ 注意: 不能用 os.kill(pid, 0) —— Windows 上 os.kill 除 CTRL_* 外
    一律调用 TerminateProcess, pid 0 也会真的把进程"终止"(以 0 为退出码)。
    """
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    kernel32.CloseHandle(h)
    return True


def _daemon_alive() -> bool:
    if fcntl is not None:
        # Linux: 尝试拿共享锁 → 拿到 = 无排他锁持有者 = daemon 已死
        try:
            fd = os.open(str(LOCK), os.O_RDONLY)
        except FileNotFoundError as e:
            logger.error(f"未找到锁: {e}")
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            os.close(fd)
            return False
        except BlockingIOError as e:
            # 拿不到共享锁 → 排他锁被持有 → daemon 活着
            logger.info(f"拿不到共享锁,排他锁被持有: {e}")
            os.close(fd)
            return True
    # Windows: PID 文件(daemon 写入自己 PID)
    try:
        pid = int(LOCK.read_text().strip())
    except (OSError, ValueError):
        return False
    return _win_pid_alive(pid)


def _start_daemon() -> bool:
    daemon_script = ROOT / "live" / "main_daemon.py"
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # 无控制台窗口
    proc = subprocess.Popen(
        [sys.executable, str(daemon_script)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **kwargs,
    )
    # 等待 daemon 建立锁/PID 文件。
    # 注意: daemon 需完成全部 import 才创建锁。qwen3_asr 模式已懒加载 torch(~1-2s),
    # 但 paraformer 模式 import torch 可能 3~10s, 慢机器更久, 所以放宽到 20s。
    for _ in range(200):
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


def _read_state() -> str:
    """读 daemon 当前状态: idle / recording / transcribing / 空(无 daemon)"""
    try:
        return STATE.read_text().strip() or ""
    except OSError:
        return ""


def toggle():
    if not _daemon_alive():
        if not _start_daemon():
            sys.exit(1)
        time.sleep(0.5)

    state = _read_state()
    logger.info(f"发送 toggle 前 daemon 状态: {state!r}")

    RESULT.unlink(missing_ok=True)   # 清掉残留结果, 防止读到旧文本
    CMD.write_text("toggle")

    if state == "recording":
        # 本次 toggle = 停止录音并转录 → 等待结果出现
        deadline = time.time() + _WAIT_RESULT_SEC
        while time.time() < deadline:
            if RESULT.exists():
                break
            # daemon 状态回到 idle 而 result 未出现 → 本次被丢弃(空音频/录音失败), 立即返回
            if _read_state() not in ("recording", "transcribing"):
                logger.info("daemon 已回到 idle 且无结果(空音频/失败), 本次无输出")
                return
            time.sleep(0.1)
        else:
            logger.warning(f"等待转录结果超时({_WAIT_RESULT_SEC}s)")
            return

        if RESULT.exists():
            try:
                # dispatcher 用 utf-8 写; Windows 下 read_text() 默认按 GBK 解码会崩, 必须显式指定
                result = json.loads(RESULT.read_text(encoding="utf-8"))
                text = result["text"]
            except (json.JSONDecodeError, KeyError):
                logger.error("结果文件损坏")
                RESULT.unlink(missing_ok=True)
                sys.exit(1)
            logger.info(f"转录结束,结果文本长度: {len(text)}")
            # Windows 控制台默认编码可能是 GBK, 强制 UTF-8, 便于 run.ps1 捕获
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
            print(text, end="", flush=True)
            RESULT.unlink(missing_ok=True)
    else:
        # state 为空/idle → 本次开始录音(daemon 会立即切到 recording), 无需等待;
        # state=transcribing → daemon 忽略本次 toggle 并提示, 也无需等待。
        logger.info("本次为开始录音(或转录中忽略), 无需等待结果")


if __name__ == "__main__":
    toggle()
