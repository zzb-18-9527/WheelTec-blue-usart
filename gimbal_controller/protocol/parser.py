"""F32C 电机协议响应解析器

响应格式: 7A + 地址 + 数据反馈类型 + 高16位 + 低16位 + BCC + 7B
"""
from dataclasses import dataclass
from .bcc import compute_bcc


@dataclass
class MotorResponse:
    addr: int
    feedback_type: int
    raw_value: int
    decoded_value: float


def parse_response(data: bytes) -> MotorResponse | None:
    """解析电机响应帧, 格式错误返回None"""
    if len(data) < 8:
        return None
    if data[0] != 0x7A or data[-1] != 0x7B:
        return None

    addr = data[1]
    fb_type = data[2]
    high16 = (data[3] << 8) | data[4]
    low16 = (data[5] << 8) | data[6]
    raw = (high16 << 16) | low16

    # 校验BCC
    expected_bcc = compute_bcc(data[:-2])
    if expected_bcc != data[-2]:
        return None

    # 解码值 (根据反馈类型)
    decoded = _decode_value(fb_type, raw)

    return MotorResponse(
        addr=addr,
        feedback_type=fb_type,
        raw_value=raw,
        decoded_value=decoded,
    )


def _decode_value(fb_type: int, raw: int) -> float:
    """根据反馈类型解码原始值"""
    if fb_type == 0x00:  # 速度反馈
        return _to_signed16(raw & 0xFFFF) / 1.0  # RPM, 无需缩放
    elif fb_type == 0x01:  # 转过总角度
        return _to_signed32(raw) / 10.0
    elif fb_type == 0x02:  # 机械角度
        return (raw & 0xFFFF) / 10.0  # 0~359.9°
    elif fb_type == 0x03:  # 加速度
        return raw / 1.0  # 转/s²
    elif fb_type == 0x04:  # 母线电压
        return raw / 100.0  # V
    return float(raw)


def _to_signed16(val: int) -> int:
    if val >= 0x8000:
        val -= 0x10000
    return val


def _to_signed32(val: int) -> int:
    if val >= 0x80000000:
        val -= 0x100000000
    return val


def parse_mech_angle(data: bytes) -> float | None:
    """解析机械角度反馈, 失败返回None"""
    resp = parse_response(data)
    if resp and resp.feedback_type == 0x02:
        return resp.decoded_value
    return None
