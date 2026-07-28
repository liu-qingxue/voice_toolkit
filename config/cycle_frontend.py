#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

CONFIG = Path.home() / ".config" / "voice_toolkit" / "config.yaml"
ORDER = ["notification", "window", "cursor"]

content = CONFIG.read_text(encoding="utf-8")

current = None
for m in ORDER:
    if f"output_mode: {m}" in content:
        current = m
        break

if current is None:
    print("未找到 output_mode", file=sys.stderr)
    sys.exit(1)

next_mode = ORDER[(ORDER.index(current) + 1) % len(ORDER)]
content = content.replace(f"output_mode: {current}", f"output_mode: {next_mode}")
CONFIG.write_text(content, encoding="utf-8")

subprocess.run(["notify-send", "前端切换", f"{current} → {next_mode}"])
