import logging
import os
import sys
import numpy as np
from config import Config
from core.transcribe_base import TranscribeBase
from pathlib import Path
from core.audio import load_wav

# 注意: funasr/torch 已懒加载(见 ParaformerTranscriber.load),
# 避免 qwen3_asr 模式启动时被迫 import 重依赖(torch 约 3~10s)


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

        # 懒加载: 只有 paraformer 模式才 import torch/funasr(约 3~10s)
        from funasr import AutoModel
        
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


# Qwen3-ASR-GGUF 后端仓库的绝对路径(保持 ~/Public 独立, git 可更新)
QWEN_BACKEND = Path.home() / "Public" / "Qwen3-ASR-GGUF"

def _ensure_qwen_backend_importable():
    """把 Qwen3-ASR-GGUF 后端仓库加进 sys.path, 使 qwen_asr_gguf 包可导入"""
    if str(QWEN_BACKEND) not in sys.path:
        sys.path.insert(0, str(QWEN_BACKEND))


def _resample_to_16k(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """把任意采样率音频重采样到 16kHz(Qwen3-ASR 引擎固定 16k)"""
    if sample_rate == 16000:
        return audio
    from scipy.signal import resample_poly
    g = np.gcd(sample_rate, 16000)
    up, down = 16000 // g, sample_rate // g
    return resample_poly(audio, up, down).astype(np.float32)


class QwenTranscriber(TranscribeBase):
    """ # Qwen3-ASR GGUF 引擎
    - 混合推理: ONNX Encoder(CPU) + llama.cpp GGUF Decoder(Vulkan GPU)
    - 依赖 ~/Public/Qwen3-ASR-GGUF 独立后端仓库
    - 精度远超 Paraformer(纯净 CER 0.56% vs 7.68%), RTF 0.04 远超实时
    """
    def __init__(self, mode: str = "live", model_name: str | None = None):
        CFG = Config(mode)
        # 显式指定模型名(工厂传入), 不依赖当前配置的 model 字段,
        # 这样测试/多模型切换时 model_dir 永远指向正确的模型目录
        self.model_name = model_name or CFG.model
        model_cfg = CFG.config["models"][self.model_name]
        self.model_dir = Path(model_cfg["dir"]).expanduser()
        self.params = model_cfg.get("params") or {}
        self.config_dir = CFG.config_dir   # ~/.config/voice_toolkit/ 下放 hotwords
        self._context: str | None = None   # 缓存, None=未加载
        self._engine = None

    @property
    def is_loaded(self) -> bool:
        return self._engine is not None

    def load(self):
        """已加载则返回; 创建 QwenASREngine(ONNX Encoder + Vulkan Decoder)"""
        if self._engine is not None:
            return

        _ensure_qwen_backend_importable()
        try:
            from qwen_asr_gguf.inference import QwenASREngine, ASREngineConfig
        except ImportError as e:
            raise RuntimeError(f"Qwen3-ASR-GGUF 后端导入失败(检查 {QWEN_BACKEND}): {e}") from e

        config = ASREngineConfig(
            model_dir=str(self.model_dir),
            onnx_provider=self.params.get("onnx_provider", "CPU"),
            llm_use_gpu=self.params.get("llm_use_gpu", True),
            encoder_frontend_fn="qwen3_asr_encoder_frontend.int4.onnx",
            encoder_backend_fn="qwen3_asr_encoder_backend.int4.onnx",
            llm_fn="qwen3_asr_llm.q4_k.gguf",
            n_ctx=self.params.get("n_ctx", 2048),
            chunk_size=self.params.get("chunk_size", 40.0),
            memory_num=self.params.get("memory_num", 1),
            enable_aligner=self.params.get("enable_aligner", False),
            verbose=self.params.get("verbose", False),
        )
        try:
            self._engine = QwenASREngine(config=config)
            logger.info("Qwen3-ASR 引擎加载成功")
        except Exception as e:
            raise RuntimeError(f"Qwen3-ASR 引擎加载失败: {e}") from e

    def unload(self):
        if self._engine is not None:
            try:
                self._engine.shutdown()
            except Exception as e:
                logger.error(f"Qwen3-ASR 引擎关闭异常: {e}")
            self._engine = None

    def _load_context(self) -> str:
        """从 hotwords 目录读取上下文增强提示
        - 配置 context 填文件名, 如: context: firefighting.txt
        - 空/0/false/null 等 falsy 值 = 关闭, 不触发文件 IO
        - 读取结果缓存, 只读一次
        """
        if self._context is not None:
            return self._context

        ctx = self.params.get("context")
        if not ctx:   # 空/0/false/None 统一视为关闭
            self._context = ""
            return ""

        fp = self.config_dir / "hotwords" / str(ctx).strip()
        if not fp.exists():
            logger.warning(f"hotwords 文件不存在: {fp}, 上下文增强已关闭")
            self._context = ""
            return ""
        try:
            self._context = fp.read_text(encoding="utf-8").strip()
            logger.info(f"hotwords 已加载: {fp} ({len(self._context)} 字)")
        except Exception as e:
            logger.error(f"hotwords 读取失败: {fp}: {e}")
            self._context = ""
        return self._context

    def transcribe(self, audio: np.ndarray | Path | str, sample_rate: int = 16000) -> str:
        """### audio 无论是路径还是数组都可返回 *转录*后的,*处理*好的str
        - Qwen3-ASR 引擎固定 16kHz, 非 16k 输入会自动重采样
        """
        # 1. 路径 → 数组
        if isinstance(audio, (str, Path)):
            audio, sample_rate = load_wav(audio)

        # 2. 数组预处理
        if len(audio) == 0:
            return ""
        if audio.ndim > 1:
            audio = audio.squeeze()

        # 3. 保证引擎已加载
        if self._engine is None:
            try:
                self.load()
            except Exception as e:
                logger.error(f"[Qwen3-ASR] 模型加载失败: {e}", exc_info=True)
                return "[模型加载错误]"

        # 4. 重采样到 16k
        audio = _resample_to_16k(audio, sample_rate)

        # 5. 推理(显式传 context/language, 走 numpy 数组接口避开上游 duration bug)
        try:
            result = self._engine.asr(
                audio=audio,
                context=self._load_context(),
                language=self.params.get("language", "Chinese"),
                chunk_size_sec=self.params.get("chunk_size", 40.0),
                memory_chunks=self.params.get("memory_num", 1),
            )
            text = (result.text or "").strip()
            logger.info(f"Qwen3-ASR 推理完成, 文本长度: {len(text)}")
            return text
        except Exception as e:
            logger.error(f"[Qwen3-ASR] 推理失败: {e}", exc_info=True)
            return "[推理失败]"

