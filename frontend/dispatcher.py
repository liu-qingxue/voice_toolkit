import json
import logging
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
    if mode == "notification":
        notification.output(text)
    elif mode == "window" and show_window:
        show_window(text)
    elif mode in ("cursor", "fcitx5"):
        fcitx5.output(text)
