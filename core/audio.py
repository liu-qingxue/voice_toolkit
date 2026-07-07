import wave
from pathlib import Path

import numpy as np
from core.config import CONFIG

SAMPLE_RATE = CONFIG["sample_rate"]


def load_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """返回归一化好的振幅的ndarray数组,以及采样率
    wave.open打开-->getframerate-->采样率
                -->getntrames-->总帧数-->readframes-->读取所有帧的byte内容-->np.frombuffer-->ndarray整数数组-->astype(np.float32)-->浮点ndarray数组-->除以32768来归一化
    """
    with wave.open(str(path), "rb") as wf:   # 注意, 这里是 wave.open ,而不是常规的open
        sr = wf.getframerate()      # frame-帧
        frames = wf.readframes(wf.getnframes())   # getnframes,获取音频对象有多少帧; readframes,读取所有帧,返回的是byte?二进制字节
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0    # frombuffer, 将字节转化为整数数组; astyoe将整数转化为浮点; 最后归一化
    return audio, sr   # 这里返回的实际上是一个元组,所以上面的类型注释没有写错


def save_wav(path: str | Path, audio: np.ndarray, sr: int = SAMPLE_RATE):
    audio_i16 = (audio * 32768.0).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_i16.tobytes())
