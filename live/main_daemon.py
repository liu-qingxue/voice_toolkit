"""
live 守护进程
启动 Qt 事件循环 + 系统托盘，由 toggle.py 写入命令文件切换录音/转录。
"""
import json
import os
import sys
import threading
import logging
import concurrent.futures
from pathlib import Path
try:
    import fcntl  # Linux: POSIX 文件锁(Windows 无此模块, 见 _try_lock)
except ImportError:
    fcntl = None  # Windows: 改用 PID 文件互斥
from PyQt6.QtCore import Qt, QObject, QTimer, QFileSystemWatcher, QSocketNotifier
from PyQt6.QtGui import QIcon, QPainter, QPixmap, QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

ROOT = Path(__file__).resolve().parent.parent   # 入口处必须要有!!!
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import log
from config import CFG
from core import create_transcriber
from live.recorder import LiveRecorder
from frontend.window import TranscriptionPopup
from frontend.dispatcher import dispatch

LOCK = CFG.lock_file
RESULT = CFG.result_file
CMD = CFG.cannel_cmd
STATE = CFG.state_file


def _write_state(state: str):
    """把 daemon 运行状态(idle/recording/transcribing)写入 state 文件。
    供 toggle.py / run.ps1 判断本次 toggle 应否等待转录结果。纯新增文件,
    Linux 旧调用链不读它, 无任何副作用。"""
    try:
        STATE.write_text(state, encoding="utf-8")
    except OSError as e:
        logger.error(f"state 文件写入失败: {e}")

IDLE_TIMEOUT = CFG.idle_timeout_sec

DEBUG_LOG = log.LOG_FILE
logger = logging.getLogger("live/main_daemon.py")
logger.warning("测试一下这个logger的名称")

_lock_fd: int | None = None
_transcriber = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)   # concurrent-并发,executor-执行者

def _try_lock() -> bool:
    """获取单实例锁, 成功返回 True, 已有实例则返回 False
    - Linux:   fcntl 排他锁(沿用旧机制)
    - Windows: PID 文件 —— 文件里存 daemon 自己 PID, 进程存活即互斥
    """
    global _lock_fd
    if fcntl is None:
        return _win_try_pid_lock()
    try:
        _lock_fd = os.open(str(LOCK), os.O_CREAT | os.O_RDWR)   # 读写模式+文件不存在时自动创建
        logger.info(f"{LOCK}创建成功,lock_fd为{_lock_fd}")
    except OSError as e:
        logger.error(f"系统错误,无法创建锁文件: {e}")
        return False
    except Exception as e:
        logger.error(f"上锁错误: {e}")
        return False
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)   # 排他锁 + 非阻塞(Non-Blocking)—拿不到就立刻报错，不等
        logger.info(f"排它锁创建成功,lock_fd为{_lock_fd}")   # EX-exclusive-专享的/互斥的/排它的/ ; NB-no_blocking-不阻塞
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


def _win_pid_alive(pid: int) -> bool:
    """Windows 进程存活探测。
    ⚠️ 不能用 os.kill(pid, 0): Windows 上 os.kill 除 CTRL_* 外一律
    TerminateProcess, 会把 pid 对应的进程真的杀掉。"""
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    kernel32.CloseHandle(h)
    return True


def _win_try_pid_lock() -> bool:
    """Windows 单实例: PID 文件。文件里的进程活着 = 已有实例。
    若文件残留但进程已死(异常退出), 直接清理后接管。"""
    global _lock_fd
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip())
            if _win_pid_alive(pid):
                logger.warning(f"已有实例在运行 (pid={pid})")
                return False
        except (OSError, ValueError):
            pass
        # 残留(进程已死/内容损坏) → 清理接管
        try:
            LOCK.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"清理残留锁失败: {e}")
    try:
        LOCK.write_text(str(os.getpid()), encoding="ascii")
    except OSError as e:
        logger.error(f"PID 锁写入失败: {e}")
        return False
    _lock_fd = "pid"   # 占位标记, 仅用于 _release_lock 判断
    logger.info(f"PID 锁创建成功, pid={os.getpid()}")
    return True


