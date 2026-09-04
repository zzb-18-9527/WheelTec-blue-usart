"""运动序列后台执行器

每个动作均发送完整指令链: 控制模式 → 速度(2RPM) → 目标角度
"""
import time
from typing import Callable
from PyQt5.QtCore import QThread, pyqtSignal

from ..protocol import commands

FIXED_SPEED = 2


class SequenceWorker(QThread):
    step_complete = pyqtSignal(str)
    all_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        send_full_cmd_fn: Callable[[int, float], None],
        send_cmd_fn: Callable[[bytes], None],
        log_fn: Callable[[str], None],
        offset_angle: float,
        solo_wait: float = 2.5,
        on_step_complete: Callable[[str], None] | None = None,
        on_all_complete: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._send_full = send_full_cmd_fn
        self._send_cmd = send_cmd_fn
        self._log = log_fn
        self._offset = offset_angle
        self._running = True
        self._action_wait = 3.0
        self._return_wait = 3.0
        self._solo_wait = solo_wait

        if on_step_complete:
            self.step_complete.connect(on_step_complete)
        if on_all_complete:
            self.all_complete.connect(on_all_complete)

    def run(self):
        try:
            self._execute_steps()
            if self._running:
                self.all_complete.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self._running = False

    def _move_to(self, motor_id: int, angle: float, label: str, wait: float = None, mode: int = None):
        if not self._running:
            return
        self._send_full(motor_id, angle, mode=mode or commands.MODE_SINGLE_DIRECT)
        self._log(f"  电机{motor_id:02d} → {angle:.1f}°")
        self._wait(wait if wait is not None else self._action_wait)

    def _move_to_dual(self, angle1: float, angle2: float):
        """双电机交替发送指令，01直通模式，02T型模式"""
        self._send_cmd(commands.set_control_mode(1, commands.MODE_SINGLE_DIRECT))
        self._send_cmd(commands.set_control_mode(2, commands.MODE_SINGLE_T))
        self._send_cmd(commands.set_speed(1, FIXED_SPEED))
        self._send_cmd(commands.set_speed(2, FIXED_SPEED))
        self._send_cmd(commands.set_single_angle(1, angle1))
        self._send_cmd(commands.set_single_angle(2, angle2))

    def _return_zero(self, motor_id: int, wait: float = None, mode: int = None):
        if not self._running:
            return
        self._send_full(motor_id, 0.0, mode=mode or commands.MODE_SINGLE_DIRECT)
        self._log(f"  电机{motor_id:02d} → 回零 0°")
        self._wait(wait if wait is not None else self._return_wait)

    def _wait(self, seconds: float):
        step = 0.1
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(step)
            elapsed += step

    def _execute_steps(self):
        offset = self._offset
        cw_angle = offset
        ccw_angle = 360 - offset

        self._log("=== 阶段1: 单轴运动 ===")

        if self._running:
            self.step_complete.emit("步骤1: 01顺时针偏转")
            self._log("步骤1: 02保持0°, 01顺时针偏转")
            self._move_to(1, cw_angle, "01顺时针")
            self._return_zero(1)

        if self._running:
            self.step_complete.emit("步骤2: 01逆时针偏转")
            self._log("步骤2: 02保持0°, 01逆时针偏转")
            self._move_to(1, ccw_angle, "01逆时针")
            self._return_zero(1)

        if self._running:
            self.step_complete.emit("步骤3: 02顺时针偏转")
            self._log("步骤3: 01保持0°, 02顺时针偏转(T型)")
            self._move_to(2, cw_angle, "02顺时针", wait=self._solo_wait, mode=commands.MODE_SINGLE_T)
            self._return_zero(2, wait=self._solo_wait, mode=commands.MODE_SINGLE_T)

        if self._running:
            self.step_complete.emit("步骤4: 02逆时针偏转")
            self._log("步骤4: 01保持0°, 02逆时针偏转(T型)")
            self._move_to(2, ccw_angle, "02逆时针", wait=self._solo_wait, mode=commands.MODE_SINGLE_T)
            self._return_zero(2, wait=self._solo_wait, mode=commands.MODE_SINGLE_T)

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
            self._move_to_dual(a1, a2)
            self._log(f"  电机01 → {a1:.1f}°, 电机02 → {a2:.1f}°")
            self._wait(self._action_wait)

            if not self._running:
                break
            self._move_to_dual(0.0, 0.0)
            self._log("  双电机回零 0°")
            self._wait(self._return_wait)
