""" # 配置查看器
- 直接以类属性访问各个配置参数
- 配置不得修改
"""
import os
import sys
from pathlib import Path
import yaml
import copy
import logging

logger = logging.getLogger("config/config.py")


def _is_windows() -> bool:
    """当前是否 Windows 平台(跨平台分支的统一开关)"""
    return sys.platform == "win32"


def _default_config_dir() -> Path:
    """用户配置目录: 放 config.yaml / hotwords
    - Linux:   ~/.config/voice_toolkit      (沿用旧约定)
    - Windows: %APPDATA%\voice_toolkit      (Roaming, 随账号漫游)
    """
    if _is_windows():
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "voice_toolkit"
    return Path("~/.config/voice_toolkit").expanduser()


def _default_runtime_dir() -> Path:
    """运行时文件目录: 锁/结果/cmd/state 文件
    - Linux:   /tmp/transcriber             (沿用旧约定)
    - Windows: %LOCALAPPDATA%\voice_toolkit  (Local, 本机即可)
    注意: 与 default_config 的 lock_file/result_file 默认值联动,
    用户若在 config.yaml 显式写了这两个字段, 则以其为准。
    """
    if _is_windows():
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "voice_toolkit"
    return Path("/tmp/transcriber")


_xdg_config = _default_config_dir()
_yaml_path = _xdg_config / "config.yaml"
_xdg_config.mkdir(parents=True, exist_ok=True)
_RUNTIME_DIR = _default_runtime_dir()
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