def _release_lock():
    """释放单实例锁"""
    global _lock_fd
    if _lock_fd is None:
        return
    if fcntl is None:
        # Windows: 删 PID 文件
        try:
            LOCK.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"PID 锁删除失败: {e}")
        _lock_fd = None
        return
    fcntl.flock(_lock_fd, fcntl.LOCK_UN)
    os.close(_lock_fd)
    logger.info("已解锁")
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
        self._icon_rec = _build_icon(Qt.GlobalColor.red)   # rec-recording
        self._icon_loaded = _build_icon(Qt.GlobalColor.darkGreen)

        CMD.unlink(missing_ok=True)

        # 文件变更监控 
        self._fs_watcher = QFileSystemWatcher(self)   # QObject 子类在创建时都可以接受一个 parent 参数 ,负责它的生命周期
        self._fs_watcher.directoryChanged.connect(self._on_cmd_dir_changed)  # Watcher-观察者
        self._fs_watcher.addPath(str(CMD.parent))

        # 转录结果轮询 (保持低开销，转录完成后立即 dispatch) ──
        self._transcribe_poll = QTimer(self)   # poll-轮询
        self._transcribe_poll.timeout.connect(self._poll_transcribe)
        self._transcribe_poll.start(100)   # 按设定的时间间隔，定期发射 timeout 信号,这里的Qtimer是一个定时器,timeout不是超时!

        # ── 配置热加载 ──
        if sys.platform == "win32":
            # Windows 无 inotify: 定时器轮询 config.yaml 的 mtime, 有变化才重载(开销可忽略)
            self._cfg_mtime: float | None = None
            self._cfg_poll = QTimer(self)
            self._cfg_poll.timeout.connect(self._on_cfg_poll)
            self._cfg_poll.start(1000)
        else:
            # Linux: inotify 事件驱动(沿用旧机制)
            import ctypes
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            self._inotify_fd = libc.inotify_init()
            if self._inotify_fd < 0:
                logger.error("inotify_init 失败")
            else:
                wd = libc.inotify_add_watch(
                    self._inotify_fd,
                    str(CFG.config_dir).encode(),
                    0x02 | 0x100)  # IN_CLOSE_WRITE | IN_CREATE
                if wd < 0:
                    logger.error("inotify_add_watch 失败")
                else:
                    self._inotify_notifier = QSocketNotifier(
                        self._inotify_fd, QSocketNotifier.Type.Read)
                    self._inotify_notifier.activated.connect(self._on_inotify_ready)

        # ── 空闲卸载计时器 ──
        self._idle = QTimer(self)   # idle-空闲(ideal-理想/理想的)
        self._idle.setSingleShot(True)   # 单次触发,single-单次;shot-开一次枪
        self._idle.timeout.connect(self._release_engine)

        self._idle.start(IDLE_TIMEOUT * 1000)   # 将 ms 转化为 s

    # ===== cmd三个命令 ============
    def _on_cmd_dir_changed(self, path: str):
        """CMD 文件所在的目录有变动时触发"""
        if not CMD.exists():
            return
        try:
            cmd = CMD.read_text().strip()
            CMD.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"cannel_cmd文件({CMD})读取失败: {e}")
            return

        logger.debug(f"CMD 内容: {cmd!r}")
        if cmd == "quit":
            self._on_quit()
        elif cmd == "release":
            self._release_engine()
        elif cmd == "toggle":
            self._toggle()

    def _on_quit(self):
        """ # 退出
        - 如果在录音,直接丢弃
        - 然后:
            - 卸载模型
            - 停止转录结果轮询(_transcribe_poll)
            - 删除通信文件, 结果暂存文件
            - 解锁
            - 通知Qt关闭
        """
        if self._recorder is not None:
            discarded_audio = self._recorder.stop()  # 1. 拿出来
            if discarded_audio is not None and len(discarded_audio) > 0:
                logger.info(f"[退出] 丢弃未转录音频，长度: {len(discarded_audio)}") # 2. 记录一下
                del discarded_audio  # 3. 显式删除引用（非必须，但很清晰）
            if self._rec_thread:
                self._rec_thread.join(timeout=3)   # 等待这个线程的退出最多等三秒。  
        self._release_engine()
        self._transcribe_poll.stop()
        CMD.unlink(missing_ok=True)
        RESULT.unlink(missing_ok=True)
        STATE.unlink(missing_ok=True)
        _release_lock()
        QApplication.quit()

    def _release_engine(self):
        """ # 卸载模型
        - 卸载模型
        - 停止_idle的计时
        - 更新托盘为idle状态
        """
        global _transcriber
        if _transcriber is not None:
            try:
                _transcriber.unload()
            except Exception as e:
                logger.error(f"model卸载失败; {e}")
            _transcriber = None
        self._idle.stop()
        self._tray_update(1)
        logger.info("模型已释放")

    def _toggle(self):
        """ # 响应快捷信号
        - 正在转录,返回空
            - 没在录音,开始录音
            - 在录音,  开始转录
        """
        if self._transcribing:
            self._tray.showMessage("提示", "正在转录中，请稍候", QSystemTrayIcon.MessageIcon.Information, 5000)
            return
        if self._recorder is None:
            # 开始录音(mock 调试模式不依赖麦克风)
            self._idle.stop()
            self._recorder = LiveRecorder(mock=(CFG.model == "mock"))
            # daemon--当前进程结束的时候，这个进程将作为连带进程跟着被结束。
            self._rec_thread = threading.Thread(target=self._recorder.run, daemon=True)
            self._rec_thread.start()

            # 录音已开始,更新ui
            self._tray_update(2)
            _write_state("recording")
            logger.info("录音开始")
        else:
            logger.info("录音停止，开始转录")
            audio = self._recorder.stop()
            self._rec_thread.join(timeout=5)
            self._recorder = None
            self._rec_thread = None

            # 直接返回空,更新托盘为空闲状态,并跳过转录
            if audio is None or len(audio) == 0:
                self._tray_update(1)
                _write_state("idle")
                return

            # 开始转录
            global _transcriber
            self._transcribing = True
            if _transcriber is None:
                _transcriber = create_transcriber(mode= "live")
            self._transcribe_future = _executor.submit(_transcriber.transcribe, audio)

            self._tray_update(3) # 更新托盘为转录状态
            _write_state("transcribing")

    # ===== 配置热加载 ============
    def _on_inotify_ready(self, fd):
        os.read(fd, 4096)
        if CFG.reload():
            logger.info(f"配置热加载: output_mode={CFG.output_mode}")

    def _on_cfg_poll(self):
        """Windows: 定时检查 config.yaml 是否变化(保存后自动生效)"""
        try:
            m = (CFG.config_dir / "config.yaml").stat().st_mtime
        except OSError:
            return
        if self._cfg_mtime is None or m != self._cfg_mtime:
            self._cfg_mtime = m
            if CFG.reload():
                logger.info(f"配置热加载: output_mode={CFG.output_mode}")

    # ===== 转录轮询 ========
    def _poll_transcribe(self):
        if self._transcribe_future is None:
            return
        if not self._transcribe_future.done():
            return
        logger.info("future 完成，开始取结果")
        text = ""
        try:
            text = self._transcribe_future.result()
        except Exception as e:
            logger.error(f"转录异常: {e}")
            self._tray.showMessage("转录失败", str(e), QSystemTrayIcon.MessageIcon.Critical, 5000)
        self._transcribe_future = None   # 清空队列
        self._transcribing = False   # 转录结束了!!

        # 空闲卸载器==>开始计时
        self._idle.stop()
        self._idle.start(IDLE_TIMEOUT * 1000)   # 将 ms 转化为 s

        try:
            dispatch(text,
                     notify=self._show_notification,
                     show_window=self._show_window)
        except Exception as e:
            logger.error(f"dispatch 异常: {e}", exc_info=True)
        
        self._tray_update(1)
        _write_state("idle")

    # ===== 前端 ============
    def _show_notification(self, preview: str):
        self._tray.showMessage("转录结果", preview, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _show_window(self, text: str):
        TranscriptionPopup(text)
    # ===== 托盘 ===========
    def _tray_update(self,mode: int):
        """更新托盘
        - mode=[1,2,3]==>[待机,正在录音,正在转录]
        - 将托盘变色
        - 将悬停提示变化"""
        if mode==1:
            self._tray.setIcon(self._icon_idle)
            self._tray.setToolTip("待机")
        elif mode==2:
            self._tray.setIcon(self._icon_rec)
            self._tray.setToolTip("正在录音")
        elif mode==3:
            self._tray.setIcon(self._icon_loaded)
            self._tray.setToolTip("正在转录")
        else: 
            logger.error(f"托盘调用异常")
 
# ── 入口 ──────────────────────────────────
def main():
    logger.info("=== 守护进程启动 ===")

    RESULT.unlink(missing_ok=True)

    if not _try_lock():
        logger.warning("已有实例在运行")
        sys.exit(1)
    _write_state("idle")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 当最后一个窗口关闭时，别退出。

    idle_icon = _build_icon(Qt.GlobalColor.gray)
    tray = QSystemTrayIcon()
    tray.setIcon(idle_icon)
    tray.setToolTip("live 转录")

    menu = QMenu()   # 创建空菜单
    act_status = menu.addAction("状态: 待机")   # 添加第一个项目
    act_status.setEnabled(False)   # 这个项目是只读不可操作的。
    menu.addSeparator()   # 添加一条分隔线，添加项目是从上往下添加，这里将添加到 从上往下数 的第 2 行。
    act_quit = menu.addAction("退出")   # 再次添加一个项目，它将处于从 上往下数 的第 3 行.

    tray.setContextMenu(menu)   # 将上面做好的菜单作为右键菜单，交给之前的这个系统托盘。
    tray.show()

    loop = LiveLoop(tray)
    act_quit.triggered.connect(loop._on_quit)

    def update_menu():
        if loop._recorder is not None:
            act_status.setText("状态: 录音中")
        elif loop._transcribing:
            act_status.setText("状态: 转录中")
        elif _transcriber is not None :
            act_status.setText("状态: 模型已加载")
        else:
            act_status.setText("状态: 待机")

    menu_timer = QTimer()
    menu_timer.timeout.connect(update_menu)
    menu_timer.start(500)


    logger.info("Qt 事件循环启动")
    # app.exec()--启动 Qt 的主事件循环这个方法会阻塞在这里，关闭的时候会返回一个退出码,把它交给sys.exit()
    sys.exit(app.exec())   

if __name__ == "__main__": 
    main()
