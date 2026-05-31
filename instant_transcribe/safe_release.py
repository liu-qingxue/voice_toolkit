from core.models import ParaformerV1Transcriber


class SafeRelease:
    """安全的模型释放包装。多次调用永不抛异常。"""

    def __init__(self, model: ParaformerV1Transcriber | None):
        self._model = model

    def try_release(self) -> bool:
        """释放模型。已释放则直接返回 True。"""
        if self._model is None:
            return True
        try:
            if self._model.is_loaded:
                self._model.unload()
            return True
        except Exception:
            return False

    def is_loaded(self) -> bool:
        if self._model is None:
            return False
        return self._model.is_loaded
