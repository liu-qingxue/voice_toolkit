"""
live 守护进程
启动 Qt 事件循环 + 系统托盘，由 toggle.py 写入命令文件切换录音/转录。
"""
import json
import os
import sys
import fcntl
import threading
import logging
import concurrent.futures
from pathlib import Path
from PyQt6.QtCore import Qt, QObject, QTimer, QFileSystemWatcher
from PyQt6.QtGui import QIcon, QPainter, QPixmap, QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

ROOT = Path(__file__).resolve().parent.parent   # 入口处必须要有!!!
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import log
from config import CFG
from core import create_transcriber
from live.recorder import LiveRecorder
from live.dispatcher import dispatch

LOCK = CFG.lock_file
RESULT = CFG.result_file
CMD = CFG.cannel_cmd

IDLE_TIMEOUT = CFG.idle_timeout_sec

DEBUG_LOG = log.LOG_FILE
logger = logging.getLogger(__name__)

_lock_fd: int | None = None
_transcriber = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

def _try_lock() -> bool:
    """获取排他锁—已有实例则返回 False"""
    global _lock_fd
    try:
        _lock_fd = os.open(str(LOCK), os.O_CREAT | os.O_RDWR)   # 读写模式+文件不存在时自动创建
    except OSError as e:
        logger.error(f"系统错误,无法创建锁文件: {e}")
        return False
    except Exception as e:
        logger.error(f"无法创建锁文件,错误: {e}")
        return False
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)   # 排他锁 + 非阻塞(Non-Blocking)—拿不到就立刻报错，不等
    except BlockingIOError as e:
        logger.error(f"排他锁获取失败: {e}")
        os.close(_lock_fd)
        _lock_fd = None
        return False
    except OSError as e:
        logger.error(f"系统错误,获取文件锁失败: {e}")
        os.close(_lock_fd)
        _lock_fd = None
        return False 
    except Exception as e:
        logger.error(f"错误: {e}")
        os.close(_lock_fd)
        _lock_fd = None
        return False
    return True

def _release_lock():
    """"""
    global _lock_fd
    if _lock_fd is not None:
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
        os.close(_lock_fd)
        _lock_fd = None

# ── 托盘图标 ──────────────────────────────
def _build_icon(color):
    pix = QPixmap(64, 64)   # 画布
    pix.fill(Qt.GlobalColor.transparent)   # 透明背景
    p = QPainter(pix)   # 笔
    p.setRenderHint(QPainter.RenderHint.Antialiasing)   # 抗锯齿,抗像素带来的"齿轮感"
    p.setPen(Qt.PenStyle.NoPen)   # 无边框
    p.setBrush(color)   # 填充色
    p.drawEllipse(4, 4, 56, 56)   # 图形边界为椭圆,坐标为外接矩形
    p.end()
    return QIcon(pix)   # 一个智能图标,自己可以"感受"鼠标信号来展示不同的图片

