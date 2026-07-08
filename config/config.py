from pathlib import Path
import yaml
import copy

_yaml_path = Path(__file__).resolve().parent / "config.yaml"
class Config:
    default_config = {
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "int16",
        "segment_seconds": 600,
        "lock_file": "/tmp/live_transcriber.lock",
        "result_file": "/tmp/live_transcriber_result.json",
        "models": {
            "paraformer_v1": {
                "dir": "~/.cache/modelscope/hub/models/iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch/",
                "params": {"ncpu": 2},
            },
            "paraformer_v2": {
                "dir": "~/.cache/modelscope/hub/models/iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch/",
                "params": {"ncpu": 2},
            },
        },
        "mode": "live",
        "live":{
                "model": "paraformer_v1",
                "max_duration": 6000,
                "idle_timeout_sec": 3600,
                "output_mode": "window"
                },
        "window": {
            "popup_copy_delay": 200,
            "popup_fade_ms": 300,
        }
    }
    def __init__(self):
        self.config = copy.deepcopy(self.default_config)
        self.load()
    
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
                print(f"Error reloading config: {e}")
                return False
        else:
            print(f"热加载失败,{_yaml_path}未找到配置文件")
            return False
        
    # ==== 普通一级属性 =============
    @property
    def sample_rate(self) -> int :
        """采样率"""
        return self.config["sample_rate"]
    @property
    def channels(self) -> int :
        """声道数"""
        return self.config["channels"]
    @property
    def dtype(self) -> str :
        """采样位深"""
        return self.config["dtype"]
    @property
    def segment_seconds(self) -> int :
        """分片秒数"""
        return self.config["segment_seconds"]
    @property
    def lock_file(self) -> str :
        """锁文件路径, .lock结尾"""
        return self.config["lock_file"]
    @property
    def result_file(self) -> str :
        """转写结果暂存路径, .json结尾"""
        return self.config["result_file"]
    # ==== 工作模式 ============
    @property
    def mode(self) -> str :
        """工作模式"""
        return self.config["mode"]
    # ==== 模型配置 =================
    @property
    def model(self) -> str :
        """模型名称"""
        return self.config[self.mode]["model"]
    @property
    def model_dir(self) ->str :
        """模型的父路径,以 ~ 开头,以 / 结束!"""
        return self.config["models"][self.model]["dir"]
    @property
    def ncpu(self) -> int :
        """模型的cpu线程"""
        return self.config["models"][self.model]["params"]["ncpu"]
    
    # ==== 工作模式共有参数 =======================
    @property
    def max_duration(self) -> int :
        """最长录音秒数"""
        return self.config[self.mode]["max_duration"]
    @property
    def idle_timeout_sec(self) -> int :
        """空闲模型释放秒数(0=禁用）"""
        return self.config[self.mode]["idle_timeout_sec"]
    
    # ==== 前端类型 ===============================
    @property
    def output_mode(self) -> str :
        """输出方式: notification | cursor | window"""
        return self.config[self.mode]["output_mode"]
    # ==== 窗口前端参数 =============================
    @property
    def window_popup_copy_delay(self) -> int :
        """窗口复制后停留多少**毫秒**，然后开始淡出"""
        if not self.output_mode == "window":
            print(f"警告 当前工作模式是{self.output_mode}, 仍然返回参数")
        return self.config["window"]["popup_copy_delay"]

    @property
    def window_popup_fade_ms(self) -> int :
        """窗口淡出动画持续时间--**毫秒**"""
        if not self.output_mode == "window":
            print(f"警告 当前工作模式是{self.output_mode}, 仍然返回参数")
        return self.config["window"]["popup_fade_ms"]
            
        