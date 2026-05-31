import os
import smtplib
from email.message import EmailMessage
from core.config import CONFIG


class Notifier:
    def __init__(self):
        cfg = CONFIG.get("mail", {})
        self.enabled = cfg.get("enabled", False)
        self.host = cfg.get("smtp_host", "")
        self.port = cfg.get("smtp_port", 587)
        self.user = os.environ.get("SMTP_USER", "")
        self.passwd = os.environ.get("SMTP_PASS", "")
        self.to = cfg.get("to", "")

    def send(self, subject: str, body: str):
        print(f"[notifier] {subject}")
        print(f"  {body[:200]}")
        if not self.enabled:
            return
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = self.to
        try:
            with smtplib.SMTP(self.host, self.port) as s:
                s.starttls()
                s.login(self.user, self.passwd)
                s.send_message(msg)
        except Exception as e:
            print(f"[notifier] send failed: {e}")