# ── 核心事件循环 ──────────────────────────
class LiveLoop(QObject):
    def __init__(self, tray: QSystemTrayIcon, parent=None):
        super().__init__(parent)
        self._tray = tray
        self._recorder: LiveRecorder | None = None
        self._rec_thread: threading.Thread | None = None
        self._transcribing = False
        self._transcribe_future: concurrent.futures.Future | None = None

        self._icon_idle = _build_icon(Qt.GlobalColor.gray)   # 空闲,gray-灰色
        self._icon_rec = _build_icon(Qt.GlobalColor.red)
        self._icon_loaded = _build_icon(Qt.GlobalColor.darkGreen)

        CMD.unlink(missing_ok=True)

        # 1==> 文件变更监控 
        self._fs_watcher = QFileSystemWatcher(self)   # QObject 子类在创建时都可以接受一个 parent 参数 ,负责它的生命周期
        self._fs_watcher.directoryChanged.connect(self._on_cmd_dir_changed)  # Watcher-观察者
        self._fs_watcher.addPath(str(CMD.parent))

        # 2==> 转录结果轮询 (保持低开销，转录完成后立即 dispatch) ──
        self._transcribe_poll = QTimer(self)   # poll-轮询
        self._transcribe_poll.timeout.connect(self._poll_transcribe)
        self._transcribe_poll.start(100)   # 按设定的时间间隔，定期发射 timeout 信号,这里的Qtimer是一个定时器,timeout不是超时!

        # ── 空闲卸载计时器 ──
        self._idle = QTimer(self)   # idle-空闲(ideal-理想/理想的)
        self._idle.setSingleShot(True)   # 单次触发,single-单次;shot-开一次枪
        self._idle.timeout.connect(self._on_idle)

        self._reset_idle()

    def _reset_idle(self):
        self._idle.stop()
        if IDLE_TIMEOUT > 0:
            self._idle.start(IDLE_TIMEOUT * 1000)

    def _on_cmd_dir_changed(self, path: str):
        """CMD 文件所在的目录有变动时触发"""
        if not CMD.exists():
            return
        try:
            cmd = CMD.read_text().strip()
            CMD.unlink(missing_ok=True)
        except Exception:
            return

        logger.debug(f"CMD 内容: {cmd!r}")
        if cmd == "quit":
            self._on_quit()
        elif cmd == "release":
            self._release_engine()
        elif cmd == "toggle":
            self._toggle()

    # ── 录音控制 ──────────────────────────
    def _toggle(self):
        if self._transcribing:
            self._tray.showMessage("提示", "正在转录中，请稍候",
                                   QSystemTrayIcon.MessageIcon.Information, 2000)
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
        logger.info("录音开始")

    def _stop_and_transcribe(self):
        logger.info("录音停止，开始转录")
        audio = self._recorder.stop()
        self._rec_thread.join(timeout=5)
        self._recorder = None
        self._rec_thread = None

        if audio is None or len(audio) == 0:
            self._back_to_idle()
            return

        global _transcriber
        self._transcribing = True
        self._tray.setIcon(self._icon_loaded)
        self._tray.setToolTip("转录中")

        if _transcriber is None:
            _transcriber = create_transcriber()
        self._transcribe_future = _executor.submit(_transcriber.transcribe, audio)

    def _poll_transcribe(self):
        """检查异步转录是否完成（在主线程中执行 dispatch）"""
        if self._transcribe_future is None:
            return
        if not self._transcribe_future.done():
            return
        text = ""
        try:
            text = self._transcribe_future.result()
        except Exception as e:
            logger.error(f"转录异常: {e}")
            self._tray.showMessage("转录失败", str(e),
                                   QSystemTrayIcon.MessageIcon.Critical, 5000)
        self._transcribe_future = None
        self._transcribing = False

        dispatch(text,
                 notify=self._show_notification,
                 show_window=self._show_window)
        self._reset_idle()
        self._back_to_idle()

    def _show_notification(self, preview: str):
        self._tray.showMessage("转录结果", preview,
                               QSystemTrayIcon.MessageIcon.Information, 5000)

    def _show_window(self, text: str):
        from live.popup import TranscriptionPopup
        TranscriptionPopup(text)

    def _back_to_idle(self):
        self._tray.setIcon(self._icon_idle)
        self._tray.setToolTip("待机")
        logger.info("回到待机")

    # ── 模型管理 ──────────────────────────
    def _release_engine(self):
        global _transcriber
        if _transcriber is not None:
            try:
                _transcriber.unload()
            except Exception:
                pass
            _transcriber = None
        self._idle.stop()
        self._back_to_idle()
        logger.info("模型已释放")


    def _on_idle(self):
        self._release_engine()

    # ── 退出 ──────────────────────────────
    def _on_quit(self):
        if self._recorder is not None:
            self._recorder.stop()
            if self._rec_thread:
                self._rec_thread.join(timeout=3)
        self._release_engine()
        self._transcribe_poll.stop()
        self._idle.stop()
        CMD.unlink(missing_ok=True)
        RESULT.unlink(missing_ok=True)
        _release_lock()
        QApplication.quit()

# ── 入口 ──────────────────────────────────
def main():
    logger.info("=== 守护进程启动 ===")

    RESULT.unlink(missing_ok=True)

    if not _try_lock():
        logger.warning("已有实例在运行")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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

    loop = LiveLoop(tray)

    def update_menu():
        if loop._recorder is not None:
            act_status.setText("状态: 录音中")
        elif loop._transcribing:
            act_status.setText("状态: 转录中")
        elif _transcriber is not None and hasattr(_transcriber, 'is_loaded') and _transcriber.is_loaded:
            act_status.setText("状态: 模型已加载")
        else:
            act_status.setText("状态: 待机")

    menu_timer = QTimer()
    menu_timer.timeout.connect(update_menu)
    menu_timer.start(500)

    act_quit.triggered.connect(loop._on_quit)

    logger.info("Qt 事件循环启动")
    sys.exit(app.exec())

if __name__ == "__main__": 
    main()
