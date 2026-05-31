import wave
from pathlib import Path

import numpy as np
from core.config import CONFIG

SAMPLE_RATE = CONFIG["sample_rate"]


def load_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sr


def save_wav(path: str | Path, audio: np.ndarray, sr: int = SAMPLE_RATE):
    audio_i16 = (audio * 32768.0).clip(-32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_i16.tobytes())
