"""F32C 电机协议指令生成器

帧格式: 7A + 地址 + 功能码 + [数据] + BCC校验 + 7B
BCC: 对 7A到数据区所有字节 逐字节XOR
"""
from .bcc import compute_bcc


def _build_frame(addr: int, func_code: int, data: bytes = b"") -> bytes:
    """构造完整协议帧"""
    body = bytes([0x7A, addr, func_code]) + data
    bcc = compute_bcc(body)
    return body + bytes([bcc, 0x7B])


# ============ 使能 / 失能 ============

def enable_motor(motor_id: int) -> bytes:
    """使能电机 (功能码06, 固定校验)"""
    if motor_id == 1:
        return bytes([0x7A, 0x01, 0x06, 0x7D, 0x7B])
    return bytes([0x7A, 0x02, 0x06, 0x7E, 0x7B])


def disable_motor(motor_id: int) -> bytes:
    """失能电机 (功能码05, 固定校验)"""
    if motor_id == 1:
        return bytes([0x7A, 0x01, 0x05, 0x7C, 0x7B])
    return bytes([0x7A, 0x02, 0x05, 0x7D, 0x7B])


# ============ 控制模式 ============

MODE_SPEED = 0x0000
MODE_MULTI_T = 0x0001
MODE_SINGLE_T = 0x0002
MODE_MULTI_DIRECT = 0x0003
MODE_SINGLE_DIRECT = 0x0004


def set_control_mode(motor_id: int, mode: int) -> bytes:
    """设置控制模式 (功能码00)"""
    high = (mode >> 8) & 0xFF
    low = mode & 0xFF
    return _build_frame(motor_id, 0x00, bytes([high, low]))


# ============ 速度控制 ============

def set_speed(motor_id: int, speed_rpm: int) -> bytes:
    """设置目标速度 (功能码01)
    正值=正转, 负值=反转(补码)
    """
    if speed_rpm >= 0:
        high = (speed_rpm >> 8) & 0xFF
        low = speed_rpm & 0xFF
    else:
        # 16位补码
        val = speed_rpm & 0xFFFF
        high = (val >> 8) & 0xFF
        low = val & 0xFF
    return _build_frame(motor_id, 0x01, bytes([high, low]))


def stop_motor(motor_id: int) -> bytes:
    """停止电机 (速度设为0)"""
    return set_speed(motor_id, 0)


# ============ 单圈绝对角度控制 ============

def set_single_angle(motor_id: int, angle_deg: float) -> bytes:
    """单圈绝对角度控制 (功能码03)
    角度范围 0~359.9°, 放大10倍发送
    """
    angle_int = int(round(angle_deg * 10)) & 0xFFFF
    high = (angle_int >> 8) & 0xFF
    low = angle_int & 0xFF
    return _build_frame(motor_id, 0x03, bytes([high, low]))


# ============ 多圈绝对角度控制 ============

def set_multi_angle(motor_id: int, angle_deg: float) -> bytes:
    """多圈绝对角度控制 (功能码02)
    放大10倍发送, 4字节数据
    """
    angle_int = int(round(angle_deg * 10))
    d1 = (angle_int >> 24) & 0xFF
    d2 = (angle_int >> 16) & 0xFF
    d3 = (angle_int >> 8) & 0xFF
    d4 = angle_int & 0xFF
    return _build_frame(motor_id, 0x02, bytes([d1, d2, d3, d4]))


# ============ 数据反馈请求 ============

FEEDBACK_SPEED = 0x00
FEEDBACK_TOTAL_ANGLE = 0x01
FEEDBACK_MECH_ANGLE = 0x02
FEEDBACK_ACCELERATION = 0x03
FEEDBACK_VOLTAGE = 0x04


def request_feedback(motor_id: int, feedback_type: int) -> bytes:
    """请求数据反馈 (功能码0E)"""
    return _build_frame(motor_id, 0x0E, bytes([feedback_type]))


def request_mech_angle(motor_id: int) -> bytes:
    """请求机械角度"""
    return request_feedback(motor_id, FEEDBACK_MECH_ANGLE)


# ============ 单圈绝对角度设置零点 ============

def set_single_zero_point(motor_id: int) -> bytes:
    """将当前位置设置为单圈绝对角度0点 (功能码0A)
    可掉电保存
    """
    return _build_frame(motor_id, 0x0A)


# ============ 加速度控制 ============

def set_acceleration(motor_id: int, accel: int) -> bytes:
    """设置加速度 (功能码07)"""
    high = (accel >> 8) & 0xFF
    low = accel & 0xFF
    return _build_frame(motor_id, 0x07, bytes([high, low]))


# ============ 参数保存 ============

def save_params(motor_id: int) -> bytes:
    """保存参数 (功能码08)"""
    return _build_frame(motor_id, 0x08)
