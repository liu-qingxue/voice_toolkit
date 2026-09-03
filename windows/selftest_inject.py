"""
SendInput 注入自证测试 —— 验证"核心前端"(光标注入)是否真实生效。

原理: 自己开一个 Qt 窗口(含可输入文本框), 置顶激活 → 用 run_hotkey 里同一套
_send_input_text 注入测试文本 → 从文本框读回内容, 与目标逐字符对比。
能读回 = SendInput 真把字符送进了窗口(而不是"自认为成功")。

跑法(前台, 会弹一个测试窗, 数秒后自动关闭):
    venv\\Scripts\\python windows\\selftest_inject.py
退出码: 0=注入验证通过  1=失败
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QTextEdit, QWidget

from run_hotkey import _send_input_text

# 含中文/大写/数字/特殊字符/换行(换行应被转换成回车键)
TARGET = "这是一段测试转录文本 ABC 123 !@#\n第二行 Xyz"

app = QApplication(sys.argv)

win = QWidget()
win.setWindowTitle("voice_toolkit SendInput 自证")
win.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)   # 置顶, 减少被盖
win.resize(480, 220)
editor = QTextEdit(win)
editor.setGeometry(10, 10, 460, 200)
win.show()

results: dict = {}


def step_activate():
    win.raise_()
    win.activateWindow()          # 激活 + 抢键盘焦点
    editor.setFocus()
    app.processEvents()


def step_inject():
    results["n_sent"] = _send_input_text(TARGET)
    print(f"[selftest] SendInput 调用返回: {results['n_sent']}")


def step_readback():
    got = editor.toPlainText()
    ok = (got == TARGET)
    print(f"[selftest] 读回 {len(got)} 字符")
    print(f"[selftest] 目标: {TARGET!r}")
    print(f"[selftest] 读回: {got!r}")
    print(f"[selftest] {'[PASS] SendInput 注入真实生效' if ok else '[FAIL] 读回与目标不一致'}")
    results["ok"] = ok
    app.quit()


# 时序链: 显示→稳定→激活→注入→读回
QTimer.singleShot(700, step_activate)
QTimer.singleShot(1100, step_inject)
QTimer.singleShot(2100, step_readback)

# 兜底超时(10s), 防止异常情况挂死
QTimer.singleShot(10000, lambda: (print("[selftest] 超时退出"), app.quit()))

app.exec()
sys.exit(0 if results.get("ok") else 1)
