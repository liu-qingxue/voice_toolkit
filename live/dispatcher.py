import json
import logging
import time
from pathlib import Path
from config import CFG

logger = logging.getLogger("live/dispatcher.py")

def dispatch(text: str, *, notify=None, show_window=None):
    logger.info(f"dispatch 被调用, text长度={len(text)}, mode={CFG.output_mode}")
    result_path = CFG.result_file
    result_path.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")

    if not text:
        return

    mode = CFG.output_mode
    if mode == "notification" and notify:
        preview = text[:60].replace("\n", " ")
        notify(preview)
    elif mode == "window" and show_window:
        show_window(text)
    elif mode in ("cursor", "fcitx5"):
        Path("/tmp/voxtype").mkdir(parents=True, exist_ok=True)
        Path("/tmp/voxtype/result").write_text(text, encoding="utf-8")
        Path("/tmp/voxtype/commit").write_text(str(time.time()), encoding="utf-8")
