import logging
import tempfile
import os
import numpy as np
from config.config import CFG
from core.transcribe_base import TranscribeBase
from pathlib import Path
from funasr import AutoModel

logger = logging.getLogger(__name__)

os.environ.setdefault("MODELSCOPE_DISABLE_NETWORK", "1") # .setdefault(key, value)	只在 key 不存在 时才设值（已存在则跳过）

class ParaformerV1Transcriber(TranscribeBase):
    """SeACo-Paraformer — 实时转录用。
    最优配置: ncpu=2, 纯净 CER=7.68%, RTF=0.187x
    """
    def __init__(self):
        self.ncpu = CFG.ncpu
        self.model_dir = CFG.model_dir
        self.vad_dir = CFG.vad_dir
        self.punc_dir = CFG.punc_dir
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
            device="cpu",
            disable_pbar=True,  # 无加载进度条
            disable_update=True, # 不更新
            vad_model=self.vad_dir,
            vad_model_revision="v2.0.4",
            vad_kwargs={"max_single_segment_time": 30000},  # VAD 参数：单段最长 30 秒
            punc_model=self.punc_dir,
            punc_model_revision="v2.0.4",
        )
        self._model = AutoModel(**kwargs)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if len(audio) == 0:
            return ""
        if self._model is None:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[V1] 模型加载失败: {e}", exc_info=True)
                return "[模型加载错误]"
        if audio.ndim > 1:
            audio = audio.squeeze()  # 某些录音设备返回的音频带多余的维度,模型只认一维数组,去掉大小为1的维度
        
        tmp_path = None
        try:
            from core.audio import save_wav
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name  # 这里实际上获取了path
            tmp.close()
            
            save_wav(tmp_path, audio, sample_rate)
            result = self._model.generate(input=tmp_path)
            return self._extract(result)
            
        except TypeError as e:
            logger.error(f"[V1] 模型参数错误: {e}")
            return "[参数错误]"
        except RuntimeError as e:
            logger.error(f"[V1] 模型推理失败: {e}", exc_info=True)
            return "[推理失败]"
        except Exception as e:
            logger.error(f"[V1] 未知转录错误: {e}", exc_info=True)
            return "[转录异常]"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as e:
                    logger.warning(f"[V1] 临时文件删除失败: {tmp_path}, {e}")
    @staticmethod
    def _extract(result) -> str:
        if isinstance(result, list):
            texts = [r.get("text", "") for r in result if isinstance(r, dict)]
            return "\n".join(t for t in texts if t).strip()
        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()

    def unload(self):
        self._model = None



class ParaformerV2Transcriber(TranscribeBase):
    """Paraformer VAD+Punc — 日志转录用。
    最优配置: ncpu=2, 降质 CER=18.35% (全场最低), RTF=0.140x
    """
    MODEL_ID = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"

    def __init__(self, ncpu: int | None = None, model_dir: str | None = None):
        self.ncpu = ncpu or CFG.ncpu
        self.model_dir = model_dir
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self):
        if self._model is not None:
            return
        from funasr import AutoModel
        model_dir = self.model_dir or CFG.model_dir

        if not model_dir:
            model_dir = str(Path.home() / ".cache/modelscope/hub")

        model_path = model_dir
        vad_path = _local_path("iic/speech_fsmn_vad_zh-cn-16k-common-pytorch")
        punc_path = _local_path("iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch")

        for name, path in [("主模型", model_path), ("VAD", vad_path), ("标点", punc_path)]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"本地{name}模型路径不存在: {path}")

        kwargs = dict(
            model=model_path,
            model_revision="v2.0.4",
            ncpu=self.ncpu,
            device="cpu",
            disable_pbar=True,
            disable_update=True,
            cache_dir=model_dir,
            vad_model=vad_path,
            vad_model_revision="v2.0.4",
            vad_kwargs={"max_single_segment_time": 30000},
            punc_model=punc_path,
            punc_model_revision="v2.0.4",
        )
        if model_dir:
            kwargs["model_dir"] = model_dir
        self._model = AutoModel(**kwargs)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if len(audio) == 0:
            return ""
        if audio.ndim > 1:
            audio = audio.squeeze()
        if self._model is None:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[V2] 模型加载失败: {e}", exc_info=True)
                return "[模型加载错误]"
        
        tmp_path = None
        try:
            from core.audio import save_wav
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()
            
            save_wav(tmp_path, audio, sample_rate)
            result = self._model.generate(input=tmp_path)
            return self._extract(result)
            
        except TypeError as e:
            logger.error(f"[V2] 模型参数错误: {e}")
            return "[参数错误]"
        except RuntimeError as e:
            logger.error(f"[V2] 模型推理失败: {e}", exc_info=True)
            return "[推理失败]"
        except Exception as e:
            logger.error(f"[V2] 未知转录错误: {e}", exc_info=True)
            return "[转录异常]"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError as e:
                    logger.warning(f"[V2] 临时文件删除失败: {tmp_path}, {e}")

    def unload(self):
        self._model = None

    @staticmethod
    def _extract(result) -> str:
        if isinstance(result, list):
            texts = [r.get("text", "") for r in result if isinstance(r, dict)]
            return "\n".join(t for t in texts if t).strip()
        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()
