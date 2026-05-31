import json
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date
from core.config import CONFIG


class Fetcher:
    def __init__(self, host: str, port: int = 8765, data_dir: str | Path = None):
        self.base = f"http://{host}:{port}"
        self.data_dir = Path(data_dir or CONFIG["pc_data_dir"])
        self.raw_dir = self.data_dir / "raw"

    def fetch(self, d: date) -> list[Path]:
        date_str = d.isoformat()
        status = self._get_json(f"/status")
        target_files = [
            f for f in status.get("files", [])
            if f.startswith(date_str)
        ]
        if not target_files:
            return []

        downloaded = []
        for fname_with_date in target_files:
            short_name = fname_with_date.split("/", 1)[1]
            local = self._download_one(date_str, short_name)
            if local:
                downloaded.append(local)

        if downloaded:
            self._confirm(date_str, [f.name for f in downloaded])

        return downloaded

    def _download_one(self, date_str: str, fname: str) -> Path | None:
        url = f"{self.base}/download/{date_str}/{fname}"
        local_dir = self.raw_dir / date_str
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / fname

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                remote_md5 = resp.headers.get("Content-MD5", "")
                if remote_md5:
                    local_md5 = hashlib.md5(data).hexdigest()
                    if local_md5 != remote_md5:
                        raise ValueError(f"MD5 mismatch: {fname}")
                local_path.write_bytes(data)
            print(f"[fetcher] downloaded {fname} ({len(data)} bytes)")
            return local_path
        except Exception as e:
            print(f"[fetcher] download {fname} failed: {e}")
            return None

    def _get_json(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.base}{path}", timeout=10) as resp:
            return json.loads(resp.read())

    def _confirm(self, date_str: str, files: list[str]):
        body = json.dumps({"date": date_str, "files": files}).encode()
        req = urllib.request.Request(
            f"{self.base}/confirm",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            print(f"[fetcher] confirmed {len(files)} files, "
                  f"phone deleted {result.get('deleted', 0)}")
        except Exception as e:
            print(f"[fetcher] confirm failed: {e}")
            raise
