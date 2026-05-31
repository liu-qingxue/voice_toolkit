import json
import os
import signal
import sys
import threading
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QObject, QProcess, Qt, QTimer
from PyQt6.QtGui import QClipboard, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from core.config import CONFIG
from instant_transcribe.engine import LiveEngine
from instant_transcribe.recorder import LiveRecorder
from instant_transcribe.safe_release import SafeRelease

logger = logging.getLogger(__name__)

LOCK = Path(CONFIG["live"]["lock_file"])
RESULT = Path(CONFIG["live"]["result_file"])
STATUS = Path(str(LOCK) + "_status")
IDLE_TIMEOUT = CONFIG.get("live", {}).get("idle_timeout_sec", 3600)

HELPER = (Path(__file__).resolve().parent.parent
          / "global_shortcut_helper" / "build" / "global-shortcut-helper")


class Daemon(QObject):
    def __init__(self):
        super().__init__()
        
        # 创建全局状态锁，保护所有共享状态的并发访问
        self._state_lock = threading.RLock()

        if STATUS.exists() and STATUS.read_text().strip() in ("recording", "transcribing"):
            self._tray = QSystemTrayIcon(self)
            self._tray.showMessage("my_instant_transcribe", "已有实例在运行", QSystemTrayIcon.MessageIcon.Information, 3000)
            QTimer.singleShot(500, QApplication.quit)
            return

        if LOCK.exists():
            try:
                old_pid = int(LOCK.read_text().strip())
                os.kill(old_pid, 0)
                print("[daemon] 已有实例在运行", file=sys.stderr)
                return
            except (OSError, ValueError):
                LOCK.unlink(missing_ok=True)

        try:
            self._engine = LiveEngine()
        except Exception as e:
            print(f"[daemon] 引擎加载失败: {e}", file=sys.stderr)
            QApplication.quit()
            return
        self._safe = SafeRelease(self._engine._engine)

        self._recorder: LiveRecorder | None = None
        self._rec_thread: threading.Thread | None = None
        self._recording = False
        self._transcribing = False
        self._queue: list[str] = []

        self._icon_idle = self._build_icon(Qt.GlobalColor.gray)
        self._icon_rec = self._build_icon(Qt.GlobalColor.red)
        self._icon_loaded = self._build_icon(Qt.GlobalColor.darkGreen)
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._icon_idle)
        self._tray.setToolTip("my_instant_transcribe")

        menu = QMenu()
        self._act_status = menu.addAction("状态: 待机")
        self._act_status.setEnabled(False)
        self._act_toggle = menu.addAction("开始录音")
        self._act_toggle.triggered.connect(self._on_toggle_action)
        act_release = menu.addAction("释放模型")
        act_release.triggered.connect(self._on_release_action)
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self._on_quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activate)
        self._tray.show()
        self._tray.setIcon(self._icon_idle)
        self._tray.showMessage("my_instant_transcribe", "后台已启动", QSystemTrayIcon.MessageIcon.Information, 3000)

        signal.signal(signal.SIGUSR1, lambda s, f: self._queue.append("usr1"))
        signal.signal(signal.SIGUSR2, lambda s, f: self._queue.append("usr2"))
        signal.signal(signal.SIGTERM, lambda s, f: self._queue.append("quit"))

        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_queue)
        self._poll.start(100)

        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self._on_idle)

        self._rec_watch = QTimer(self)
        self._rec_watch.timeout.connect(self._check_recorder)
        self._rec_watch.start(500)

        # 原子化地初始化状态
        self._set_state("idle")
        self._stamp_menu()
        LOCK.write_text(str(os.getpid()))

        self._helper = QProcess(self)
        self._helper_tries = 0
        if HELPER.exists():
            self._helper.finished.connect(self._restart_helper)
            self._helper.start(str(HELPER))
        else:
            print(f"[daemon] helper 未找到: {HELPER}", file=sys.stderr)

    # ── 信号队列轮询 ──────────────────────

    def _poll_queue(self):
        while self._queue:
            msg = self._queue.pop(0)
            if msg == "usr1":
                self._toggle_recording()
            elif msg == "usr2":
                self._on_release()
            elif msg == "quit":
                self._on_quit()

    # ── 状态管理（原子化操作）──────────────

    def _set_state(self, state: str) -> bool:
        """原子化地设置状态（内存和文件同步）
        
        Args:
            state: "idle", "recording", "transcribing"
        
        Returns:
            成功为True，否则为False
        """
        with self._state_lock:
            try:
                if state == "idle":
                    self._recording = False
                    self._transcribing = False
                elif state == "recording":
                    self._recording = True
                    self._transcribing = False
                elif state == "transcribing":
                    self._recording = False
                    self._transcribing = True
                else:
                    logger.warning(f"Unknown state: {state}")
                    return False
                
                # 同时更新文件，确保内存和文件状态一致
                STATUS.write_text(state)
                logger.debug(f"State changed to {state}")
                return True
            except Exception as e:
                logger.error(f"Failed to set state {state}: {e}")
                return False
    
    def _get_state(self) -> str:
        """原子化地获取当前状态"""
        with self._state_lock:
            if self._transcribing:
                return "transcribing"
            elif self._recording:
                return "recording"
            else:
                return "idle"

    # ── 转发 ──────────────────────────────

    def _on_toggle_action(self):
        self._queue.append("usr1")

    def _on_release_action(self):
        self._queue.append("usr2")

    def _on_tray_activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._queue.append("usr1")

    def _build_icon(self, color: Qt.GlobalColor) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(4, 4, 56, 56)
        p.end()
        return QIcon(pix)

    # ── 录音切换（遵循 a/b/c 规范）─────────

    def _toggle_recording(self):
        # 检查转录状态
        with self._state_lock:
            transcribing = self._transcribing
            recording = self._recording
        
        if transcribing:
            self._tray.showMessage("my_instant_transcribe", "正在转录，请稍候",
                                   QSystemTrayIcon.MessageIcon.Information, 3000)
            return

        if not recording:
            # 启动录音
            try:
                self._recorder = LiveRecorder()
                self._rec_thread = threading.Thread(target=self._record_worker, daemon=True)
                
                # 原子化地设置状态
                if not self._set_state("recording"):
                    self._recorder = None
                    self._rec_thread = None
                    return
                
                self._rec_thread.start()
                self._tray.setIcon(self._icon_rec)
                self._tray.setToolTip("my_instant_transcribe - 录音中")
                self._tray.showMessage("my_instant_transcribe", "开始录音",
                                       QSystemTrayIcon.MessageIcon.Information, 2000)
                self._stamp_menu()
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                self._recorder = None
                self._rec_thread = None
                self._set_state("idle")
                self._stamp_menu()
        else:
            # 停止录音
            self._tray.showMessage("my_instant_transcribe", "录音结束，即将转录",
                                   QSystemTrayIcon.MessageIcon.Information, 2000)
            
            # 安全地停止录音
            try:
                audio = self._recorder.stop()
                self._rec_thread.join(timeout=5)
            except Exception as e:
                logger.error(f"Error stopping recorder: {e}")
                audio = None
            finally:
                with self._state_lock:
                    self._recorder = None
                    self._rec_thread = None
                
                # 状态转换到idle（由_transcribe_and_output改为transcribing）
                self._transcribe_and_output(audio)

    def _record_worker(self):
        try:
            self._recorder.run()
        except Exception as e:
            logger.error(f"Recorder thread error: {e}", exc_info=True)
        finally:
            try:
                # 如果录音线程异常退出，通知主线程
                setattr(self._recorder, '_normal_exit', False)
            except Exception:
                pass

    def _check_recorder(self):
        """定时检查录音线程是否仍在运行"""
        with self._state_lock:
            recording = self._recording
            rec_thread = self._rec_thread
            recorder = self._recorder
        
        if recording and rec_thread and not rec_thread.is_alive():
            normal = getattr(recorder, '_normal_exit', False)
            print("[daemon]", "录音线程正常结束" if normal else "录音线程异常退出",
                  file=sys.stderr, flush=True)
            
            try:
                rec_thread.join()
                audio = recorder.stop()
            except Exception as e:
                logger.error(f"Error stopping recorder in check: {e}")
                audio = None
            finally:
                with self._state_lock:
                    self._rec_thread = None
                    self._recording = False
                    self._recorder = None
            
            # 开始转录
            self._transcribe_and_output(audio)

    def _restart_helper(self, _exit_code=None):
        if self._helper_tries >= 3:
            self._tray.showMessage("my_instant_transcribe", "快捷键注册失败，请重启应用",
                                   QSystemTrayIcon.MessageIcon.Critical, 5000)
            return
        self._helper_tries += 1
        self._helper.start(str(HELPER))

    # ── 转录 + 输出 ───────────────────────

    def _transcribe_and_output(self, audio):
        if audio is None or len(audio) == 0:
            print("[daemon] 音频为空", file=sys.stderr, flush=True)
            self._set_state("idle")
            self._stamp_menu()
            return
        
        # 原子化地设置为转录状态
        if not self._set_state("transcribing"):
            self._set_state("idle")
            self._stamp_menu()
            return
        
        self._stamp_menu()
        self._tray.showMessage("my_instant_transcribe", "转录中，请稍候...",
                               QSystemTrayIcon.MessageIcon.Information, 3000)
        try:
            text = self._engine.transcribe(audio)
        except Exception as e:
            print(f"[daemon] 转录异常: {e}", file=sys.stderr, flush=True)
            logger.error(f"Transcription error: {e}", exc_info=True)
            self._tray.showMessage("my_instant_transcribe", f"转录失败: {e}",
                                   QSystemTrayIcon.MessageIcon.Critical, 5000)
            text = ""
        finally:
            # 设置回idle状态，确保无论成功或失败都恢复
            pass
        
        if text:
            try:
                RESULT.write_text(json.dumps({"text": text}), encoding="utf-8")
                self._reset_idle()
                mode = CONFIG.get("live", {}).get("output_mode", "notification")
                if mode == "window":
                    from instant_transcribe.popup import TranscriptionPopup
                    TranscriptionPopup(text)
                elif mode == "cursor":
                    QGuiApplication.clipboard().setText(text)
                    import subprocess
                    subprocess.Popen(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])
                else:
                    preview = text[:60].replace("\n", " ")
                    self._tray.showMessage("my_instant_transcribe", preview,
                                           QSystemTrayIcon.MessageIcon.Information, 5000)
            except Exception as e:
                logger.error(f"Error outputting transcription: {e}")
        
        # 最后原子化地恢复到idle状态
        self._set_state("idle")
        self._stamp_menu()

    # ── 模型管理 ──────────────────────────

    def _on_release(self):
        """释放模型"""
        with self._state_lock:
            transcribing = self._transcribing
        
        if transcribing:
            return
        self._safe.try_release()
        self._idle.stop()
        self._set_state("idle")
        self._tray.setIcon(self._icon_idle)
        self._tray.setToolTip("my_instant_transcribe - 待机 (模型已释放)")
        self._stamp_menu()

    def _reset_idle(self):
        """重置空闲计时器"""
        self._idle.stop()
        if IDLE_TIMEOUT > 0:
            self._idle.start(IDLE_TIMEOUT * 1000)

    def _on_idle(self):
        """空闲超时回调"""
        self._safe.try_release()
        self._set_state("idle")
        self._tray.setIcon(self._icon_idle)
        self._tray.setToolTip("my_instant_transcribe - 待机 (模型已释放)")
        self._stamp_menu()

    # ── 托盘 UI 更新 ─────────────────────

    def _stamp_menu(self):
        """更新托盘菜单和图标（读取共享状态需要加锁）"""
        with self._state_lock:
            transcribing = self._transcribing
            recording = self._recording
        
        state = []
        if transcribing:
            state.append("转录中")
            self._tray.setIcon(self._icon_loaded)
        elif recording:
            state.append("录音中")
            self._tray.setIcon(self._icon_rec)
        elif self._safe.is_loaded():
            state.append("模型已加载")
            self._tray.setIcon(self._icon_loaded)
        else:
            state.append("待机")
            self._tray.setIcon(self._icon_idle)
        if IDLE_TIMEOUT > 0:
            state.append(f"空闲释放:{IDLE_TIMEOUT}s")
        else:
            state.append("空闲释放:关")
        self._act_status.setText("  |  ".join(state))
        self._act_toggle.setText("停止录音" if recording else "开始录音")
        self._act_toggle.setEnabled(not transcribing)

    # ── 退出 ──────────────────────────────

    def _on_quit(self):
        """安全退出"""
        with self._state_lock:
            transcribing = self._transcribing
        
        if transcribing:
            reply = QMessageBox.question(
                None, "确认退出", "正在转录中，退出将中断转录。确定退出？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        self._safe.try_release()
        
        # 停止定时器
        self._poll.stop()
        self._rec_watch.stop()
        self._idle.stop()
        
        # 停止helper进程
        if hasattr(self, '_helper') and self._helper.state() == QProcess.ProcessState.Running:
            self._helper.kill()
            self._helper.waitForFinished(2000)
        
        # 清理锁文件
        LOCK.unlink(missing_ok=True)
        STATUS.unlink(missing_ok=True)
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _ = Daemon()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
