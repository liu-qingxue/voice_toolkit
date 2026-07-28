import logging
import os
import numpy as np
from config import Config
from core.transcribe_base import TranscribeBase
from pathlib import Path
from funasr import AutoModel
from core.audio import load_wav


logger = logging.getLogger("core/models.py")

os.environ.setdefault("MODELSCOPE_DISABLE_NETWORK", "1") # .setdefault(key, value)	只在 key 不存在 时才设值（已存在则跳过）

class ParaformerTranscriber(TranscribeBase):
    """ # SeACo-Paraformer模型引擎
    - 在使用 transcribe 时有逻辑保证模型加载
    - 依赖上游的函数传递mode!
    SeACo-Paraformer2 — 实时转录用。
    最优配置: ncpu=2, 纯净 CER=7.68%, RTF=0.187x
    """
    def __init__(self,mode: str= "live"):
        CFG = Config(mode)
        self.ncpu = CFG.ncpu
        self.model_dir = CFG.model_dir
        self.vad_dir = CFG.vad_dir
        self.punc_dir = CFG.punc_dir
        self.device = CFG.device
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self):
        """已经加载了model就返回None"""
        if self._model is not None:
            return
        
        for name, path in [("主模型", self.model_dir), ("VAD", self.vad_dir), ("标点", self.punc_dir)]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"本地{name}模型路径不存在: {path}")

        kwargs = dict(
            model=self.model_dir,
            model_revision="v2.0.4",
            ncpu=self.ncpu,
            device=self.device,
            disable_pbar=True,  # 无加载进度条
            disable_update=True, # 不更新
            vad_model=self.vad_dir,
            vad_model_revision="v2.0.4",
            vad_kwargs={"max_single_segment_time": 30000},  # VAD 参数：单段最长 30 秒
            punc_model=self.punc_dir,
            punc_model_revision="v2.0.4",
        )
        try:
            self._model = AutoModel(**kwargs)
            logger.info("model加载成功")
        except Exception as e:
            raise RuntimeError(f"模型加载失败: {e}") from e

    def unload(self):
        self._model = None

    def transcribe(self, audio: np.ndarray | Path | str,sample_rate: int = 16000) -> str:
        """### audio无论是路径还是数组都可返回 *转录*后的,*处理*好的str
        - 对于 sample_rate 默认为16k,对于 Paraformer 模型只能为16k
        """
        # 1. 如果是路径，立刻加载成数组
        if isinstance(audio,(str,Path)):
            audio, _ = load_wav(audio)

        # 2. 现在 audio 一定是 np.ndarray,安全地做数组操作
        if len(audio) == 0:
            return ""
        if audio.ndim > 1:
            audio = audio.squeeze()  # 某些录音设备返回的音频带多余的维度,模型只认一维数组,去掉大小为1的维度

        # 3. 保证 model 被加载
        if self._model is None:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[V1] 模型加载失败: {e}", exc_info=True)
                return "[模型加载错误]"
            
        # 4. 推理
        logger.info(f"开始推理, 音频长度: {len(audio)}")
        try:
            result = self._model.generate(input=audio)
            logger.info(f"推理完成, 原始结果: {type(result)}")
            text = self._extract(result)
            logger.info(f"提取文本: {text[:50]!r}")
            return text
        except TypeError as e:
            logger.error(f"[V1] 模型参数错误: {e}", exc_info=True)
            return "[参数错误]"
        except RuntimeError as e:
            logger.error(f"[V1] 模型推理失败: {e}", exc_info=True)
            return "[推理失败]"
        except Exception as e:
            logger.error(f"[V1] 未知转录错误: {e}", exc_info=True)
            return "[转录异常]"
        
    @staticmethod   # 不读类属性
    def _extract(result) -> str:
        """内部的字符处理函数"""
        if isinstance(result, list):
            texts = [r.get("text", "") for r in result if isinstance(r, dict)]
            return "\n".join(t for t in texts if t).strip()   # 接受迭代器来拼接所有字符
        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()

