from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class Transcriber(ABC):
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


class MockTranscriber(Transcriber):
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "这是一段测试转录文本 ABC 123 !@#"
