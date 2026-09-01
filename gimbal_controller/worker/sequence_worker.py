"""运动序列后台执行器

执行流程:
  阶段1 - 单轴运动 (4步):
    1. 02保持0°, 01顺时针偏转 → 01回零
    2. 02保持0°, 01逆时针偏转 → 01回零
    3. 01保持0°, 02顺时针偏转 → 02回零
    4. 01保持0°, 02逆时针偏转 → 02回零
  阶段2 - 组合运动 (4步):
    5. 01顺+02顺 → 双回零
    6. 01顺+02逆 → 双回零
    7. 01逆+02顺 → 双回零
    8. 01逆+02逆 → 双回零
"""
import time
from typing import Callable
from PyQt5.QtCore import QThread, pyqtSignal

from ..protocol import commands


class SequenceWorker(QThread):
    step_complete = pyqtSignal(str)   # 当前步骤名称
    all_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        send_cmd_fn: Callable[[bytes], None],
        log_fn: Callable[[str], None],
        offset_angle: float,
        speed_rpm: int,
        on_step_complete: Callable[[str], None] | None = None,
        on_all_complete: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._send = send_cmd_fn
        self._log = log_fn
        self._offset = offset_angle
        self._speed = speed_rpm
        self._running = True

        self._cmd_interval = 0.015   # 指令间间隔 (秒)
        self._action_wait = 3.0      # 等待电机到达目标 (秒)
        self._return_wait = 3.0      # 等待回零完成 (秒)

        if on_step_complete:
            self.step_complete.connect(on_step_complete)
        if on_all_complete:
            self.all_complete.connect(on_all_complete)

    def run(self):
        try:
            self._setup_motors()
            self._execute_steps()
            if self._running:
                self.all_complete.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self._running = False

    def _send_cmd(self, data: bytes):
        if not self._running:
            return
        self._send(data)
        time.sleep(self._cmd_interval)

    def _setup_motors(self):
        """初始化: 切换单圈绝对模式(直通) + 设定速度"""
        self._log("序列初始化: 设置单圈绝对模式(直通)")
        self._send_cmd(commands.set_control_mode(1, commands.MODE_SINGLE_DIRECT))
        self._send_cmd(commands.set_control_mode(2, commands.MODE_SINGLE_DIRECT))
        self._send_cmd(commands.set_speed(1, self._speed))
        self._send_cmd(commands.set_speed(2, self._speed))

    def _move_to(self, motor_id: int, angle: float, label: str):
        """移动电机到指定角度并等待"""
        if not self._running:
            return
        self._send_cmd(commands.set_single_angle(motor_id, angle))
        self._log(f"  电机{motor_id:02d} → {angle:.1f}°")
        self._wait(self._action_wait)

    def _return_zero(self, motor_id: int):
        """电机回零"""
        if not self._running:
            return
        self._send_cmd(commands.set_single_angle(motor_id, 0.0))
        self._log(f"  电机{motor_id:02d} → 回零 0°")
        self._wait(self._return_wait)

    def _wait(self, seconds: float):
        """可中断等待"""
        step = 0.1
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(step)
            elapsed += step

    def _execute_steps(self):
        offset = self._offset
        cw_angle = offset        # 顺时针偏转: 0 + offset
        ccw_angle = 360 - offset  # 逆时针偏转: 360 - offset

        # ===== 阶段1: 单轴运动 =====
        self._log("=== 阶段1: 单轴运动 ===")

        # 步骤1: 02保持0°, 01顺时针
        if self._running:
            self.step_complete.emit("步骤1: 01顺时针偏转")
            self._log("步骤1: 01顺时针偏转")
            self._move_to(1, cw_angle, "01顺时针")
            self._return_zero(1)

        # 步骤2: 02保持0°, 01逆时针
        if self._running:
            self.step_complete.emit("步骤2: 01逆时针偏转")
            self._log("步骤2: 01逆时针偏转")
            self._move_to(1, ccw_angle, "01逆时针")
            self._return_zero(1)

        # 步骤3: 01保持0°, 02顺时针
        if self._running:
            self.step_complete.emit("步骤3: 02顺时针偏转")
            self._log("步骤3: 02顺时针偏转")
            self._move_to(2, cw_angle, "02顺时针")
            self._return_zero(2)

        # 步骤4: 01保持0°, 02逆时针
        if self._running:
            self.step_complete.emit("步骤4: 02逆时针偏转")
            self._log("步骤4: 02逆时针偏转")
            self._move_to(2, ccw_angle, "02逆时针")
            self._return_zero(2)

        # ===== 阶段2: 组合运动 =====
        self._log("=== 阶段2: 组合运动 ===")

        combos = [
            ("步骤5: 01顺+02顺", cw_angle, cw_angle),
            ("步骤6: 01顺+02逆", cw_angle, ccw_angle),
            ("步骤7: 01逆+02顺", ccw_angle, cw_angle),
            ("步骤8: 01逆+02逆", ccw_angle, ccw_angle),
        ]

        for step_name, a1, a2 in combos:
            if not self._running:
                break
            self.step_complete.emit(step_name)
            self._log(step_name)
            # 同时发送两电机目标角度
            self._send_cmd(commands.set_single_angle(1, a1))
            self._send_cmd(commands.set_single_angle(2, a2))
            self._log(f"  电机01 → {a1:.1f}°, 电机02 → {a2:.1f}°")
            self._wait(self._action_wait)

            if not self._running:
                break
            # 双回零
            self._send_cmd(commands.set_single_angle(1, 0.0))
            self._send_cmd(commands.set_single_angle(2, 0.0))
            self._log("  双电机回零 0°")
            self._wait(self._return_wait)
