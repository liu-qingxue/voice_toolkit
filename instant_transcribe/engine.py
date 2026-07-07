from core.transcribe_base import Transcriber
from core.model_factory import create_transcriber, get_default_transcriber


class LiveEngine:
    """实时转录引擎"""
    
    def __init__(self, transcriber: Transcriber | None = None, model_type: str = "v1"):
        """
        Args:
            transcriber: 自定义转录器实例（可选）
            model_type: 模型类型（"v1" 或 "v2"），仅当 transcriber 为 None 时使用
        """
        if transcriber is not None:
            self._engine = transcriber
        else:
            # 默认使用 V1 用于实时场景，除非指定其他
            self._engine = create_transcriber(model_type)

    @property
    def is_loaded(self) -> bool:
        return hasattr(self._engine, 'is_loaded') and self._engine.is_loaded

    def load(self):
        if hasattr(self._engine, 'load'):
            self._engine.load()

    def unload(self):
        if hasattr(self._engine, 'unload'):
            self._engine.unload()

    def transcribe(self, audio, sample_rate: int = 16000) -> str:
        return self._engine.transcribe(audio, sample_rate)
    
    def set_transcriber(self, model_type: str) -> None:
        """切换转录器模型"""
        self.unload()
        self._engine = create_transcriber(model_type)

