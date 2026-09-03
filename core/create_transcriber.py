"""
转录器入口 —— 给我音频，给你文本。

模型分发在 这里处理，新增模型只需在这里加分支。
"""
import logging
from config import Config
from core.models import ParaformerTranscriber, QwenTranscriber
from core.transcribe_base import MockTranscriber

logger = logging.getLogger("core/create_transcriber.py")

transcriber = None
transcriber_model = None   # 记录创建时的 model 值

def create_transcriber(mode: str= "live") -> ParaformerTranscriber :
    CFG = Config(mode)
    global transcriber, transcriber_model
    model = CFG.model

    # CFG 变了 → 丢弃旧缓存
    if transcriber is not None and transcriber_model != model:
        transcriber.unload()
        transcriber = None

    if transcriber is None:
        if model == "mock":
            # 调试前端链路用: 不加载任何模型, 固定返回测试文本
            transcriber = MockTranscriber()
        elif model in ("paraformer_v1", "paraformer_v2"):
            transcriber = ParaformerTranscriber(mode)
        elif model == "qwen3_asr":
            transcriber = QwenTranscriber(mode, model_name=model)
        else:
            raise ValueError(f"不支持的模型类型: {model}")
        transcriber_model = model

    return transcriber