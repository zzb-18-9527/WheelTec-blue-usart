"""BLE / 串口 连接对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QPushButton, QComboBox, QLabel, QProgressBar, QLineEdit,
    QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread


class BLEScanThread(QThread):
    devices_found = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, ble_manager):
        super().__init__()
        self._ble = ble_manager

    def run(self):
        try:
            result = self._ble.scan_devices(timeout=6.0)
            self.devices_found.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class BLEConnectThread(QThread):
    result = pyqtSignal(bool)

    def __init__(self, ble_manager, address):
        super().__init__()
        self._ble = ble_manager
        self._addr = address

    def run(self):
        try:
            ok = self._ble.connect(self._addr)
            self.result.emit(ok)
        except Exception as e:
            print(f"BLE连接线程异常: {e}")
            self.result.emit(False)


class ConnectDialog(QDialog):
    connection_established = pyqtSignal(str, str)

    def __init__(self, ble_manager, serial_manager, parent=None):
        super().__init__(parent)
        self._ble = ble_manager
        self._serial = serial_manager
        self._scan_thread = None
        self._connect_thread = None
        self.setWindowTitle("连接设备")
        self.setMinimumWidth(520)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()

        # ===== BLE 标签页 =====
        ble_tab = QWidget()
        ble_layout = QVBoxLayout(ble_tab)

        # 扫描区
        scan_row = QHBoxLayout()
        self._lbl_ble_status = QLabel("未扫描")
        self._btn_scan = QPushButton("扫描BLE设备")
        self._btn_scan.clicked.connect(self._start_scan)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        scan_row.addWidget(self._lbl_ble_status)
        scan_row.addWidget(self._btn_scan)
        ble_layout.addLayout(scan_row)
        ble_layout.addWidget(self._progress)

        # 设备列表
        self._combo_ble = QComboBox()
        self._combo_ble.setMinimumWidth(400)
        ble_layout.addWidget(QLabel("发现的设备:"))
        ble_layout.addWidget(self._combo_ble)

        # 连接按钮
        self._btn_ble_connect = QPushButton("连接")
        self._btn_ble_connect.clicked.connect(self._ble_connect)
        ble_layout.addWidget(self._btn_ble_connect)
        ble_layout.addStretch()

        # ===== 串口标签页 =====
        serial_tab = QWidget()
        serial_layout = QVBoxLayout(serial_tab)
        self._combo_ports = QComboBox()
        self._btn_refresh = QPushButton("刷新串口列表")
        self._btn_refresh.clicked.connect(self._refresh_ports)
        self._btn_serial_connect = QPushButton("连接")
        self._btn_serial_connect.clicked.connect(self._serial_connect)
        self._edit_baudrate = QLineEdit("115200")
        self._edit_baudrate.setMaximumWidth(120)

        baud_layout = QHBoxLayout()
        baud_layout.addWidget(QLabel("波特率:"))
        baud_layout.addWidget(self._edit_baudrate)
        baud_layout.addStretch()

        serial_layout.addWidget(self._btn_refresh)
        serial_layout.addWidget(QLabel("可用串口:"))
        serial_layout.addWidget(self._combo_ports)
        serial_layout.addLayout(baud_layout)
        serial_layout.addWidget(self._btn_serial_connect)

        # 提示
        hint = QLabel("提示: HC-04蓝牙模块默认波特率为 9600")
        hint.setStyleSheet("color: #f9c74f;")
        serial_layout.addWidget(hint)
        serial_layout.addStretch()

        self._tabs.addTab(ble_tab, "BLE连接")
        self._tabs.addTab(serial_tab, "串口连接")
        layout.addWidget(self._tabs)

        self._refresh_ports()

    # ===== BLE 扫描 =====

    def _start_scan(self):
        self._btn_scan.setEnabled(False)
        self._lbl_ble_status.setText("正在扫描...")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._combo_ble.clear()
        self._ble.start_event_loop()
        self._scan_thread = BLEScanThread(self._ble)
        self._scan_thread.devices_found.connect(self._on_scan_done)
        self._scan_thread.error.connect(self._on_scan_error)
        self._scan_thread.start()

    def _on_scan_done(self, devices):
        self._progress.setVisible(False)
        self._btn_scan.setEnabled(True)
        count = 0
        for name, addr in devices:
            if name == "未知设备":
                continue
            self._combo_ble.addItem(f"{name}  [{addr}]", addr)
            count += 1
        self._lbl_ble_status.setText(f"发现 {count} 个有效设备")

    def _on_scan_error(self, err):
        self._progress.setVisible(False)
        self._btn_scan.setEnabled(True)
        self._lbl_ble_status.setText(f"扫描失败: {err}")

    # ===== BLE 连接 =====

    def _ble_connect(self):
        addr = self._combo_ble.currentData()
        if not addr:
            QMessageBox.warning(self, "提示", "请先扫描并选择设备")
            return
        self._btn_ble_connect.setEnabled(False)
        self._lbl_ble_status.setText(f"正在连接 {addr}...")
        self._connect_thread = BLEConnectThread(self._ble, addr)
        self._connect_thread.result.connect(self._on_ble_connected)
        self._connect_thread.start()

    def _on_ble_connected(self, ok):
        self._btn_ble_connect.setEnabled(True)
        if ok:
            # 自动选择最后一个可写特征并完成连接
            write_uuid = self._ble.write_uuid
            name = self._combo_ble.currentText()
            self._lbl_ble_status.setText(
                f"已连接，写特征: {write_uuid or '无'}"
            )
            self.connection_established.emit("BLE", name)
            self.accept()
        else:
            self._lbl_ble_status.setText("连接失败，请重试")

    # ===== 串口连接 =====

    def _refresh_ports(self):
        self._combo_ports.clear()
        for desc, port in self._serial.list_ports():
            self._combo_ports.addItem(f"{desc} [{port}]", port)

    def _serial_connect(self):
        port = self._combo_ports.currentData()
        if not port:
            QMessageBox.warning(self, "提示", "没有可用串口")
            return
        baudrate = int(self._edit_baudrate.text() or "115200")
        if self._serial.connect(port, baudrate):
            self.connection_established.emit("串口", port)
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "串口连接失败")
