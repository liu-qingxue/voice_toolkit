import json
import logging
import sys
from pathlib import Path
from config import CFG
from frontend import fcitx5, notification

logger = logging.getLogger("frontend/dispatcher.py")


def dispatch(text: str, *, notify=None, show_window=None):
    logger.info(f"dispatch 被调用, text长度={len(text)}, mode={CFG.output_mode}")
    result_path = CFG.result_file
    result_path.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")

    if not text:
        return

    mode = CFG.output_mode
    if sys.platform == "win32" and mode in ("cursor", "fcitx5"):
        # Windows 无 fcitx5 插件: 光标注入由 windows 侧 run.ps1(SendInput) 负责,
        # 这里结果已落盘到 result 文件, 无需也不能用 fcitx5 写 /tmp/voxtype。
        logger.info("Windows: cursor/fcitx5 模式不注入, 交给 run.ps1 用 SendInput 上屏")
        return
    if mode == "notification":
        if sys.platform == "win32":
            # Windows 无 notify-send/wl-copy: 有回调(Qt 托盘)则用它弹气泡
            preview = text[:60].replace("\n", " ").strip()
            if notify:
                notify(preview)
            else:
                logger.info(f"Windows 无通知回调, 预览: {preview}")
            return
        notification.output(text)
    elif mode == "window" and show_window:
        show_window(text)
    elif mode in ("cursor", "fcitx5"):
        fcitx5.output(text)
