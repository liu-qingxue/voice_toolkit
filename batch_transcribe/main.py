#!/usr/bin/env python3
"""批量转录 — 菜单交互版"""

import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_factory import create_transcriber

AUDIO_EXTENSIONS = {".wav", ".m4a"}
MODEL_LABELS = {
    "v1": "V1 (SeACo-Paraformer, 热词增强)",
    "v2": "V2 (Paraformer VAD+Punc, 标点恢复)",
}


class State:
    def __init__(self):
        self.model_type = "v2"
        self.audio_dir: Path | None = None
        self.all_scanned: list[Path] = []
        self.selected_ids: set[int] = set()
        self.output_dir: Path | None = None


def clear():
    print("\033[2J\033[H", end="")


def divider(char: str = "=", width: int = 56):
    print(char * width)


def selected_files(state: State) -> list[Path]:
    return [state.all_scanned[i] for i in sorted(state.selected_ids)]


def input_yn(prompt: str) -> bool:
    c = input(prompt).strip().lower()
    return c in ("", "y", "yes")


# ============================================================
# 二级面板
# ============================================================

def panel_model(state: State):
    clear()
    print("--- 选择模型 ---\n")
    for key, label in MODEL_LABELS.items():
        mark = " ←" if key == state.model_type else ""
        num = "1" if key == "v1" else "2"
        print(f"  [{num}] {label}{mark}")
    print()
    while True:
        c = input("> ").strip()
        if c == "1":
            state.model_type = "v1"
            return
        if c == "2":
            state.model_type = "v2"
            return
        print("  请输入 1 或 2")


def panel_audio(state: State):
    clear()
    print("--- 选择音频 ---")
    if state.audio_dir:
        print(f"  当前目录: {state.audio_dir}")
    print()

    p = input("输入音频目录 (回车保持) > ").strip()
    if p:
        path = Path(p).expanduser()
        if not path.is_dir():
            print(f"\n  路径不存在或不是目录: {path}")
            input("按回车返回...")
            return
        state.audio_dir = path.resolve()
        state.all_scanned = scan_audio(state.audio_dir)
        state.selected_ids.clear()

    if state.audio_dir is None:
        print("  尚未设置音频目录")
        input("按回车返回...")
        return

    _select_files(state)


def scan_audio(audio_dir: Path) -> list[Path]:
    files: list[Path] = []
    for ext in sorted(AUDIO_EXTENSIONS):
        files.extend(sorted(audio_dir.glob(f"*{ext}")))
    return sorted(files)


def _select_files(state: State):
    files = state.all_scanned
    while True:
        clear()
        wav = sum(1 for f in files if f.suffix.lower() == ".wav")
        m4a = sum(1 for f in files if f.suffix.lower() == ".m4a")
        print("--- 选择文件 ---")
        print(f"  扫描: .wav: {wav}, .m4a: {m4a}, 共 {len(files)} 个")
        print()

        n_digits = len(str(len(files)))
        for i, f in enumerate(files):
            mark = "✓" if i in state.selected_ids else " "
            print(f"  [{mark}] {i + 1:>{n_digits}}. {f.name}")

        print("\n  数字=切换 | A=全选 | D=全不选 | Enter=确认")
        c = input("> ").strip().lower()

        if c == "":
            return
        elif c == "a":
            state.selected_ids = set(range(len(files)))
        elif c == "d":
            state.selected_ids.clear()
        else:
            try:
                idx = int(c) - 1
                if 0 <= idx < len(files):
                    if idx in state.selected_ids:
                        state.selected_ids.discard(idx)
                    else:
                        state.selected_ids.add(idx)
            except ValueError:
                pass


def panel_output(state: State):
    clear()
    print("--- 输出目录 ---")
    if state.output_dir:
        print(f"  当前: {state.output_dir}")
    print()

    p = input("输入输出目录 (回车保持) > ").strip()
    if p:
        path = Path(p).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        state.output_dir = path.resolve()


