"""
voice_toolkit Windows 快捷键入口 —— 无窗口版

用 pythonw.exe 运行, GUI 子系统 → 永不弹终端:
    <项目>/venv/Scripts/pythonw.exe  <项目>/windows/run_hotkey.py

一次运行 = 一次 toggle:
  ① daemon 待机(idle)  → 开始录音(托盘变红)
  ② 录音中(recording) → 停止并转录, 文本 SendInput 注入当前光标
  ③ 转录中(transcribing) → daemon 忽略
出错(daemon 起不来等) → 三声低音

反馈时序(跟手原则, 与录音逻辑解耦):
  - 按下瞬间应立即反馈(不等待任何后端逻辑)
  - 转录文本上屏后再播成功音

⚠️ 声音开关已从【代码常量】移到【生效配置 config.yaml 的 sounds: 段】:
  - 嫌吵: 配置里 enabled: false 即可一键全静音, 不用改代码。
  - 播放通道背景(play_verify.py 实测 2026-09): Beep/sounddevice 时响时不响,
    PlaySound 不响且抛 AttributeError(本机 Python312 的 winsound.pyd 缺失
    SND_SYNC, 疑似发行版裁剪); 仅 PowerShell SoundPlayer 稳定。
  - 播放实现: 预生成 wav + PowerShell SoundPlayer。
参数:
  --dry-run   只跑 toggle 不注入、不响(调试链路用)
"""
import os
import sys
from pathlib import Path

# pythonw 下 stdout/stderr 为 None, 兜底到 devnull, 防止 print/logger 崩
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.toggle import ToggleError, toggle_capture

# ── 声音反馈: 预生成 wav + PowerShell SoundPlayer ──────────
# 开关从生效配置读取: %APPDATA%\voice_toolkit\config.yaml 的 sounds: 段。
# 总开关 enabled=false 时全部静音(耳机/嫌吵一键关); 三个子开关只在该
#   enabled=true 时生效(start 按键嗒/done 上屏成功/fail 出错)。
# 配置缺失/解析失败 → 用下列代码默认(永不因配置问题崩)。
_SOUND_DEFAULT = {
    "enabled": True,   # 总开关
    "start": False,    # 按键"嗒"(本机播放时序体验差, 默认关)
    "done": True,      # 上屏成功双高音(音色温和, 默认开)
    "fail": False,     # 出错三低音(默认关)
}
_SOUND_CFG = dict(_SOUND_DEFAULT)


def _load_sound_cfg():
    """从生效配置读 sounds: 段并合并(仅接受 bool, 其余保持默认); 容错静默。"""
    try:
        import yaml
        cfg_dir = os.environ.get("APPDATA") or os.path.expanduser("~")
        p = os.path.join(cfg_dir, "voice_toolkit", "config.yaml")
        with open(p, encoding="utf-8") as f:
            s = (yaml.safe_load(f) or {}).get("sounds") or {}
        for k in _SOUND_DEFAULT:
            if k in s and isinstance(s[k], bool):
                _SOUND_CFG[k] = s[k]
    except Exception:
        pass  # 配置读不到就用代码默认, 不阻塞快捷键功能


_load_sound_cfg()

# 音色: (freq Hz, 时长 ms); freq<=0 = 静音间隔
_SOUNDS = {
    "start": ((560, 75),),                                    # 按键收到: 一声短"嗒"
    "done": ((880, 100), (0, 40), (1320, 180)),               # 上屏成功: 温和双高音
    "fail": ((300, 110), (0, 80), (220, 140), (0, 80), (180, 220)),  # 出错三低音
}
_SOUND_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "voice_toolkit", "sounds"
)
_BEEP_VOL = 0.4   # 响度(0~1); 环境变量 VOX_BEEP_VOL 可覆盖; VOX_NO_BEEP=1 静音


def _synth_wav_bytes(tones) -> bytes:
    """合成 44.1k 16bit 单声道 wav 字节"""
    import numpy as _np
    import struct as _st
    sr = 44100
    chunks = []
    for freq, ms in tones:
        n = int(sr * ms / 1000)
        if freq <= 0:
            chunks.append(_np.zeros(n, dtype=_np.float32))
            continue
        t = _np.arange(n) / sr
        env = _np.ones(n)
        fade = max(1, int(sr * 0.004))   # 4ms 淡入淡出防爆音
        env[:fade] = _np.linspace(0, 1, fade)
        env[-fade:] = _np.linspace(1, 0, fade)
        chunks.append(_np.sin(2 * _np.pi * freq * t) * env)
    wave = _np.concatenate(chunks) if chunks else _np.zeros(1, dtype=_np.float32)
    pcm = (wave * _BEEP_VOL * 32767).astype("<i2")
    data = pcm.tobytes()
    hdr = _st.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE", b"fmt ", 16,
        1, 1, sr, sr * 2, 2, 16, b"data", len(data),
    )
    return hdr + data


