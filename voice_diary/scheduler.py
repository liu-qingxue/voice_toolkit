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
    def __init__(self, port: int = 8765):
        self.port = port
        self.meta = MetaDB()
        self.transcriber = DiaryTranscriber()
        self.cleanup = CleanupManager(self.meta)
        self.notifier = Notifier()

        def _get_phone_ip(self) -> str:
            """从默认路由获取手机热点的网关 IP（IPv4）"""
            try:
                # 使用 ip route 获取默认网关（更可靠）
                r = subprocess.run(
                    ["ip", "route", "show", "default"],
                    capture_output=True, text=True, timeout=5
                )
                # 输出示例："default via 192.168.23.99 dev wlan0 proto dhcp metric 600"
                tokens = r.stdout.strip().split()
                # 找到 "via" 后面的第一个 IP
                idx = tokens.index("via")
                return tokens[idx + 1]
            except Exception as e:
                print(f"[scheduler] 获取网关 IP 失败：{e}")
                # 常见热点网段 fallback，但最好让用户检查日志
                return "192.168.43.1"   # 作为兜底，但会在日志警告

    def run_once(self):
        # subprocess.run(["/home/qingyuxue/Projects/voice_toolkit/voice_diary/connect_to_hotspot.sh"], capture_output=True)

        #  获取手机热点 IP
        phone_ip = self._get_phone_ip()
        self.fetcher = Fetcher(phone_ip, self.port)   # 动态创建 fetcher

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
        # try:
        #     # 获取当前活动连接的名称和类型
        #     r = subprocess.run(
        #         ["nmcli", "-t", "connection", "show", "--active"],
        #         capture_output=True, text=True, timeout=5
        #     )
        #     for line in r.stdout.splitlines():
        #         parts = line.split(':')
        #         if len(parts) >= 3 and parts[2] == 'wifi':  # 第三个字段是类型
        #             ssid = parts[0]  # 第一个字段是连接名称（即 SSID）
        #             prefix = CONFIG.get("hotspot_ssid_prefix", "voice_diary")
        #             return ssid.startswith(prefix)
        #     return False
        # except Exception as e:
        #     print(f"[_check_wifi] error: {e}")
        #     return False
        return True  # 暂时跳过 Wi-Fi 检测