def panel_transcribe(state: State):
    files = selected_files(state)

    if not files or state.output_dir is None:
        clear()
        print("--- 开始转录 ---\n")
        if not files:
            print("  请先在 [2] 选择音频文件。")
        if state.output_dir is None:
            print("  请先在 [3] 设置输出目录。")
        input("\n按回车返回...")
        return

    clear()
    divider()
    print(f"  确认开始转录")
    divider()
    print(f"  模型: {MODEL_LABELS[state.model_type]}")
    print(f"  文件: {len(files)} 个")
    print(f"  输出: {state.output_dir}")
    divider()

    if not input_yn("\n确认开始? [Y/n] > "):
        return

    # — 执行 —
    clear()
    print("加载模型中...")
    transcriber = create_transcriber(state.model_type)
    print("模型已就绪。\n")
    divider()

    total = len(files)
    n_digits = len(str(total))
    ok = 0
    fail = 0

    for i, audio_file in enumerate(files, 1):
        prefix = f"[{i:>{n_digits}}/{total}] {audio_file.name}"
        try:
            out_path = _resolve_output(state.output_dir, audio_file)
            if audio_file.suffix.lower() == ".wav":
                text = transcriber.transcribe_file(audio_file)
            elif audio_file.suffix.lower() == ".m4a":
                audio_np, sr = _decode_m4a(audio_file)
                text = transcriber.transcribe(audio_np, sr)
            else:
                raise RuntimeError(f"不支持的格式: {audio_file.suffix}")

            out_path.write_text(text, encoding="utf-8")
            ok += 1
            print(f"{prefix} ... ✓")
        except Exception as e:
            fail += 1
            print(f"{prefix} ... ✗ {str(e)}")

    print()
    divider()
    report = f"  完成: {ok}/{total} 成功"
    if fail:
        report += f" | {fail} 失败"
    print(report)
    print(f"  输出: {state.output_dir}")
    divider()


def _resolve_output(output_dir: Path, audio_file: Path) -> Path:
    base = output_dir / audio_file.name
    out = base.with_suffix(".txt")
    i = 1
    while out.exists():
        out = output_dir / f"{base.stem}_{i}.txt"
        i += 1
    return out


def _decode_m4a(path: Path) -> tuple[np.ndarray, int]:
    proc = subprocess.run(
        [
            "ffmpeg", "-i", str(path),
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            "-loglevel", "error",
            "-",
        ],
        capture_output=True,
        timeout=300,
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode(errors="replace").strip() or "ffmpeg 返回非零"
        raise RuntimeError(f"ffmpeg 解码失败: {msg}")
    pcm = np.frombuffer(proc.stdout, dtype=np.int16)
    if len(pcm) == 0:
        raise RuntimeError("ffmpeg 输出为空")
    return pcm.astype(np.float32) / 32768.0, 16000


# ============================================================
# 一级面板
# ============================================================

def print_status(state: State):
    divider()
    print("  批量转录")
    divider()

    label = MODEL_LABELS[state.model_type]
    print(f"  模型: {label}")

    if state.audio_dir:
        n_selected = len(state.selected_ids)
        n_total = len(state.all_scanned)
        print(f"  音频: {state.audio_dir}  ({n_total} 个文件, 已选 {n_selected})")
    else:
        print("  音频: (未设置)")

    if state.output_dir:
        print(f"  输出: {state.output_dir}")
    else:
        print("  输出: (未设置)")

    divider("─")
    print("  [1] 选择模型")
    print("  [2] 选择音频")
    print("  [3] 选择输出目录")
    print("  [4] 开始转录")
    print("  [0] 退出")
    divider("─")


def main():
    state = State()

    while True:
        clear()
        print_status(state)
        c = input("\n> ").strip()

        if c == "1":
            panel_model(state)
        elif c == "2":
            panel_audio(state)
        elif c == "3":
            panel_output(state)
        elif c == "4":
            panel_transcribe(state)
            return
        elif c == "0":
            clear()
            print("  已退出。")
            return


if __name__ == "__main__":
    main()
