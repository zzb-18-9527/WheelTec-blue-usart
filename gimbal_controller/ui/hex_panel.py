"""手动HEX发送面板 + 接收日志"""
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTextEdit, QLabel, QGroupBox
)
from PyQt5.QtCore import pyqtSignal, Qt


class HexPanel(QWidget):
    send_requested = pyqtSignal(bytes)  # 用户手动发送HEX

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("手动HEX面板")
        g_layout = QVBoxLayout(group)

        # 发送行
        send_row = QHBoxLayout()
        self._edit_hex = QLineEdit()
        self._edit_hex.setPlaceholderText("输入HEX数据，如: 7A02067E7B")
        self._btn_send = QPushButton("发送")
        self._btn_send.setFixedWidth(80)
        self._btn_send.clicked.connect(self._on_send)
        self._edit_hex.returnPressed.connect(self._on_send)
        send_row.addWidget(self._edit_hex)
        send_row.addWidget(self._btn_send)

        # 日志区
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(120)
        self._log.setMaximumHeight(200)

        g_layout.addLayout(send_row)
        g_layout.addWidget(QLabel("通信日志:"))
        g_layout.addWidget(self._log)

        layout.addWidget(group)

    def _on_send(self):
        text = self._edit_hex.text().strip().replace(" ", "").replace("\n", "")
        try:
            data = bytes.fromhex(text)
            self.log_send(data)
            self.send_requested.emit(data)
        except ValueError:
            self.log_system(f"无效的HEX输入: {text}")

    def log_send(self, data: bytes):
        ts = time.strftime("%H:%M:%S")
        hex_str = " ".join(f"{b:02X}" for b in data)
        self._log.append(f"[{ts}] TX: {hex_str}")

    def log_recv(self, data: bytes):
        ts = time.strftime("%H:%M:%S")
        hex_str = " ".join(f"{b:02X}" for b in data)
        self._log.append(f"[{ts}] <span style='color:#06d6a0'>RX: {hex_str}</span>")

    def log_system(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log.append(f"[{ts}] <span style='color:#f9c74f'>SYS: {msg}</span>")
