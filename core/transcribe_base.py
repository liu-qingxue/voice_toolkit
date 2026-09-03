from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class TranscribeBase(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        ...

    def transcribe_file(self, wav_path: str | Path) -> str:
        from core.audio import load_wav
        audio, sr = load_wav(str(wav_path))
        if len(audio) == 0:
            return ""
        return self.transcribe(audio, sr).strip()

    @property
    def is_loaded(self) -> bool:
        return False

    def load(self):
        pass

    def unload(self):
        pass


class MockTranscriber(TranscribeBase):
    """模拟转录,用于验证外层代码的正确(调试前端链路用, 不碰模型)
    live.model 配成 mock 即启用"""
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        return "这是一段测试转录文本 ABC 123 !@#"
