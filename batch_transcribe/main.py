#!/usr/bin/env python3
"""批量转录 — 终端交互版"""

import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_factory import create_transcriber

AUDIO_EXTENSIONS = {".wav", ".m4a"}
BANNER_WIDTH = 60


def input_choice(prompt: str, accepted: set[str], error_msg: str) -> str:
    while True:
        c = input(prompt).strip()
        if c in accepted:
            return c
        print(f"  {error_msg}")


def input_dir(label: str) -> Path:
    while True:
        p = Path(input(f"\n{label} > ").strip()).expanduser()
        if p.is_dir():
            return p.resolve()
        print(f"  路径不存在或不是目录: {p}")


def input_output_dir(label: str) -> Path:
    p = Path(input(f"\n{label} > ").strip()).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def scan_audio(audio_dir: Path) -> list[Path]:
    files: list[Path] = []
    for ext in sorted(AUDIO_EXTENSIONS):
        files.extend(sorted(audio_dir.glob(f"*{ext}")))
    return sorted(files)


def confirm(audio_dir: Path, total: int, output_dir: Path, model_label: str) -> bool:
    print("\n" + "=" * BANNER_WIDTH)
    print(f"  模型: {model_label}")
    print(f"  音频: {audio_dir}  ({total} 个文件)")
    print(f"  输出: {output_dir}")
    print("=" * BANNER_WIDTH)
    while True:
        c = input("\n确认开始? [Y/n] > ").strip().lower()
        if c in ("", "y", "yes"):
            return True
        if c in ("n", "no"):
            return False


def decode_m4a(path: Path) -> tuple[np.ndarray, int]:
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


def process_one(audio_file: Path, output_dir: Path, transcriber) -> tuple[str, str | None]:
    out_path = output_dir / audio_file.with_suffix(".txt").name

    if out_path.exists():
        return "skipped", None

    ext = audio_file.suffix.lower()

    if ext == ".wav":
        try:
            text = transcriber.transcribe_file(audio_file)
        except Exception as e:
            return "failed", str(e)

    elif ext == ".m4a":
        try:
            audio_np, sr = decode_m4a(audio_file)
            text = transcriber.transcribe(audio_np, sr)
        except Exception as e:
            return "failed", str(e)

    else:
        return "failed", f"不支持的格式: {ext}"

    try:
        out_path.write_text(text, encoding="utf-8")
    except Exception as e:
        return "failed", f"保存失败: {e}"

    return "success", None


def main():
    print("\n" + "=" * BANNER_WIDTH)
    print("  批量转录")
    print("=" * BANNER_WIDTH)

    # — 选模型 —
    print("\n模型选择:")
    print("  [1] V1 - SeACo-Paraformer (热词增强)")
    print("  [2] V2 - Paraformer VAD+Punc (标点恢复, 抗噪)")
    model_type = input_choice("\n> ", {"1", "2"}, "请输入 1 或 2")
    model_type = "v1" if model_type == "1" else "v2"

    MODEL_LABELS = {
        "v1": "V1 (SeACo-Paraformer, 热词增强)",
        "v2": "V2 (Paraformer VAD+Punc, 标点恢复)",
    }
    model_label = MODEL_LABELS[model_type]

    # — 输路径 —
    audio_dir = input_dir("音频目录")
    output_dir = input_output_dir("输出目录")

    # — 扫描 —
    files = scan_audio(audio_dir)
    if not files:
        print(f"\n  未找到音频文件 ({', '.join(sorted(AUDIO_EXTENSIONS))})")
        return

    wav_count = sum(1 for f in files if f.suffix.lower() == ".wav")
    m4a_count = sum(1 for f in files if f.suffix.lower() == ".m4a")
    parts = []
    if wav_count:
        parts.append(f".wav: {wav_count}")
    if m4a_count:
        parts.append(f".m4a: {m4a_count}")
    print(f"\n  扫描到 {len(files)} 个文件 ({', '.join(parts)})")

    # — 确认 —
    if not confirm(audio_dir, len(files), output_dir, model_label):
        print("  已取消。")
        return

    # — 加载模型 —
    print("\n加载模型中...")
    transcriber = create_transcriber(model_type)
    print("模型已就绪。\n")
    print("=" * BANNER_WIDTH)

    # — 处理 —
    total = len(files)
    n_digits = len(str(total))
    results = {"success": 0, "failed": 0, "skipped": 0}
    errors: list[str] = []

    for i, audio_file in enumerate(files, 1):
        status, error_msg = process_one(audio_file, output_dir, transcriber)

        prefix = f"[{i:>{n_digits}}/{total}] {audio_file.name}"
        if status == "success":
            results["success"] += 1
            print(f"{prefix} ... ✓")
        elif status == "skipped":
            results["skipped"] += 1
            print(f"{prefix} ... 跳过 (输出已存在)")
        else:
            results["failed"] += 1
            print(f"{prefix} ... ✗ {error_msg}")
            errors.append(f"{audio_file.name}: {error_msg}")

    # — 错误日志 —
    error_log_path = output_dir / "_errors.log"
    if errors:
        error_log_path.write_text("\n".join(errors), encoding="utf-8")
    elif error_log_path.exists():
        error_log_path.unlink()

    # — 报告 —
    print("\n" + "=" * BANNER_WIDTH)
    report = [f"完成: {results['success']}/{total} 成功"]
    if results["failed"]:
        report.append(f"       {results['failed']} 失败")
    if results["skipped"]:
        report.append(f"       {results['skipped']} 跳过")
    report.append(f"输出: {output_dir}")
    if errors:
        report.append(f"错误日志: {error_log_path}")
    print("\n".join(f"  {line}" for line in report))
    print("=" * BANNER_WIDTH)


if __name__ == "__main__":
    main()
