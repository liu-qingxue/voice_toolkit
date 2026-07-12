from PyQt6.QtCore import QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)
from config.config import CFG


_DELAY = CFG.window_popup_copy_delay
_FADE = CFG.window_popup_fade_ms


class TranscriptionPopup(QWidget):
    def __init__(self, text: str):
        super().__init__()
        self._anim: QPropertyAnimation | None = None
        self.setWindowTitle("转录结果")
        self.setFixedSize(500, 350)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.addStretch()
        copy_btn = QPushButton("复制")
        copy_btn.setFixedSize(60, 26)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(lambda: self._copy(text, copy_btn))
        top.addWidget(copy_btn)
        layout.addLayout(top)

        editor = QTextEdit(self)
        editor.setPlainText(text)
        editor.setReadOnly(True)
        layout.addWidget(editor, 1)

        self.show()

    def _copy(self, text: str, btn: QPushButton):
        QApplication.clipboard().setText(text)
        btn.setText("已复制 ✓")
        btn.setStyleSheet("background-color: #4CAF50; color: white;")
        btn.setEnabled(False)
        QTimer.singleShot(_DELAY, self._fade_out)

    def _fade_out(self):
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(_FADE)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.close)
        self._anim.start()
