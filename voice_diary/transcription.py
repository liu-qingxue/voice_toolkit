from pathlib import Path
from datetime import date
from core.transcriber import Transcriber
from core.model_factory import create_transcriber
from core.config import CONFIG


_DIARY_MODEL: Transcriber | None = None


def _get_model() -> Transcriber:
    global _DIARY_MODEL
    if _DIARY_MODEL is None:
        _DIARY_MODEL = create_transcriber("v2")
    return _DIARY_MODEL


class DiaryTranscriber:
    def __init__(self, transcriber: Transcriber | None = None):
        self._engine = transcriber or _get_model()
        self.transcripts_dir = Path(CONFIG["transcripts_dir"])

    def transcribe_day(self, d: date) -> str:
        raw_dir = Path(CONFIG["raw_dir"]) / d.isoformat()
        if not raw_dir.exists():
            return ""
        wav_files = sorted(raw_dir.glob("*.wav"))
        if not wav_files:
            return ""

        segments = []
        for wav_path in wav_files:
            text = self._transcribe_file(wav_path)
            ts = wav_path.stem.replace("_", ":")
            segments.append(f"[{ts}] {text}")

        result = "\n".join(segments)
        out_dir = self.transcripts_dir / d.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "diary.txt"
        out_file.write_text(result, encoding="utf-8")
        return result

    def _transcribe_file(self, wav_path: Path) -> str:
        return self._engine.transcribe_file(wav_path)

    def set_engine(self, engine: Transcriber):
        self._engine = engine
