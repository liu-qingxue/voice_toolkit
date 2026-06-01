import subprocess
from pathlib import Path
from datetime import date, datetime, timedelta
from voice_diary.meta_db import MetaDB
from voice_diary.fetcher import Fetcher
from voice_diary.transcription import DiaryTranscriber
from voice_diary.cleanup import CleanupManager
from voice_diary.notifier import Notifier
from core.config import CONFIG


class DiaryScheduler:
    def __init__(self, host: str = "192.168.43.1", port: int = 8765):
        self.host = host
        self.port = port
        self.meta = MetaDB()
        self.fetcher = Fetcher(host, port)
        self.transcriber = DiaryTranscriber()
        self.cleanup = CleanupManager(self.meta)
        self.notifier = Notifier()

    def run_once(self):
        today = date.today()
        yesterday = today - timedelta(days=1)

        if not self._check_wifi():
            msg = f"{yesterday} 日志传输失败：未连接到手机热点"
            self.meta.mark_error(yesterday, "wifi_not_connected")
            self.notifier.send("语音日志传输失败", msg)
            return

        downloaded = self.fetcher.fetch(yesterday)
        if downloaded:
            self.meta.mark_transmitted(yesterday, [f.name for f in downloaded])
        else:
            if not self.meta.is_transmitted(yesterday):
                msg = f"{yesterday} 无文件可拉取，或全部拉取失败"
                self.meta.mark_error(yesterday, "no_files")
                self.notifier.send("语音日志拉取警告", msg)

        pending = self.meta.pending_transcription()
        for d in pending:
            try:
                self.transcriber.transcribe_day(d)
                self.meta.mark_transcribed(d)
                print(f"[scheduler] transcribed {d}")
            except Exception as e:
                self.meta.mark_error(d, str(e))
                self.notifier.send(f"转录失败 {d}", str(e))

        self.cleanup.scan_and_clean()

    def _check_wifi(self) -> bool:
        try:
            r = subprocess.run(
                ["iwgetid", "-r"],
                capture_output=True, text=True, timeout=5,
            )
            ssid = r.stdout.strip()
            return bool(ssid)
        except Exception:
            return False
