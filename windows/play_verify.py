"""Windows 声音播放途径【验证器】——逐个验证哪种 API 真的能出声。

⚠️ 必须在【你自己的终端】(桌面会话)里运行, 不要经远程/服务会话:
    cd E:\\Projects\\voice_toolkit
    venv\\Scripts\\python.exe windows\\play_verify.py

依次播放 5 种途径(每种间隔约 1.6 秒), 请记录你听到哪几个编号,
例如"2、4、5 响, 1、3 不响"。把编号报给开发者即可。
"""
import os
import struct
import sys
import tempfile
import time

VOL = 0.4   # 合成波形振幅(0~1)


def synth_wav(tones, vol=VOL) -> bytes:
    """tones: [(freq,ms),...]; freq<=0 = 静音间隔; 返回 44.1k 16bit 单声道 wav"""
    import numpy as np
    sr = 44100
    chunks = []
    for freq, ms in tones:
        n = int(sr * ms / 1000)
        if freq <= 0:
            chunks.append(np.zeros(n, dtype=np.float32))
            continue
        t = np.arange(n) / sr
        env = np.ones(n)
        fade = max(1, int(sr * 0.004))
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
        chunks.append(np.sin(2 * np.pi * freq * t) * env)
    wave = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    pcm = (wave * vol * 32767).astype("<i2")
    data = pcm.tobytes()
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE", b"fmt ", 16,
        1, 1, sr, sr * 2, 2, 16, b"data", len(data),
    ) + data


TMP_WAV = os.path.join(tempfile.gettempdir(), "voice_verify.wav")


def _ensure_tmp_wav():
    if not os.path.exists(TMP_WAV):
        with open(TMP_WAV, "wb") as f:
            f.write(synth_wav([(880, 180)]))


def play_1_beep():
    """途径1: winsound.Beep(方波, 系统提示音通道)"""
    import winsound
    winsound.Beep(880, 180)


def play_2_sounddevice():
    """途径2: sounddevice 正弦波(PortAudio)"""
    import numpy as np
    import sounddevice as sd
    sr = 44100
    n = int(sr * 0.18)
    t = np.arange(n) / sr
    env = np.ones(n)
    fade = int(sr * 0.005)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    wave = (VOL * np.sin(2 * np.pi * 880 * t) * env).astype(np.float32)
    sd.play(wave, sr)
    sd.wait()


def play_3_playsound_memory():
    """途径3: winsound.PlaySound 内存 wav"""
    import winsound
    winsound.PlaySound(synth_wav([(880, 180)]), winsound.SND_MEMORY | winsound.SND_SYNC)


def play_4_playsound_file():
    """途径4: winsound.PlaySound 文件 wav(SND_FILENAME)"""
    import winsound
    _ensure_tmp_wav()
    winsound.PlaySound(TMP_WAV, winsound.SND_FILENAME | winsound.SND_SYNC)


def play_5_soundplayer():
    """途径5: PowerShell SoundPlayer 播放文件(无窗口)"""
    import subprocess
    _ensure_tmp_wav()
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
         "-Command", f"(New-Object Media.SoundPlayer '{TMP_WAV}').PlaySync()"],
        creationflags=0x08000000, timeout=10,
    )


def main():
    print("依次播放 5 种途径, 请记录听到的编号...", flush=True)
    items = [
        ("1 winsound.Beep(方波,对照)", play_1_beep),
        ("2 sounddevice 正弦波", play_2_sounddevice),
        ("3 PlaySound 内存wav", play_3_playsound_memory),
        ("4 PlaySound 文件wav", play_4_playsound_file),
        ("5 PowerShell SoundPlayer", play_5_soundplayer),
    ]
    for label, fn in items:
        print(f">>> 正在播放: {label}", flush=True)
        try:
            fn()
            print(f"    {label} 执行完成(无异常)", flush=True)
        except Exception as e:
            print(f"    {label} 抛异常: {e}", flush=True)
        time.sleep(1.6)
    print("全部播完。请回复: 哪几个编号有声音?", flush=True)


if __name__ == "__main__":
    main()
