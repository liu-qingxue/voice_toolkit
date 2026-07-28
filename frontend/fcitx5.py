import time
from pathlib import Path

def output(text: str):
    dst = Path("/tmp/voxtype")
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "result").write_text(text, encoding="utf-8")
    (dst / "commit").write_text(str(time.time()), encoding="utf-8")
