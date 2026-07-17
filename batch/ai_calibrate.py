#!/usr/bin/env python3
"""
AI 校准 - ASR 文本后处理优化
通过 Ollama 调用本地 LLM 对语音识别结果进行中文发音优化

用法:
  # 管道模式（糖的用法）
  cat result.txt | python batch/ai_calibrate.py

  # 文件模式
  python batch/ai_calibrate.py -i input.txt -o output.txt

  # 目录批量模式
  python batch/ai_calibrate.py -i ./results/ -o ./calibrated/

  # 指定模型和 Ollama 地址
  python batch/ai_calibrate.py -i input.txt -m qwen2.5:3b --host 192.168.1.100:11434
"""

import sys
import argparse
from pathlib import Path

import requests


SYSTEM_PROMPT = (
    "你是一个中文语音识别校准助手。"
    "你唯一要做的就是对我给你的文本逐句分析，这些文本都是语音识别的结果。"
    "结合中文发音规律和上下文理解，分析原本真实情景下发言人的意图，"
    "从而得出你认为发言人在当时情景下最有可能想要说的内容。"
    "直接输出校准后的文本，不要任何解释。"
)


_CHUNK_TARGET = 1500  # 每块目标字符数，自动分割不在句子中间切


class AICalibrator:
    """通过 Ollama 本地 LLM 对 ASR 文本进行中文发音优化校准"""

    def __init__(self, model: str = "qwen3:1.7b-q8_0",
                 host: str = "localhost:11434",
                 timeout: int = 0,
                 num_ctx: int = 16384):
        self.model = model
        self.api_url = f"http://{host}/api/chat"
        self.timeout = timeout
        self.num_ctx = num_ctx

    def calibrate(self, text: str) -> str:
        if not text.strip():
            return text

        if len(text) <= _CHUNK_TARGET:
            return self._call(text)

        chunks = self._smart_split(text)
        results = [self._call(c) for c in chunks]
        return "".join(results)

    @staticmethod
    def _smart_split(text: str) -> list[str]:
        """在句子边界附近智能分割，不依赖换行符"""
        if len(text) <= _CHUNK_TARGET:
            return [text]

        strong = set("。！？；\n")
        weak = set("，、；：")
        chunks = []
        start = 0
        n = len(text)

        while start < n:
            if n - start <= _CHUNK_TARGET:
                chunks.append(text[start:])
                break

            end = start + _CHUNK_TARGET
            if end >= n:
                chunks.append(text[start:])
                break

            # 在 target 位置附近找句子边界
            cut = -1
            for i in range(end, start - 1, -1):
                if i >= n:
                    continue
                ch = text[i]
                if ch in strong:
                    cut = i + 1
                    break
                elif ch in weak and cut == -1:
                    cut = i + 1

            if cut == -1 or cut <= start:
                cut = end  # 硬切

            # 切分点不能太短（至少 300 字）
            if cut - start < 300:
                cut = end

            chunks.append(text[start:cut])
            start = cut

        return chunks

    def _call(self, text: str) -> str:
        """单次调用 Ollama API，num_predict 根据输入长度动态算"""
        num_predict = max(2048, int(len(text) * 1.5))
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": self.num_ctx,
                "num_predict": num_predict,
            },
        }

        try:
            _timeout = None if self.timeout == 0 else self.timeout
            resp = requests.post(self.api_url, json=payload, timeout=_timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except requests.exceptions.ConnectionError:
            print(f"[错误] Ollama 连接失败: {self.api_url}", file=sys.stderr)
            return text
        except requests.exceptions.Timeout:
            print(f"[错误] Ollama 请求超时 ({self.timeout}s)", file=sys.stderr)
            return text
        except Exception as e:
            print(f"[错误] 校准失败: {e}", file=sys.stderr)
            return text


def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _report(original: str, calibrated: str, name: str = ""):
    """输出校准量化统计"""
    if original == calibrated:
        print(f"  {name} → 无变化", file=sys.stderr)
        return
    orig_len = len(original)
    calib_len = len(calibrated)
    diff_chars = sum(
        1 for a, b in zip(original, calibrated) if a != b
    ) + abs(orig_len - calib_len)
    pct = diff_chars / max(orig_len, 1) * 100
    print(f"  {name} → 改动 {diff_chars} 字 ({pct:.1f}%)  {orig_len}字 → {calib_len}字",
          file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="ASR 文本 AI 校准工具")
    parser.add_argument("-i", "--input", help="输入文件或目录（缺省读 stdin）")
    parser.add_argument("-o", "--output", help="输出文件或目录（缺省写 stdout）")
    parser.add_argument("-m", "--model", default="qwen3:1.7b-q8_0",
                        help="Ollama 模型名（默认 qwen3:1.7b-q8_0）")
    parser.add_argument("--host", default="localhost:11434",
                        help="Ollama 服务地址（默认 localhost:11434）")
    parser.add_argument("-t", "--timeout", type=int, default=0,
                        help="请求超时秒数（0=不超时，默认 0）")
    parser.add_argument("--num-ctx", type=int, default=16384,
                        help="上下文窗口大小（token 数，默认 16384）")
    parser.add_argument("-d", "--diff", action="store_true",
                        help="显示校准前后的文本差异")
    args = parser.parse_args()

    calibrator = AICalibrator(
        model=args.model, host=args.host, timeout=args.timeout,
        num_ctx=args.num_ctx,
    )

    # ── 目录批量模式 ──
    if args.input and Path(args.input).is_dir():
        in_dir = Path(args.input)
        out_dir = Path(args.output) if args.output else in_dir.parent / f"{in_dir.name}_calibrated"
        out_dir.mkdir(parents=True, exist_ok=True)

        txt_files = sorted(in_dir.glob("*.txt"))
        if not txt_files:
            print(f"在 {in_dir} 中未找到 .txt 文件", file=sys.stderr)
            sys.exit(1)

        for i, fp in enumerate(txt_files, 1):
            rel = fp.relative_to(in_dir)
            op = out_dir / rel.parent / f"{rel.stem}_calibrated.txt"
            op.parent.mkdir(parents=True, exist_ok=True)
            text = _read(fp)
            calibrated = calibrator.calibrate(text)
            _write(op, calibrated)
            if args.diff:
                print(f"[{i}/{len(txt_files)}] {fp.name} -> {op.name}", file=sys.stderr)
                _report(text, calibrated, fp.name)
            else:
                print(f"[{i}/{len(txt_files)}] {fp.name} -> {op.name}")

        print(f"完成: {len(txt_files)} 个文件已校准")
        return

    # ── 单文件模式 ──
    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"文件不存在: {in_path}", file=sys.stderr)
            sys.exit(1)
        text = _read(in_path)
        calibrated = calibrator.calibrate(text)
        if args.output:
            out_path = Path(args.output)
            _write(out_path, calibrated)
            print(f"写入 -> {out_path}")
        else:
            out_path = in_path.with_stem(f"{in_path.stem}_calibrated")
            _write(out_path, calibrated)
            print(f"写入 -> {out_path}")
        if args.diff:
            _report(text, calibrated, in_path.name)
        return

    # ── 管道模式（stdin → stdout） ──
    text = sys.stdin.read()
    calibrated = calibrator.calibrate(text)
    print(calibrated)
    if args.diff:
        _report(text, calibrated, "<stdin>")


if __name__ == "__main__":
    main()
