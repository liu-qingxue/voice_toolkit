"""
live 守护进程
启动 Qt 事件循环 + 系统托盘，由 toggle.py 写入命令文件切换录音/转录。
"""
import json
import os
import sys
import threading
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt, QObject, QProcess, QTimer
from PyQt6.QtGui import QIcon, QPainter, QPixmap, QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config.config import CFG
from core.create_transcriber import create_transcriber
from live.recorder import LiveRecorder
from live.dispatcher import dispatch

ROOT = Path(__file__).resolve().parent.parent
LOCK = Path(CFG.lock_file)
RESULT = Path(CFG.result_file)
CMD = Path(str(LOCK) + "_cmd")
IDLE_TIMEOUT = CFG.idle_timeout_sec or 3600
HELPER = ROOT / "global_shortcut_helper" / "build" / "global-shortcut-helper"
DEBUG_LOG = Path("/tmp/live_transcriber_debug.log")

logger = logging.getLogger(__name__)


def _debug(msg: str):
    with DEBUG_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{os.getpid()}] {msg}\n")


# ── 托盘图标 ──────────────────────────────

def _build_icon(color):
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(4, 4, 56, 56)
    p.end()
    return QIcon(pix)


# ── 核心循环 ──────────────────────────────

class LiveLoop(QObject):
    def __init__(self, tray: QSystemTrayIcon, parent=None):
        super().__init__(parent)
        self._tray = tray
        self._recorder: LiveRecorder | None = None
        self._rec_thread: threading.Thread | None = None
        self._transcribing = False
        self._queue: list[str] = []

        self._icon_idle = _build_icon(Qt.GlobalColor.gray)
        self._icon_rec = _build_icon(Qt.GlobalColor.red)
        self._icon_loaded = _build_icon(Qt.GlobalColor.darkGreen)

        CMD.unlink(missing_ok=True)

        self._poll_cnt = 0
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_queue)
        self._poll.start(100)

        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self._on_idle)

        self._transcriber = None
        self._reset_idle()

    def _poll_queue(self):
        self._poll_cnt += 1
        if self._poll_cnt % 100 == 0:
            _debug(f"_poll_queue 已触发 {self._poll_cnt} 次")
        # 检查命令文件
        if CMD.exists():
            _debug("CMD 文件存在")
            try:
                cmd = CMD.read_text().strip()
                CMD.unlink(missing_ok=True)
                _debug(f"CMD 内容: {cmd!r}")
            except Exception as e:
                _debug(f"CMD 读取异常: {e}")
                cmd = ""
            if cmd == "toggle":
                self._queue.append("toggle")
            elif cmd == "quit":
                self._queue.append("quit")
            elif cmd == "release":
                self._queue.append("release")

        while self._queue:
            msg = self._queue.pop(0)
            _debug(f"处理队列消息: {msg}")
            if msg == "toggle":
                self._toggle()
            elif msg == "release":
                self._release_engine()
            elif msg == "quit":
                self._on_quit()

    # ── 录音控制 ──────────────────────────

    def _toggle(self):
        if self._transcribing:
            self._tray.showMessage("提示", "正在转录中，请稍候", QSystemTrayIcon.MessageIcon.Information, 2000)
            return

        if self._recorder is None:
            self._start_recording()
        else:
            self._stop_and_transcribe()

    def _start_recording(self):
        self._recorder = LiveRecorder()
        self._rec_thread = threading.Thread(target=self._recorder.run, daemon=True)
        self._rec_thread.start()
        self._tray.setIcon(self._icon_rec)
        self._tray.setToolTip("录音中")
        _debug("录音开始")

    def _stop_and_transcribe(self):
        _debug("录音停止，开始转录")
        audio = self._recorder.stop()
        self._rec_thread.join(timeout=5)
        self._recorder = None
        self._rec_thread = None

        if audio is None or len(audio) == 0:
            self._back_to_idle()
            return

        self._transcribing = True
        self._tray.setIcon(self._icon_loaded)
        self._tray.setToolTip("转录中")

        try:
            if self._transcriber is None:
                self._transcriber = create_transcriber()
            text = self._transcriber.transcribe(audio)
        except Exception as e:
            _debug(f"转录异常: {e}")
            self._tray.showMessage("转录失败", str(e), QSystemTrayIcon.MessageIcon.Critical, 5000)
            text = ""

        self._transcribing = False

        dispatch(text,
                 notify=self._show_notification,
                 show_window=self._show_window)
        self._reset_idle()
        self._back_to_idle()

    def _show_notification(self, preview: str):
        self._tray.showMessage("转录结果", preview, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _show_window(self, text: str):
        from live.popup import TranscriptionPopup
        TranscriptionPopup(text)

    def _back_to_idle(self):
        self._tray.setIcon(self._icon_idle)
        self._tray.setToolTip("待机")
        _debug("回到待机")

    # ── 模型管理 ──────────────────────────

    def _release_engine(self):
        if self._transcriber is not None:
            try:
                self._transcriber.unload()
            except Exception:
                pass
            self._transcriber = None
        self._idle.stop()
        self._back_to_idle()
        _debug("模型已释放")

    def _reset_idle(self):
        self._idle.stop()
        if IDLE_TIMEOUT > 0:
            self._idle.start(IDLE_TIMEOUT * 1000)

    def _on_idle(self):
        self._release_engine()

    # ── 退出 ──────────────────────────────

    def _on_quit(self):
        if self._recorder is not None:
            self._recorder.stop()
            if self._rec_thread:
                self._rec_thread.join(timeout=3)
        self._release_engine()
        self._poll.stop()
        self._idle.stop()
        CMD.unlink(missing_ok=True)
        LOCK.unlink(missing_ok=True)
        RESULT.unlink(missing_ok=True)
        QApplication.quit()


# ── 入口 ──────────────────────────────────

def main():
    _debug("=== 守护进程启动 ===")

    # 清理旧资源
    RESULT.unlink(missing_ok=True)

    # 单例检测
    if LOCK.exists():
        try:
            old_pid = int(LOCK.read_text().strip())
            os.kill(old_pid, 0)
            print("已有实例在运行", file=sys.stderr)
            sys.exit(1)
        except ValueError:
            LOCK.unlink(missing_ok=True)
        except ProcessLookupError:
            LOCK.unlink(missing_ok=True)
        except PermissionError:
            print("权限不足，无法确认旧实例状态", file=sys.stderr)
            sys.exit(1)
        except OSError:
            LOCK.unlink(missing_ok=True)

    # Qt 应用
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 系统托盘
    tray = QSystemTrayIcon()
    idle_icon = _build_icon(Qt.GlobalColor.gray)
    tray.setIcon(idle_icon)
    tray.setToolTip("live 转录")

    menu = QMenu()
    act_status = menu.addAction("状态: 待机")
    act_status.setEnabled(False)
    menu.addSeparator()
    act_quit = menu.addAction("退出")
    tray.setContextMenu(menu)
    tray.show()

    # 核心循环
    loop = LiveLoop(tray)

    # 菜单联动
    def update_menu():
        if loop._recorder is not None:
            act_status.setText("状态: 录音中")
        elif loop._transcribing:
            act_status.setText("状态: 转录中")
        elif loop._transcriber is not None and hasattr(loop._transcriber, 'is_loaded') and loop._transcriber.is_loaded:
            act_status.setText("状态: 模型已加载")
        else:
            act_status.setText("状态: 待机")

    menu_timer = QTimer()
    menu_timer.timeout.connect(update_menu)
    menu_timer.start(500)

    # 退出菜单
    act_quit.triggered.connect(loop._on_quit)

    # 写入 LOCK
    LOCK.write_text(str(os.getpid()))
    _debug(f"LOCK 已写入 (pid={os.getpid()})")

    # Helper 进程（父对象为 loop，保证生命周期）
    helper = QProcess(loop)
    if HELPER.exists():
        def _start_helper():
            try:
                helper.start(str(HELPER))
            except RuntimeError:
                _debug("helper 已销毁，忽略")
        helper.finished.connect(_start_helper)
        _start_helper()
    else:
        print(f"[live] helper 未找到: {HELPER}", file=sys.stderr)

    _debug("Qt 事件循环启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
