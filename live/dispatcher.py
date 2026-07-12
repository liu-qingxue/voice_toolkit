import json
from pathlib import Path
from config.config import CFG


def dispatch(text: str, *, notify=None, show_window=None):
    """非流式输出分发。

    始终写入结果文件，有文本时再触发前端回调。

    Args:
        text: 转录文本
        notify: 通知回调（notification 模式）
        show_window: 弹窗回调（window 模式）
    """
    result_path = Path(CFG.result_file)
    result_path.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")

    if not text:
        return

    mode = CFG.output_mode
    if mode == "notification" and notify:
        preview = text[:60].replace("\n", " ")
        notify(preview)
    elif mode == "window" and show_window:
        show_window(text)
    elif mode == "cursor":
        pass
