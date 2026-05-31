import logging
import tempfile
import os
import numpy as np
from core.config import CONFIG
from core.transcriber import Transcriber

logger = logging.getLogger(__name__)


class ParaformerV1Transcriber(Transcriber):
    """SeACo-Paraformer — 实时转录用。
    最优配置: ncpu=2, 纯净 CER=7.68%, RTF=0.187x
    """
    MODEL_ID = "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"

    def __init__(self, ncpu: int | None = None, model_dir: str | None = None):
        self.ncpu = ncpu or CONFIG.get("model", {}).get("ncpu", 2)
        self.model_dir = model_dir
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self):
        if self._model is not None:
            return
        from funasr import AutoModel
        model_id = CONFIG.get("model", {}).get("live") or self.MODEL_ID
        model_dir = self.model_dir or CONFIG.get("model", {}).get("dir")
        kwargs = dict(
            model=model_id,
            model_revision="v2.0.4",
            ncpu=self.ncpu,
            device="cpu",
            disable_pbar=True,
            disable_update=True,
            vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
            vad_model_revision="v2.0.4",
            vad_kwargs={"max_single_segment_time": 30000},
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
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
                logger.error(f"[V1] 模型加载失败: {e}", exc_info=True)
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

    def unload(self):
        self._model = None

    @staticmethod
    def _extract(result) -> str:
        if isinstance(result, list):
            texts = [r.get("text", "") for r in result if isinstance(r, dict)]
            return "".join(texts).strip()
        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()


class ParaformerV2Transcriber(Transcriber):
    """Paraformer VAD+Punc — 日志转录用。
    最优配置: ncpu=2, 降质 CER=18.35% (全场最低), RTF=0.140x
    """
    MODEL_ID = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"

    def __init__(self, ncpu: int | None = None, model_dir: str | None = None):
        self.ncpu = ncpu or CONFIG.get("model", {}).get("ncpu", 2)
        self.model_dir = model_dir
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self):
        if self._model is not None:
            return
        from funasr import AutoModel
        model_id = CONFIG.get("model", {}).get("diary") or self.MODEL_ID
        model_dir = self.model_dir or CONFIG.get("model", {}).get("dir")
        kwargs = dict(
            model=model_id,
            model_revision="v2.0.4",
            ncpu=self.ncpu,
            device="cpu",
            disable_pbar=True,
            disable_update=True,
            vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
            vad_model_revision="v2.0.4",
            vad_kwargs={"max_single_segment_time": 30000},
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
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
            return "".join(texts).strip()
        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()
