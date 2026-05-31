from abc import ABC, abstractmethod

import numpy as np


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        ...

    def load(self):
        pass

    def unload(self):
        pass


class MockTranscriber(Transcriber):
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        return "这是一段测试转录文本 ABC 123 !@#"