def _ensure_sound_files():
    """预生成三个固定提示音 wav(已存在则跳过, 零开销)"""
    try:
        os.makedirs(_SOUND_DIR, exist_ok=True)
        for name, tones in _SOUNDS.items():
            p = os.path.join(_SOUND_DIR, name + ".wav")
            if not os.path.exists(p):
                with open(p, "wb") as f:
                    f.write(_synth_wav_bytes(tones))
    except Exception:
        pass


_ensure_sound_files()


def _play_sound(name: str):
    """PowerShell SoundPlayer 无窗口播放固定 wav(实测唯一稳定通道)。
    总开关关闭或对应子开关关闭时直接返回。"""
    try:
        if not _SOUND_CFG["enabled"] or not _SOUND_CFG[name]:
            return
        if os.environ.get("VOX_NO_BEEP") == "1":
            return
        import subprocess
        path = os.path.join(_SOUND_DIR, name + ".wav")
        cmd = f"(New-Object Media.SoundPlayer '{path}').PlaySync()"
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
            creationflags=0x08000000,   # CREATE_NO_WINDOW
            timeout=10,
        )
    except Exception:
        pass  # 静默失败


def _beep_received():
    """按键收到(按下瞬间反馈, 与录音逻辑无关)"""
    _play_sound("start")


def _beep_success():
    """推理完成/文本已注入光标"""
    _play_sound("done")


def _beep_failed():
    """出错"""
    _play_sound("fail")


# ── 单实例互斥: 连按/重复触发时丢弃后到按键, 防并行 toggle/播放叠加 ──
_MUTEX_HANDLE = None


def _acquire_single_instance() -> bool:
    global _MUTEX_HANDLE
    if "--dry-run" in sys.argv:
        return True
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = wintypes.HANDLE
        _MUTEX_HANDLE = k32.CreateMutexW(None, False, "Local\\voice_toolkit_hotkey")
        return ctypes.get_last_error() != 183   # 183 = ERROR_ALREADY_EXISTS
    except Exception:
        return True   # 互斥失败不阻塞使用


# ── SendInput 光标注入(ctypes 直调 user32, 不碰剪贴板) ────
def _send_input_text(text: str) -> bool:
    import ctypes
    from ctypes import wintypes

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    VK_RETURN = 0x0D

    class MOUSEINPUT(ctypes.Structure):
        """补位成员: x64 上真实 INPUT 的 union 取 MOUSEINPUT(32B) 为最大,
        INPUT 总大小 40B。只含键盘会让 sizeof=32, SendInput 校验 cbSize 时报
        ERROR_INVALID_PARAMETER(87) 拒绝——这是之前注入失败的根因。"""
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_ulonglong),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_ulonglong),  # ULONG_PTR
        ]

    class _UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]

    def _key_unicode(ch: str, key_up: bool) -> INPUT:
        i = INPUT()
        i.type = INPUT_KEYBOARD
        i.ki.wVk = 0
        i.ki.wScan = ord(ch)   # KEYEVENTF_UNICODE: wScan 即 UTF-16 码元
        i.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
        return i

    def _key_vk(vk: int, key_up: bool) -> INPUT:
        i = INPUT()
        i.type = INPUT_KEYBOARD
        i.ki.wVk = vk
        i.ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
        return i

    # 换行统一转回车键(与真实键盘一致, 应用兼容性最好); 其余字符走 Unicode(绕过输入法)
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    inputs: list = []
    for ch in norm:
        if ch == "\n":
            inputs.append(_key_vk(VK_RETURN, False))
            inputs.append(_key_vk(VK_RETURN, True))
        else:
            inputs.append(_key_unicode(ch, False))
            inputs.append(_key_unicode(ch, True))

    user32 = ctypes.windll.user32
    send = user32.SendInput
    send.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    send.restype = wintypes.UINT
    size = ctypes.sizeof(INPUT)

    # SendInput 单次上限较大, 分批发送更稳
    BATCH = 500
    for off in range(0, len(inputs), BATCH):
        seg = inputs[off:off + BATCH]
        arr = (INPUT * len(seg))(*seg)
        if send(len(seg), arr, size) != len(seg):
            return False
    return True


# ── 主流程 ─────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv

    if not _acquire_single_instance():
        # 上一个按键还在处理中, 丢弃本次, 防止 toggle/声音并发错乱
        return 0

    # 跟手: 按下瞬间立即给一声"嗒", 不等待任何后端逻辑
    if not dry_run:
        _beep_received()

    try:
        text = toggle_capture()
    except ToggleError as e:
        print(f"[run_hotkey] toggle 失败: {e}", file=sys.stderr)
        if not dry_run:
            _beep_failed()
        return 1

    if not text:
        # 开始录音 / 转录中忽略 / 空结果 → 已响过"嗒", 不再补音(托盘图标是状态主力)
        return 0

    print(f"[run_hotkey] 转录文本({len(text)}字): {text[:50]}", file=sys.stderr)
    if dry_run:
        return 0

    if _send_input_text(text):
        if not dry_run:
            _beep_success()
    else:
        print("[run_hotkey] SendInput 注入失败(目标窗口可能是管理员权限)", file=sys.stderr)
        if not dry_run:
            _beep_failed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
