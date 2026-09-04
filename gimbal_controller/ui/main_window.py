"""主窗口 - 二维云台远控程序
所有操作统一发送完整指令链: 控制模式 → 速度(固定2RPM) → 目标角度
"""
from functools import partial
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QLabel, QDoubleSpinBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer

from ..state.motor_state import GimbalState
from ..protocol import commands
from ..protocol.parser import parse_response
from ..connection.command_queue import CommandQueue
from ..ui.connect_dialog import ConnectDialog
from ..ui.hex_panel import HexPanel
from ..worker.sequence_worker import SequenceWorker
from ..worker.velocity_sequence_worker import VelocitySequenceWorker

# 固定速度: 2 RPM
FIXED_SPEED = 2


class MainWindow(QMainWindow):
    def __init__(self, ble_manager, serial_manager):
        super().__init__()
        self._ble = ble_manager
        self._serial = serial_manager
        self._state = GimbalState()
        self._sequence_worker = None
        self._vel_seq_worker = None
        self._cmd_queue = None

        self.setWindowTitle("F32C 二维云台远控程序")
        self.setMinimumSize(800, 580)
        self._init_ui()
        self._connect_signals()

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

        self._btn_enable = QPushButton("使能电机")
        self._btn_enable.setObjectName("btn_enable")
        self._btn_enable.setCheckable(True)
        left_layout.addWidget(self._btn_enable)

        self._btn_home = QPushButton("回零 (机械0点)")
        left_layout.addWidget(self._btn_home)

        self._btn_get_angle = QPushButton("获取机械角度")
        left_layout.addWidget(self._btn_get_angle)

        self._btn_save_angle = QPushButton("保存角度 (设置01电机零点)")
        left_layout.addWidget(self._btn_save_angle)

        left_layout.addWidget(QLabel("设置01电机角度 (°):"))
        self._spin_set_angle = QDoubleSpinBox()
        self._spin_set_angle.setRange(0, 359.9)
        self._spin_set_angle.setDecimals(1)
        self._spin_set_angle.setSingleStep(1.0)
        left_layout.addWidget(self._spin_set_angle)
        self._btn_confirm_angle = QPushButton("确认旋转")
        left_layout.addWidget(self._btn_confirm_angle)

        left_layout.addStretch()

        # --- 中列: 电机状态 ---
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

        # --- 右列: 点动 + 运动序列 ---
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)

        jog_group = QGroupBox("X轴点动控制")
        jog_layout = QVBoxLayout(jog_group)
        self._btn_cw = QPushButton("X轴顺时针旋转")
        self._btn_cw.setObjectName("btn_cw")
        self._btn_ccw = QPushButton("X轴逆时针旋转")
        self._btn_ccw.setObjectName("btn_ccw")
        jog_layout.addWidget(self._btn_cw)
        jog_layout.addWidget(self._btn_ccw)
        jog_layout.addWidget(QLabel("(按下旋转，松开停止)"))
        right_layout.addWidget(jog_group)

        seq_group = QGroupBox("运动序列")
        seq_layout = QVBoxLayout(seq_group)

        seq_row = QHBoxLayout()
        seq_row.addWidget(QLabel("偏转角度 (°):"))
        self._spin_offset = QDoubleSpinBox()
        self._spin_offset.setRange(0.1, 180)
        self._spin_offset.setValue(30)
        self._spin_offset.setDecimals(1)
        seq_row.addWidget(self._spin_offset)
        seq_layout.addLayout(seq_row)

        seq_row_wait = QHBoxLayout()
        seq_row_wait.addWidget(QLabel("02电机等待时间 (s):"))
        self._spin_solo_wait = QDoubleSpinBox()
        self._spin_solo_wait.setRange(0.5, 10.0)
        self._spin_solo_wait.setValue(2.5)
        self._spin_solo_wait.setDecimals(1)
        self._spin_solo_wait.setSingleStep(0.5)
        seq_row_wait.addWidget(self._spin_solo_wait)
        seq_layout.addLayout(seq_row_wait)

        seq_row2 = QHBoxLayout()
        self._btn_seq_start = QPushButton("执行运动序列")
        self._btn_seq_stop = QPushButton("停止序列")
        self._btn_seq_stop.setEnabled(False)
        seq_row2.addWidget(self._btn_seq_start)
        seq_row2.addWidget(self._btn_seq_stop)
        seq_layout.addLayout(seq_row2)

        seq_row3 = QHBoxLayout()
        self._btn_vel_seq_start = QPushButton("速度运动序列")
        self._btn_vel_seq_stop = QPushButton("停止速度序列")
        self._btn_vel_seq_stop.setEnabled(False)
        seq_row3.addWidget(self._btn_vel_seq_start)
        seq_row3.addWidget(self._btn_vel_seq_stop)
        seq_layout.addLayout(seq_row3)

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
        self._btn_vel_seq_start.clicked.connect(self._start_vel_sequence)
        self._btn_vel_seq_stop.clicked.connect(self._stop_vel_sequence)
        self._hex_panel.send_requested.connect(self._send_raw)
        self._ble.set_data_callback(self._on_data_received)
        self._ble.set_disconnect_callback(self._on_ble_disconnected)
        self._serial.set_data_callback(self._on_data_received)

    # =========== 辅助: 发送完整指令链 ===========

    def _send_full_cmd(self, motor_id: int, angle: float, mode: int = commands.MODE_SINGLE_DIRECT):
        """发送完整指令链(可从工作线程安全调用): 控制模式 → 速度(2RPM) → 目标角度"""
        self._send_command_safe(commands.set_control_mode(motor_id, mode))
        self._send_command_safe(commands.set_speed(motor_id, FIXED_SPEED))
        self._send_command_safe(commands.set_single_angle(motor_id, angle))

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

        if self._cmd_queue:
            self._cmd_queue.stop()
        if conn_type == "BLE":
            self._cmd_queue = CommandQueue(
                send_fn=self._ble.send_data,
                send_async_fn=self._ble.send_data_async,
                min_interval=0.01,
            )
        else:
            self._cmd_queue = CommandQueue(
                send_fn=self._serial.send_data,
                min_interval=0.01,
            )
        self._cmd_queue.start()
        self._hex_panel.log_system(f"已通过{conn_type}连接: {name}")

    def _on_ble_disconnected(self):
        QTimer.singleShot(0, self._handle_ble_disconnect)

    def _handle_ble_disconnect(self):
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
        """发送指令并记录日志(仅从GUI线程调用)"""
        if self._cmd_queue:
            self._cmd_queue.put(data)
            self._hex_panel.log_send(data)
        else:
            self._hex_panel.log_system("未连接，无法发送")

    def _send_command_safe(self, data: bytes):
        """发送指令，不操作GUI(可从工作线程安全调用)"""
        if self._cmd_queue:
            self._cmd_queue.put(data)

    def _log_safe(self, msg: str):
        """线程安全的日志(调度到GUI线程执行)"""
        QTimer.singleShot(0, lambda: self._hex_panel.log_system(msg))

    def _send_raw(self, data: bytes):
        if self._cmd_queue:
            self._cmd_queue.put(data)
        else:
            self._hex_panel.log_system("未连接，无法发送")

    def _on_data_received(self, data: bytes):
        self._hex_panel.log_recv(data)
        resp = parse_response(data)
        if resp and resp.feedback_type == 0x02:
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
        """回零: 完整指令链 模式+速度+角度"""
        self._send_full_cmd(1, 0.0)
        self._send_full_cmd(2, 0.0)
        self._hex_panel.log_system("回零指令已发送 (模式/速度/角度)")

    # =========== 获取机械角度 ===========

    def _get_mech_angles(self):
        self._send_command(commands.request_mech_angle(1))
        self._send_command(commands.request_mech_angle(2))

    # =========== 保存角度 ===========

    def _save_angle(self):
        self._send_command(commands.set_single_zero_point(1))
        self._state.motor_01.zero_saved = True
        self._hex_panel.log_system("01电机零点已保存")

    # =========== 确认旋转 ===========

    def _confirm_angle(self):
        angle = self._spin_set_angle.value()
        self._send_full_cmd(1, angle)
        self._hex_panel.log_system(f"01电机旋转到 {angle:.1f}°")

    # =========== X轴点动 ===========

    def _jog_start(self, motor_id, direction):
        """点动: 切换速度模式 + 发送速度(正/负)"""
        speed = FIXED_SPEED * direction
        self._send_command(commands.set_control_mode(motor_id, commands.MODE_SPEED))
        self._send_command(commands.set_speed(motor_id, speed))
        self._hex_panel.log_system(f"电机{motor_id:02d} 点动{'顺时针' if direction > 0 else '逆时针'} {FIXED_SPEED}RPM")

    def _jog_stop(self, motor_id):
        self._send_command(commands.set_control_mode(motor_id, commands.MODE_SPEED))
        self._send_command(commands.set_speed(motor_id, 0))
        self._hex_panel.log_system(f"电机{motor_id:02d} 点动停止")

    # =========== 运动序列 ===========

    def _start_sequence(self):
        if not self._state.motor_01.zero_saved:
            QMessageBox.warning(self, "提示", "请先点击\"保存角度\"设置01电机零点")
            return

        if self._sequence_worker and self._sequence_worker.isRunning():
            self._sequence_worker.stop()
            self._sequence_worker.wait(5000)

        offset = self._spin_offset.value()
        solo_wait = self._spin_solo_wait.value()

        self._sequence_worker = SequenceWorker(
            send_full_cmd_fn=self._send_full_cmd,
            send_cmd_fn=self._send_command_safe,
            log_fn=self._log_safe,
            offset_angle=offset,
            solo_wait=solo_wait,
            on_step_complete=self._on_seq_step,
            on_all_complete=self._on_seq_complete,
        )
        self._set_controls_enabled(False)
        self._btn_seq_stop.setEnabled(True)
        self._lbl_seq_status.setText("运动序列执行中...")
        self._sequence_worker.start()

    def _stop_sequence(self):
        if self._sequence_worker and self._sequence_worker.isRunning():
            self._sequence_worker.stop()
            self._sequence_worker.wait(5000)
            self._hex_panel.log_system("运动序列已停止")
        self._set_controls_enabled(True)
        self._lbl_seq_status.setText("已停止")

    def _on_seq_step(self, step_name):
        self._lbl_seq_status.setText(f"执行中: {step_name}")

    def _on_seq_complete(self):
        self._set_controls_enabled(True)
        self._lbl_seq_status.setText("运动序列完成")
        self._hex_panel.log_system("运动序列全部完成")

    # =========== 速度运动序列 ===========

    def _start_vel_sequence(self):
        if self._vel_seq_worker and self._vel_seq_worker.isRunning():
            self._vel_seq_worker.stop()
            self._vel_seq_worker.wait(5000)

        offset = self._spin_offset.value()
        solo_wait = self._spin_solo_wait.value()

        self._vel_seq_worker = VelocitySequenceWorker(
            send_cmd_fn=self._send_command_safe,
            send_full_cmd_fn=self._send_full_cmd,
            log_fn=self._log_safe,
            offset_angle=offset,
            solo_wait=solo_wait,
            on_step_complete=self._on_vel_seq_step,
            on_all_complete=self._on_vel_seq_complete,
        )
        self._set_controls_enabled(False)
        self._btn_vel_seq_stop.setEnabled(True)
        self._lbl_seq_status.setText("速度运动序列执行中...")
        self._vel_seq_worker.start()

    def _stop_vel_sequence(self):
        if self._vel_seq_worker and self._vel_seq_worker.isRunning():
            self._vel_seq_worker.stop()
            self._vel_seq_worker.wait(5000)
            self._hex_panel.log_system("速度运动序列已停止")
        self._set_controls_enabled(True)
        self._lbl_seq_status.setText("已停止")

    def _on_vel_seq_step(self, step_name):
        self._lbl_seq_status.setText(f"执行中: {step_name}")

    def _on_vel_seq_complete(self):
        self._set_controls_enabled(True)
        self._lbl_seq_status.setText("速度运动序列完成")
        self._hex_panel.log_system("速度运动序列全部完成")

    def _set_controls_enabled(self, enabled: bool):
        controls = [
            self._btn_enable, self._btn_home, self._btn_get_angle,
            self._btn_save_angle, self._btn_confirm_angle,
            self._btn_cw, self._btn_ccw,
            self._btn_seq_start, self._btn_vel_seq_start,
        ]
        for btn in controls:
            btn.setEnabled(enabled)

    def _update_status(self):
        pass
