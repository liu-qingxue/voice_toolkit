from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

def _deep_merge(base: dict, overrides: dict):
    for k, v in overrides.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


CONFIG = {
    "sample_rate": 16000,
    "channels": 1,
    "dtype": "int16",
    "segment_seconds": 600,
    "model": {
        "dir": None,
        "live": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "diary": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "ncpu": 2,
    },
    "live": {
        "lock_file": "/tmp/live_transcriber.lock",
        "result_file": "/tmp/live_transcriber_result.json",
        "max_duration": 60,
        "idle_timeout_sec": 3600,
        "output_mode": "notification",
        "popup_copy_delay": 400,
        "popup_fade_ms": 300,
    },
}

_yaml_path = Path(__file__).resolve().parent.parent / "config.yaml"
if yaml and _yaml_path.exists():
    with open(_yaml_path, encoding="utf-8") as _f:
        _overrides = yaml.safe_load(_f)
    if isinstance(_overrides, dict):
        _deep_merge(CONFIG, _overrides)


def reload():
    """
    重新加载配置（热加载）
    用于配置更新时重新读取文件
    """
    global CONFIG
    
    # 重置 CONFIG 为默认值
    CONFIG.clear()
    CONFIG.update({
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "int16",
        "segment_seconds": 600,
        "model": {
            "dir": None,
            "live": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            "diary": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            "ncpu": 2,
        },
        "live": {
            "lock_file": "/tmp/live_transcriber.lock",
            "result_file": "/tmp/live_transcriber_result.json",
            "max_duration": 60,
            "idle_timeout_sec": 3600,
            "output_mode": "notification",
            "popup_copy_delay": 400,
            "popup_fade_ms": 300,
        },
    })
    
    # 重新加载 YAML
    if yaml and _yaml_path.exists():
        try:
            with open(_yaml_path, encoding="utf-8") as _f:
                _overrides = yaml.safe_load(_f)
            if isinstance(_overrides, dict):
                _deep_merge(CONFIG, _overrides)
            return True
        except Exception as e:
            print(f"Error reloading config: {e}")
            return False
    
    return True
