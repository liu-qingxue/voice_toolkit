import shutil
from pathlib import Path
from datetime import date, timedelta
from core.config import CONFIG
from voice_assistant.meta_db import MetaDB


class CleanupManager:
    def __init__(self, meta: MetaDB):
        self.meta = meta
        self.raw_dir = Path(CONFIG["raw_dir"])
        self.transcripts_dir = Path(CONFIG["transcripts_dir"])
        self.core_dir = Path(CONFIG["core_dir"])
        self.retention = CONFIG["retention_days"]

    def scan_and_clean(self):
        expirable = self.meta.expirable_dates(self.retention)
        for d in expirable:
            self._clean_date(d)

    def preserve(self, d: date, filenames: list[str]):
        date_str = d.isoformat()
        src_raw = self.raw_dir / date_str
        dst_core = self.core_dir / date_str
        dst_core.mkdir(parents=True, exist_ok=True)
        preserved = []
        for fname in filenames:
            src = src_raw / fname
            if src.exists():
                shutil.copy2(src, dst_core / fname)
                preserved.append(fname)
        if preserved:
            self.meta.mark_preserved(d, preserved)
            print(f"[cleanup] preserved {len(preserved)} files from {date_str}")

    def _clean_date(self, d: date):
        date_str = d.isoformat()
        raw_dir = self.raw_dir / date_str
        trans_dir = self.transcripts_dir / date_str
        core_dir = self.core_dir / date_str

        if core_dir.exists():
            for f in raw_dir.glob("*.wav"):
                if not (core_dir / f.name).exists():
                    f.unlink()
        else:
            if raw_dir.exists():
                shutil.rmtree(raw_dir)
        if trans_dir.exists():
            shutil.rmtree(trans_dir)
        self.meta.mark_cleaned(d)
        print(f"[cleanup] cleaned {date_str}")