class Config:      
    default_config = {
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "int16",
        "segment_seconds": 600,
        "lock_file": str(_RUNTIME_DIR / "live_transcriber.lock"),
        "result_file": str(_RUNTIME_DIR / "live_transcriber_result.json"),
        "models": {
            "paraformer_v1": {
                "dir": "~/.cache/modelscope/hub/models/iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch/",
                "vad_dir":"~/.cache/modelscope/hub/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                "punc_dir":"~/.cache/modelscope/hub/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                "params": {"ncpu": 2},
            },
            "paraformer_v2": {
                "dir": "~/.cache/modelscope/hub/models/iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch/",
                "vad_dir":"~/.cache/modelscope/hub/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                "punc_dir":"~/.cache/modelscope/hub/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                "params": {"ncpu": 2},
            },
            "qwen3_asr": {
                "dir": "~/models/qwen3-asr-gguf/",
                "params": {
                    "onnx_provider": "CPU",      # AMD 上 ONNX Encoder 走 CPU(计算量极小)
                    "llm_use_gpu": True,          # Decoder 走 llama.cpp Vulkan GPU
                    "enable_aligner": False,       # 暂不需要时间戳对齐
                    "n_ctx": 2048,                # 上下文 token 数(每秒音频约 20 token)
                    "chunk_size": 40.0,           # 每片段秒数
                    "memory_num": 1,              # 记忆片段数
                    "language": "Chinese",        # 识别语言
                    "context": "",                # 上下文增强提示(专业术语场景强烈建议填写)
                    "verbose": False,              # 引擎详细日志
                },
            },
        },
        "live":{
                "model": "paraformer_v1",
                "max_duration": 6000,
                "idle_timeout_sec": 3600,
                "output_mode": "window",
                "stream":True,
                "device": "auto"
                },
        "batch":{
            "model":"paraformer_v2",
            "stream":False,
            "device":"auto"
        },
        "window": {
            "popup_copy_delay": 200,
            "popup_fade_ms": 300,
        }
    }
    def __init__(self,mode:str="live"):
        """ # 配置查看器
        - 直接以类属性访问各个配置参数
        - 配置不得修改
        """
        self.config = copy.deepcopy(self.default_config)
        self.load()
        if mode in {"live","batch"}:
            self.mode= mode
        else:self.mode = "live"
    
    def load(self):
        if _yaml_path.exists():
            with open(_yaml_path, encoding="utf-8") as _f:
                _overrides = yaml.safe_load(_f)
            if isinstance(_overrides, dict):
                self._deep_merge(self.config, _overrides)

    def _deep_merge(self, base: dict, overrides: dict):
        """base作为overrides的字段补充(覆盖)
        merge:合并;
        overrides:over是在xx上,ride是行驶, 故为覆盖
        """
        for k, v in overrides.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            elif k in base and type(base[k]) != type(v):
                # _debug(f"类型不匹配：{k}={type(base[k])} vs {type(v)}，跳过")
                continue  # 或 raise
            else:
                base[k] = v

    def reload(self) -> bool: 
        """
        重新加载配置（热加载）
        用于配置更新时重新读取文件,
        成功返回True,失败使用旧配置并返回False
        """
        # 重置 CONFIG 为默认值
        self.config.clear()   # 清空为{}
        self.config.update(copy.deepcopy(self.default_config))
        # 重新加载 YAML
        if _yaml_path.exists():
            try:
                with open(_yaml_path, encoding="utf-8") as _f:
                    _overrides = yaml.safe_load(_f)
                if isinstance(_overrides, dict):
                    self._deep_merge(self.config, _overrides)
                return True
            except Exception as e:
                logger.error(f"Error reloading config: {e}")
                return False
        else:
            logger.error(f"热加载失败,{_yaml_path}未找到配置文件")
            return False
        
    # ==== 普通一级属性 =============
    @property
    def sample_rate(self) -> int :
        """采样率"""
        valid={8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000, 192000}
        if self.config["sample_rate"] in valid:
            return self.config["sample_rate"]
        else:return self.default_config["sample_rate"]
    @property
    def channels(self) -> int :
        """声道数"""
        valid={1, 2, 6, 8}
        if self.config["channels"] in valid:
            return self.config["channels"]
        else:return self.default_config["channels"]
    @property
    def dtype(self) -> str :
        """采样位深"""
        valid={"int16", "int24", "int32", "float32", "float64"}
        if self.config["dtype"] in valid:
            return self.config["dtype"]
        else:return self.default_config["dtype"]
    @property
    def segment_seconds(self) -> int :
        """分片秒数"""
        if type(self.config["segment_seconds"])==int and self.config["segment_seconds"]>0:
            return self.config["segment_seconds"]
        else:return self.default_config["segment_seconds"]
    
    @property
    def lock_file(self) -> Path :
        """锁文件路径"""
        if isinstance(self.config["lock_file"],str):
            lock_file = Path(self.config["lock_file"])
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            return lock_file
        else:return self.default_config["lock_file"]
    @property
    def result_file(self) -> Path :
        """转写结果暂存路径"""
        if isinstance(self.config["result_file"],str):
            result_file = Path(self.config["result_file"])
            result_file.parent.mkdir(parents= True, exist_ok= True)
            return Path(self.config["result_file"])
        else:return Path(self.default_config["result_file"])
    @property
    def ROOT(self) -> Path :
        """项目根目录（通过 config 位置自动定位）"""
        return Path(__file__).resolve().parent.parent
    @property
    def config_dir(self) -> Path:
        """用户配置目录(config.yaml / hotwords 所在): Linux ~/.config/voice_toolkit, Windows %APPDATA%\voice_toolkit"""
        return _xdg_config
    @property
    def cannel_cmd(self):
        """轻量级进程间通信(IPC)通道,传递命令"""
        return Path(str(self.lock_file)+"_cmd")
    @property
    def state_file(self) -> Path:
        """daemon 状态文件(idle/recording/transcribing), 供 toggle/前端判断应否等待结果"""
        return Path(str(self.lock_file)+"_state")
    # ==== 模型配置 =================
    @property
    def model(self) -> str :
        """模型名称"""
        if "model" in self.config[self.mode]:
            model=self.config[self.mode]["model"]
            if isinstance(model,str):
                return self.config[self.mode]["model"]
            else:
                logger.warning(f"model的名称不合法:{model}")
                raise ValueError(f"model的名称不合法:{model}")
        else:
            logger.error(f"{self.mode}的models里未配置必要的参数model!")
            raise ValueError(f"{self.mode}的models里未配置必要的参数model!")
    @property
    def model_dir(self) -> Path :
        """模型的父路径"""
        if "model" in self.config[self.mode]:
            model_dir = Path(self.config["models"][self.model]["dir"]).expanduser()
            if model_dir.exists():
                return model_dir
            else:
                logger.error(f"模型{model_dir}未找到")
                raise FileNotFoundError(f"模型{model_dir}未找到")
        else:
            logger.error(f"{self.mode}的models里未配置必要的参数model")
            raise ValueError(f"{self.mode}的models里未配置必要的参数model!")
    @property
    def model_params(self) -> dict | None :
        """模型的特调参数表,不存在返回None"""
        if "params" in self.config["models"][self.model]:
            return self.config["models"][self.model]["params"]
        else:
            logger.error(f"请检查当前的{self.mode}工作模式对应{self.model}模型里是否配置了特调参数表,未使用参数")
            return None
    @property
    def ncpu(self) -> int | None:
        """模型的cpu线程,如果上级参数表不存在或者,本参数不存在都返回None"""
        if self.model_params:
            if "ncpu" in self.model_params:
                ncpu = self.model_params["ncpu"]
                if ncpu in range(1,20):
                    return self.config["models"][self.model]["params"]["ncpu"]
                else:
                    logger.warning(f"当前model{self.model}的ncpu-模型的cpu线程配置内容不合法,当前使用{self.default_config["models"][self.model]["params"]["ncpu"]}")
                    return self.default_config["models"][self.model]["params"]["ncpu"]
    @property
    def vad_dir(self) -> Path :
        """vad模型的父路径"""
        vad_dir = Path(self.config["models"][self.model]["vad_dir"]).expanduser()
        if vad_dir.exists():
            return vad_dir
        else:
            logger.error(f"vad模型未找到:{vad_dir}")
            raise FileNotFoundError(f"vad模型未找到:{vad_dir}")
    @property
    def punc_dir(self) -> Path :
        """punc(标点)模型的父路径"""
        punc_dir = Path(self.config["models"][self.model]["punc_dir"]).expanduser()
        if punc_dir.exists():
            return punc_dir
        else:
            logger.error(f"标点model未找到:{punc_dir}")
            raise FileNotFoundError(f"标点model未找到:{punc_dir}")
    
    # ==== 均有的工作模式参数 ======================
    @property
    def is_stream(self) -> bool:
        """是否流式输出（根据当前模式读取 live/batch 下的 stream 字段）"""
        is_stream = self.config[self.mode].get("stream", False)
        if isinstance(is_stream,bool):
            return self.config[self.mode].get("stream", False)
        else:
            logger.warning(f"配置mode{self.mode}的stream字段未配置或配置错误,使用False")
            return False
    @property
    def device(self) -> str:
        """计算设备: auto 则自动检测, 也可手动指定 cuda/cpu"""
        device = self.config[self.mode].get("device", "auto")
        if device != "auto":
            if device in ("cuda", "cpu"):
                return device
            logger.warning(f"不支持的 device: {device}，回退自动检测")
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    # ==== live工作模式参数 =======================
    @property
    def max_duration(self) -> int | None:
        """live的最长录音秒数,非live返回None"""
        if "max_duration" in self.config[self.mode]:
            max_duration = self.config[self.mode]["max_duration"]
            if isinstance(max_duration,int) and max_duration>0:
                return self.config[self.mode]["max_duration"]
            else:
                logger.warning(f"配置的max_duration{max_duration} 有误,使用了")
                return self.default_config[self.mode]["max_duration"]
        return None
    @property
    def idle_timeout_sec(self) -> int | None :
        """live的空闲模型释放秒数(0=禁用）,非live返回None"""
        if "idle_timeout_sec" in self.config[self.mode]:
            idle_timeout_sec = self.config[self.mode]["idle_timeout_sec"]
            if isinstance(idle_timeout_sec,int) and idle_timeout_sec>=0:
                return self.config[self.mode]["idle_timeout_sec"]
            else:
                logger.warning(f"配置的idle_timeout_sec:{idle_timeout_sec}不合法,使用了默认值:{self.default_config[self.mode]["idle_timeout_sec"]}")
                return self.default_config[self.mode]["idle_timeout_sec"]
        return None
    # ==== batch工作模式参数 ======================
    # ==== 前端类型 ===============================
    @property
    def output_mode(self) -> str | None :
        """输出方式: notification | cursor | window | fcitx5 | None(无)"""
        if "output_mode" in self.config[self.mode]:
            if self.config[self.mode]["output_mode"] in {"notification","cursor","window","fcitx5"}:
                return self.config[self.mode]["output_mode"]
            else:
                logger.warning(f"配置的不合法前端形式为: {self.config[self.mode]["output_mode"]}")
                raise ValueError(f"配置的不合法前端形式为: {self.config[self.mode]["output_mode"]}")
        return None
    # ==== 窗口前端参数 =============================
    @property
    def window_popup_copy_delay(self) -> int :
        """窗口复制后停留多少**毫秒**，然后开始淡出"""
        if not self.output_mode == "window":
            logger.warning(f"警告 当前工作模式是{self.output_mode}, 仍然返回参数")
        if "popup_copy_delay" in self.config["window"] and self.config["window"]["popup_copy_delay"]>=0:
            return self.config["window"]["popup_copy_delay"]
        else:
            logger.warning(f"你的window对应的window_popup_copy_delay参数为空或者不合法,返回了200的默认值")
            return self.default_config["window"]["popup_copy_delay"]
    @property
    def window_popup_fade_ms(self) -> int :
        """窗口淡出动画持续时间--**毫秒**"""
        if not self.output_mode == "window":
            logger.warning(f"警告 当前工作模式是{self.output_mode}, 仍然返回参数")
            return self.config["window"]["popup_fade_ms"]
        if "popup_fade_ms" in self.config["window"] and self.config["window"]["popup_fade_ms"]>=0:
            return self.config["window"]["popup_fade_ms"]
        else:
            logger.warning(f"你的window对应的popup_fade_ms参数为空或者不合法,返回了300的默认值")
            return self.default_config["window"]["popup_fade_ms"]
CFG = Config()
