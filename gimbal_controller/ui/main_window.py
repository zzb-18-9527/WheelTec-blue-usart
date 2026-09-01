"""主窗口 - 二维云台远控程序"""
from functools import partial
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QLabel, QLineEdit, QDoubleSpinBox,
    QSpinBox, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread

from ..state.motor_state import GimbalState
from ..protocol import commands
from ..protocol.parser import parse_response, parse_mech_angle
from ..connection.command_queue import CommandQueue
from ..ui.connect_dialog import ConnectDialog
from ..ui.hex_panel import HexPanel
from ..worker.sequence_worker import SequenceWorker


class MainWindow(QMainWindow):
    def __init__(self, ble_manager, serial_manager):
        super().__init__()
        self._ble = ble_manager
        self._serial = serial_manager
        self._state = GimbalState()
        self._sequence_worker = None
        self._cmd_queue = None  # 连接后创建

        self.setWindowTitle("F32C 二维云台远控程序")
        self.setMinimumSize(800, 650)
        self._init_ui()
        self._connect_signals()

        # 定时器: 更新连接状态显示
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(500)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # ========== 顶部: 连接状态栏 ==========
        conn_bar = QHBoxLayout()
        self._lbl_conn_status = QLabel("未连接")
        self._lbl_conn_status.setObjectName("lbl_disconnected")
        self._lbl_conn_status.setProperty("class", "lbl_disconnected")
        self._btn_connect = QPushButton("连接")
        self._btn_disconnect = QPushButton("断开")
        self._btn_disconnect.setEnabled(False)
        conn_bar.addWidget(QLabel("连接状态:"))
        conn_bar.addWidget(self._lbl_conn_status)
        conn_bar.addStretch()
        conn_bar.addWidget(self._btn_connect)
        conn_bar.addWidget(self._btn_disconnect)
        root.addLayout(conn_bar)

        # ========== 主体: 三列布局 ==========
        main_row = QHBoxLayout()

        # --- 左列: 控制按钮 ---
        left_col = QGroupBox("控制操作")
        left_layout = QVBoxLayout(left_col)

        # 使能/失能
        self._btn_enable = QPushButton("使能电机")
        self._btn_enable.setObjectName("btn_enable")
        self._btn_enable.setCheckable(True)
        left_layout.addWidget(self._btn_enable)

        # 回零
        home_speed_row = QHBoxLayout()
        home_speed_row.addWidget(QLabel("回零速度:"))
        self._spin_home_speed = QSpinBox()
        self._spin_home_speed.setRange(1, 500)
        self._spin_home_speed.setValue(10)
        self._spin_home_speed.setSuffix(" RPM")
        home_speed_row.addWidget(self._spin_home_speed)
        left_layout.addLayout(home_speed_row)

        self._btn_home = QPushButton("回零 (机械0点)")
        left_layout.addWidget(self._btn_home)

        # 获取机械角度
        self._btn_get_angle = QPushButton("获取机械角度")
        left_layout.addWidget(self._btn_get_angle)

        # 保存角度 (设置01电机零点)
        self._btn_save_angle = QPushButton("保存角度 (设置01电机零点)")
        left_layout.addWidget(self._btn_save_angle)

        # 设置01电机角度
        left_layout.addWidget(QLabel("设置01电机角度 (°):"))
        self._spin_set_angle = QDoubleSpinBox()
        self._spin_set_angle.setRange(0, 359.9)
        self._spin_set_angle.setDecimals(1)
        self._spin_set_angle.setSingleStep(1.0)
        left_layout.addWidget(self._spin_set_angle)

        angle_speed_row = QHBoxLayout()
        angle_speed_row.addWidget(QLabel("旋转速度:"))
        self._spin_angle_speed = QSpinBox()
        self._spin_angle_speed.setRange(1, 500)
        self._spin_angle_speed.setValue(10)
        self._spin_angle_speed.setSuffix(" RPM")
        angle_speed_row.addWidget(self._spin_angle_speed)
        left_layout.addLayout(angle_speed_row)

        self._btn_confirm_angle = QPushButton("确认旋转")
        left_layout.addWidget(self._btn_confirm_angle)

        left_layout.addStretch()

        # --- 中列: 电机状态显示 ---
        mid_col = QGroupBox("电机状态")
        mid_layout = QVBoxLayout(mid_col)

        mid_layout.addWidget(QLabel("01电机 (X轴):"))
        self._lbl_angle_01 = QLabel("--- °")
        self._lbl_angle_01.setObjectName("lbl_angle_01")
        mid_layout.addWidget(self._lbl_angle_01)

        mid_layout.addWidget(QLabel("02电机 (Y轴):"))
        self._lbl_angle_02 = QLabel("--- °")
        self._lbl_angle_02.setObjectName("lbl_angle_02")
        mid_layout.addWidget(self._lbl_angle_02)

        mid_layout.addStretch()

        # --- 右列: X轴点动 + 运动序列 ---
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)

        # X轴点动
        jog_group = QGroupBox("X轴点动控制")
        jog_layout = QVBoxLayout(jog_group)

        jog_speed_row = QHBoxLayout()
        jog_speed_row.addWidget(QLabel("速度 (RPM):"))
        self._spin_jog_speed = QSpinBox()
        self._spin_jog_speed.setRange(1, 1000)
        self._spin_jog_speed.setValue(10)
        jog_speed_row.addWidget(self._spin_jog_speed)
        jog_layout.addLayout(jog_speed_row)

        self._btn_cw = QPushButton("X轴顺时针旋转")
        self._btn_cw.setObjectName("btn_cw")
        self._btn_ccw = QPushButton("X轴逆时针旋转")
        self._btn_ccw.setObjectName("btn_ccw")
        jog_layout.addWidget(self._btn_cw)
        jog_layout.addWidget(self._btn_ccw)
        jog_layout.addWidget(QLabel("(按下旋转，松开停止)"))

        right_layout.addWidget(jog_group)

        # 运动序列
        seq_group = QGroupBox("运动序列")
        seq_layout = QVBoxLayout(seq_group)

        seq_row1 = QHBoxLayout()
        seq_row1.addWidget(QLabel("偏转角度 (°):"))
        self._spin_offset = QDoubleSpinBox()
        self._spin_offset.setRange(0.1, 180)
        self._spin_offset.setValue(30)
        self._spin_offset.setDecimals(1)
        seq_row1.addWidget(self._spin_offset)

        seq_row1.addWidget(QLabel("速度 (RPM):"))
        self._spin_seq_speed = QSpinBox()
        self._spin_seq_speed.setRange(1, 500)
        self._spin_seq_speed.setValue(10)
        seq_row1.addWidget(self._spin_seq_speed)
        seq_layout.addLayout(seq_row1)

        seq_row2 = QHBoxLayout()
        self._btn_seq_start = QPushButton("执行运动序列")
        self._btn_seq_stop = QPushButton("停止序列")
        self._btn_seq_stop.setEnabled(False)
        seq_row2.addWidget(self._btn_seq_start)
        seq_row2.addWidget(self._btn_seq_stop)
        seq_layout.addLayout(seq_row2)

        self._lbl_seq_status = QLabel("就绪")
        seq_layout.addWidget(self._lbl_seq_status)

        right_layout.addWidget(seq_group)
        right_layout.addStretch()

        main_row.addWidget(left_col, 1)
        main_row.addWidget(mid_col, 1)
        main_row.addWidget(right_col, 1)
        root.addLayout(main_row, 1)

        # ========== 底部: HEX面板 ==========
        self._hex_panel = HexPanel()
        root.addWidget(self._hex_panel)

    def _connect_signals(self):
        self._btn_connect.clicked.connect(self._show_connect_dialog)
        self._btn_disconnect.clicked.connect(self._disconnect)
        self._btn_enable.clicked.connect(self._toggle_enable)
        self._btn_home.clicked.connect(self._home_motors)
        self._btn_get_angle.clicked.connect(self._get_mech_angles)
        self._btn_save_angle.clicked.connect(self._save_angle)
        self._btn_confirm_angle.clicked.connect(self._confirm_angle)
        self._btn_cw.pressed.connect(lambda: self._jog_start(1, 1))
        self._btn_cw.released.connect(lambda: self._jog_stop(1))
        self._btn_ccw.pressed.connect(lambda: self._jog_start(1, -1))
        self._btn_ccw.released.connect(lambda: self._jog_stop(1))
        self._btn_seq_start.clicked.connect(self._start_sequence)
        self._btn_seq_stop.clicked.connect(self._stop_sequence)
        self._hex_panel.send_requested.connect(self._send_raw)

        # 设置BLE数据回调 & 断连回调
        self._ble.set_data_callback(self._on_data_received)
        self._ble.set_disconnect_callback(self._on_ble_disconnected)
        self._serial.set_data_callback(self._on_data_received)

    # =========== 连接管理 ===========

    def _show_connect_dialog(self):
        dlg = ConnectDialog(self._ble, self._serial, self)
        dlg.connection_established.connect(self._on_connected)
        dlg.exec_()

    def _on_connected(self, conn_type, name):
        self._state.connected = True
        self._state.connection_type = conn_type
        self._state.device_name = name
        self._lbl_conn_status.setText(f"已连接 {conn_type}: {name}")
        self._lbl_conn_status.setObjectName("lbl_connected")
        self._lbl_conn_status.style().unpolish(self._lbl_conn_status)
        self._lbl_conn_status.style().polish(self._lbl_conn_status)
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)

        # 创建并启动指令队列
        if self._cmd_queue:
            self._cmd_queue.stop()
        if conn_type == "BLE":
            raw_send = self._ble.send_data
        else:
            raw_send = self._serial.send_data
        self._cmd_queue = CommandQueue(send_fn=raw_send, min_interval=0.015)
        self._cmd_queue.start()

        self._hex_panel.log_system(f"已通过{conn_type}连接: {name}")

    def _on_ble_disconnected(self):
        """BLE设备断开连接的回调(由bleak从事件循环线程调用)"""
        QTimer.singleShot(0, self._handle_ble_disconnect)

    def _handle_ble_disconnect(self):
        """在主线程处理BLE断连"""
        if not self._state.connected:
            return
        self._stop_cmd_queue()
        self._state.connected = False
        self._lbl_conn_status.setText("连接已断开(设备离线)")
        self._lbl_conn_status.setObjectName("lbl_disconnected")
        self._lbl_conn_status.style().unpolish(self._lbl_conn_status)
        self._lbl_conn_status.style().polish(self._lbl_conn_status)
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._hex_panel.log_system("BLE设备已断开连接")

    def _disconnect(self):
        try:
            if self._state.connection_type == "BLE":
                self._ble.disconnect()
            else:
                self._serial.disconnect()
        except Exception:
            pass
        self._stop_cmd_queue()
        self._state.connected = False
        self._lbl_conn_status.setText("未连接")
        self._lbl_conn_status.setObjectName("lbl_disconnected")
        self._lbl_conn_status.style().unpolish(self._lbl_conn_status)
        self._lbl_conn_status.style().polish(self._lbl_conn_status)
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._hex_panel.log_system("已断开连接")

    def _stop_cmd_queue(self):
        if self._cmd_queue:
            self._cmd_queue.stop()
            self._cmd_queue = None

    # =========== 数据收发 ===========

    def _send_command(self, data: bytes):
        """发送电机指令(通过队列串行发送)"""
        if self._cmd_queue:
            self._cmd_queue.put(data)
            self._hex_panel.log_send(data)
        else:
            self._hex_panel.log_system("未连接，无法发送")

    def _send_raw(self, data: bytes):
        """手动HEX面板发送(同样通过队列)"""
        if self._cmd_queue:
            self._cmd_queue.put(data)
        else:
            self._hex_panel.log_system("未连接，无法发送")

    def _on_data_received(self, data: bytes):
        """收到电机响应"""
        self._hex_panel.log_recv(data)
        resp = parse_response(data)
        if resp and resp.feedback_type == 0x02:  # 机械角度
            # 通过QTimer在主线程更新UI
            angle = resp.decoded_value
            QTimer.singleShot(0, partial(self._update_angle_display, resp.addr, angle))

    def _update_angle_display(self, addr, angle):
        if addr == 0x01:
            self._state.motor_01.angle = angle
            self._lbl_angle_01.setText(f"{angle:.1f}°")
        elif addr == 0x02:
            self._state.motor_02.angle = angle
            self._lbl_angle_02.setText(f"{angle:.1f}°")

    # =========== 使能/失能 ===========

    def _toggle_enable(self, checked):
        if checked:
            self._send_command(commands.enable_motor(1))
            self._send_command(commands.enable_motor(2))
            self._state.set_enabled(1, True)
            self._state.set_enabled(2, True)
            self._btn_enable.setText("失能电机")
            self._btn_enable.setProperty("motor_active", "true")
            self._hex_panel.log_system("电机已使能")
        else:
            self._send_command(commands.disable_motor(1))
            self._send_command(commands.disable_motor(2))
            self._state.set_enabled(1, False)
            self._state.set_enabled(2, False)
            self._btn_enable.setText("使能电机")
            self._btn_enable.setProperty("motor_active", "false")
            self._hex_panel.log_system("电机已失能")
        self._btn_enable.style().unpolish(self._btn_enable)
        self._btn_enable.style().polish(self._btn_enable)

    # =========== 回零 ===========

    def _home_motors(self):
        """回零: 两电机回到机械0点"""
        speed = self._spin_home_speed.value()
        self._send_command(commands.set_control_mode(1, commands.MODE_SINGLE_DIRECT))
        self._send_command(commands.set_control_mode(2, commands.MODE_SINGLE_DIRECT))
        self._send_command(commands.set_speed(1, speed))
        self._send_command(commands.set_speed(2, speed))
        self._send_command(commands.set_single_angle(1, 0.0))
        self._send_command(commands.set_single_angle(2, 0.0))
        self._hex_panel.log_system(f"回零指令已发送 (速度 {speed}RPM)")

    # =========== 获取机械角度 ===========

    def _get_mech_angles(self):
        self._send_command(commands.request_mech_angle(1))
        self._send_command(commands.request_mech_angle(2))

    # =========== 保存角度 ===========

    def _save_angle(self):
        """保存角度: 向01电机发送设置零点指令"""
        self._send_command(commands.set_single_zero_point(1))
        self._state.motor_01.zero_saved = True
        self._hex_panel.log_system("01电机零点已保存")

    # =========== 确认旋转 ===========

    def _confirm_angle(self):
        """设置01电机旋转到指定角度"""
        angle = self._spin_set_angle.value()
        speed = self._spin_angle_speed.value()
        self._send_command(commands.set_control_mode(1, commands.MODE_SINGLE_DIRECT))
        self._send_command(commands.set_speed(1, speed))
        self._send_command(commands.set_single_angle(1, angle))
        self._hex_panel.log_system(f"01电机旋转到 {angle:.1f}° (速度 {speed}RPM)")

    # =========== X轴点动 ===========

    def _jog_start(self, motor_id, direction):
        """点动开始: 切换速度模式并发送速度"""
        speed = self._spin_jog_speed.value()
        actual_speed = speed * direction
        self._send_command(commands.set_control_mode(motor_id, commands.MODE_SPEED))
        self._send_command(commands.set_speed(motor_id, actual_speed))
        self._hex_panel.log_system(f"电机{motor_id:02d} 点动{'顺时针' if direction > 0 else '逆时针'} {speed}RPM")

    def _jog_stop(self, motor_id):
        """点动停止"""
        self._send_command(commands.stop_motor(motor_id))
        self._hex_panel.log_system(f"电机{motor_id:02d} 点动停止")

    # =========== 运动序列 ===========

    def _start_sequence(self):
        if not self._state.motor_01.zero_saved:
            QMessageBox.warning(self, "提示", "请先点击\"保存角度\"设置01电机零点")
            return

        # 确保旧线程已完全结束
        if self._sequence_worker and self._sequence_worker.isRunning():
            self._sequence_worker.stop()
            self._sequence_worker.wait(5000)

        offset = self._spin_offset.value()
        speed = self._spin_seq_speed.value()

        self._sequence_worker = SequenceWorker(
            send_cmd_fn=self._send_command,
            log_fn=self._hex_panel.log_system,
            offset_angle=offset,
            speed_rpm=speed,
            on_step_complete=self._on_seq_step,
            on_all_complete=self._on_seq_complete,
        )
        # 禁用所有操作按钮，仅保留停止
        self._set_controls_enabled(False)
        self._btn_seq_stop.setEnabled(True)
        self._lbl_seq_status.setText("运动序列执行中...")
        self._sequence_worker.start()

    def _stop_sequence(self):
        if self._sequence_worker and self._sequence_worker.isRunning():
            self._sequence_worker.stop()
            self._sequence_worker.wait(5000)  # 等待线程真正结束，最多5秒
            self._hex_panel.log_system("运动序列已停止")
        self._set_controls_enabled(True)
        self._lbl_seq_status.setText("已停止")

    def _on_seq_step(self, step_name):
        self._lbl_seq_status.setText(f"执行中: {step_name}")

    def _on_seq_complete(self):
        self._set_controls_enabled(True)
        self._lbl_seq_status.setText("运动序列完成")
        self._hex_panel.log_system("运动序列全部完成")

    def _set_controls_enabled(self, enabled: bool):
        """启用/禁用所有操作按钮(运动序列执行期间锁定)"""
        controls = [
            self._btn_enable,
            self._btn_home,
            self._btn_get_angle,
            self._btn_save_angle,
            self._btn_confirm_angle,
            self._btn_cw,
            self._btn_ccw,
            self._btn_seq_start,
        ]
        for btn in controls:
            btn.setEnabled(enabled)

    # =========== 状态更新 ===========

    def _update_status(self):
        pass  # 可扩展为定期轮询角度
