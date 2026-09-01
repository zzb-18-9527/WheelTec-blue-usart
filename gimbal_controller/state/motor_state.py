"""电机状态管理"""
from dataclasses import dataclass, field


@dataclass
class MotorState:
    angle: float = 0.0         # 当前机械角度 (°)
    speed: float = 0.0         # 当前速度 (RPM)
    enabled: bool = False      # 使能状态
    mode: int = 0              # 控制模式
    zero_saved: bool = False   # 零点是否已保存


@dataclass
class GimbalState:
    motor_01: MotorState = field(default_factory=MotorState)
    motor_02: MotorState = field(default_factory=MotorState)
    connected: bool = False
    connection_type: str = ""  # "BLE" or "串口"
    device_name: str = ""

    def update_angle(self, motor_id: int, angle: float):
        if motor_id == 1:
            self.motor_01.angle = angle
        else:
            self.motor_02.angle = angle

    def set_enabled(self, motor_id: int, enabled: bool):
        if motor_id == 1:
            self.motor_01.enabled = enabled
        else:
            self.motor_02.enabled = enabled

    def set_zero_saved(self, saved: bool):
        self.motor_01.zero_saved = saved
