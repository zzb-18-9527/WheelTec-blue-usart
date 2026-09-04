"""速度运动序列后台执行器

01电机: 速度模式，通过 角速度×时间 估算角度偏移
02电机: 位置模式（单圈绝对直通），精确角度控制
固定速度2RPM = 12°/s
"""
import time
from typing import Callable
from PyQt5.QtCore import QThread, pyqtSignal

from ..protocol import commands

FIXED_SPEED = 2
DEG_PER_SEC = 360.0 * FIXED_SPEED / 60.0  # 12°/s


class VelocitySequenceWorker(QThread):
    step_complete = pyqtSignal(str)
    all_complete = pyqtSignal()

    def __init__(
        self,
        send_cmd_fn: Callable[[bytes], None],
        send_full_cmd_fn: Callable[[int, float], None],
        log_fn: Callable[[str], None],
        offset_angle: float,
        solo_wait: float = 2.5,
        on_step_complete: Callable[[str], None] | None = None,
        on_all_complete: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._send = send_cmd_fn
        self._send_full = send_full_cmd_fn
        self._log = log_fn
        self._offset = offset_angle
        self._move_time = offset_angle / DEG_PER_SEC
        self._running = True
        self._pos_wait = 3.0
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
            self._log(f"速度序列异常: {e}")

    def stop(self):
        self._running = False

    def _send_cmd(self, data: bytes):
        if self._running:
            self._send(data)

    # ---- 01电机: 速度模式 ----

    def _run_motor01(self, direction: int):
        speed = FIXED_SPEED * direction
        self._send_cmd(commands.set_control_mode(1, commands.MODE_SPEED))
        self._send_cmd(commands.set_speed(1, speed))

    def _stop_motor01(self):
        self._send_cmd(commands.set_control_mode(1, commands.MODE_SPEED))
        self._send_cmd(commands.set_speed(1, 0))

    # ---- 02电机: 位置模式 ----

    def _move_motor02(self, angle: float):
        """T型位置模式移动02电机到指定角度"""
        self._send_full(2, angle, mode=commands.MODE_SINGLE_T)

    # ---- 等待 ----

    def _wait(self, seconds: float):
        step = 0.05
        elapsed = 0.0
        while elapsed < seconds and self._running:
            time.sleep(step)
            elapsed += step

    # ---- 单轴运动(01速度模式) ----

    def _do_01_velocity_move(self, direction: int, label: str):
        """01电机速度模式偏转+归零，02电机保持0°"""
        if not self._running:
            return
        dir_label = "顺" if direction > 0 else "逆"
        self._send_full(2, 0.0)
        self._log(f"  01电机{dir_label}偏转 {self._move_time:.1f}s (速度2RPM), 02保持0°(速度2RPM)")
        self._run_motor01(direction)
        self._wait(self._move_time)
        self._stop_motor01()
        self._wait(0.3)

        if not self._running:
            return
        self._send_full(2, 0.0)
        self._log(f"  01电机归零 {self._move_time:.1f}s (速度2RPM), 02保持0°(速度2RPM)")
        self._run_motor01(-direction)
        self._wait(self._move_time)
        self._stop_motor01()
        self._wait(0.3)

    # ---- 单轴运动(02位置模式) ----

    def _do_02_position_move(self, direction: int, label: str):
        """02电机位置模式偏转+归零"""
        if not self._running:
            return
        dir_label = "顺" if direction > 0 else "逆"
        angle = self._offset if direction > 0 else (360 - self._offset)
        self._log(f"  02电机{dir_label}偏转 {self._offset}°→{angle:.1f}° (位置模式, 速度2RPM)")
        self._move_motor02(angle)
        self._wait(self._solo_wait)

        if not self._running:
            return
        self._log(f"  02电机归零 0° (位置模式, 速度2RPM)")
        self._move_motor02(0.0)
        self._wait(self._solo_wait)

    # ---- 组合运动 ----

    def _do_combo_move(self, m1_dir: int, m2_dir: int, label: str):
        """01速度模式 + 02位置模式 同时偏转+归零，指令交替发送"""
        if not self._running:
            return
        m2_angle = self._offset if m2_dir > 0 else (360 - self._offset)
        m1_speed = FIXED_SPEED * m1_dir
        self._log(f"  {label} 偏转: 01速度{self._move_time:.1f}s(2RPM), 02位置{m2_angle:.1f}°(2RPM)")
        self._send_cmd(commands.set_control_mode(1, commands.MODE_SPEED))
        self._send_cmd(commands.set_control_mode(2, commands.MODE_SINGLE_T))
        self._send_cmd(commands.set_speed(1, m1_speed))
        self._send_cmd(commands.set_speed(2, FIXED_SPEED))
        self._send_cmd(commands.set_single_angle(2, m2_angle))
        self._wait(self._move_time)
        self._stop_motor01()
        self._wait(0.3)

        if not self._running:
            return
        self._log(f"  归零: 01速度{self._move_time:.1f}s(2RPM), 02位置0°(2RPM)")
        self._send_cmd(commands.set_control_mode(1, commands.MODE_SPEED))
        self._send_cmd(commands.set_control_mode(2, commands.MODE_SINGLE_T))
        self._send_cmd(commands.set_speed(1, -m1_speed))
        self._send_cmd(commands.set_speed(2, FIXED_SPEED))
        self._send_cmd(commands.set_single_angle(2, 0.0))
        self._wait(self._move_time)
        self._stop_motor01()
        self._wait(0.3)

    def _execute_steps(self):
        self._log(f"=== 混合序列: {self._offset}° (01速度/02位置) ===")

        # 阶段1: 单轴
        if self._running:
            self.step_complete.emit("步骤1: 01顺时针(速度)")
            self._log("步骤1: 02保持0°, 01顺时针偏转(速度模式)")
            self._do_01_velocity_move(1, "顺")

        if self._running:
            self.step_complete.emit("步骤2: 01逆时针(速度)")
            self._log("步骤2: 02保持0°, 01逆时针偏转(速度模式)")
            self._do_01_velocity_move(-1, "逆")

        if self._running:
            self.step_complete.emit("步骤3: 02顺时针(位置)")
            self._log("步骤3: 01保持不动, 02顺时针偏转(位置模式)")
            self._do_02_position_move(1, "顺")

        if self._running:
            self.step_complete.emit("步骤4: 02逆时针(位置)")
            self._log("步骤4: 01保持不动, 02逆时针偏转(位置模式)")
            self._do_02_position_move(-1, "逆")

        self._log("=== 阶段2: 组合运动 ===")

        combos = [
            ("步骤5: 01顺+02顺", 1, 1),
            ("步骤6: 01顺+02逆", 1, -1),
            ("步骤7: 01逆+02顺", -1, 1),
            ("步骤8: 01逆+02逆", -1, -1),
        ]
        for name, d1, d2 in combos:
            if not self._running:
                return
            self.step_complete.emit(name)
            self._log(name)
            self._do_combo_move(d1, d2, name.split(":")[1].strip())
