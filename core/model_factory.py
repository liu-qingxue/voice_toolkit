"""
转录器工厂
根据配置动态创建合适的转录器实例
"""

from typing import Literal
from core.transcribe_base import TranscribeBase
from core.models import ParaformerV1Transcriber, ParaformerV2Transcriber


def create_transcriber(
    model_type: Literal["v1", "v2", "live", "diary"] | None = None,
    **kwargs
) -> TranscribeBase:
    """
    工厂函数：创建转录器实例
    
    Args:
        model_type: 模型类型
            - "v1" 或 "live": ParaformerV1 (清晰语音，实时场景)
            - "v2" 或 "diary": ParaformerV2 (降质语音，日志场景)
            - None: 根据 CONFIG 自动选择（默认使用 diary）
        **kwargs: 传递给转录器的参数 (ncpu, model_dir, ...)
    
    Returns:
        Transcriber 实例
    
    Examples:
        >>> # 创建 V1 转录器（清晰语音）
        >>> transcriber = create_transcriber("v1", ncpu=4)
        
        >>> # 创建 V2 转录器（降质语音）
        >>> transcriber = create_transcriber("diary")
        
        >>> # 自动选择（根据配置）
        >>> transcriber = create_transcriber()
    """
    
    # 规范化别名
    if model_type in ("live",):
        model_type = "v1"
    elif model_type in ("diary",):
        model_type = "v2"
    
    if model_type == "v1":
        return ParaformerV1Transcriber(**kwargs)
    elif model_type == "v2":
        return ParaformerV2Transcriber(**kwargs)
    elif model_type is None:
        # 默认使用 V2（日志场景）
        return ParaformerV2Transcriber(**kwargs)
    else:
        raise ValueError(f"未知的转录器类型: {model_type}")


def get_default_transcriber(use_v1: bool = False, **kwargs) -> TranscribeBase:
    """
    获取默认转录器
    
    Args:
        use_v1: 是否使用 V1（清晰语音），默认 False 使用 V2
        **kwargs: 传递给转录器的参数
    
    Returns:
        Transcriber 实例
    """
    model_type = "v1" if use_v1 else "v2"
    return create_transcriber(model_type, **kwargs)
