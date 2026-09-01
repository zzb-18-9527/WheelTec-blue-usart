"""串口连接管理器 (基于 pyserial)"""
import threading
import time
from typing import Callable

import serial
import serial.tools.list_ports


class SerialManager:
    def __init__(self):
        self._port: serial.Serial | None = None
        self._connected = False
        self._on_data_received: Callable[[bytes], None] | None = None
        self._reader_thread: threading.Thread | None = None
        self._running = False

    def set_data_callback(self, callback: Callable[[bytes], None]):
        self._on_data_received = callback

    @staticmethod
    def list_ports() -> list[tuple[str, str]]:
        """列出所有串口, 返回 [(description, port_name), ...]"""
        ports = serial.tools.list_ports.comports()
        return [(f"{p.description} ({p.device})", p.device) for p in ports]

    def connect(self, port_name: str, baudrate: int = 115200) -> bool:
        """连接串口"""
        try:
            self._port = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                parity=serial.PARITY_NONE,
                timeout=0.1,
            )
            self._connected = True
            self._running = True
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True
            )
            self._reader_thread.start()
            return True
        except Exception as e:
            print(f"串口连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        self._running = False
        if self._port and self._port.is_open:
            self._port.close()
        self._connected = False
        self._port = None

    def send_data(self, data: bytes) -> bool:
        if not self._port or not self._connected:
            return False
        try:
            self._port.write(data)
            return True
        except Exception as e:
            print(f"串口发送失败: {e}")
            return False

    def _read_loop(self):
        buffer = bytearray()
        while self._running and self._connected:
            try:
                if self._port and self._port.in_waiting:
                    chunk = self._port.read(self._port.in_waiting)
                    buffer.extend(chunk)

                    # 按帧分割: 寻找 7A...7B
                    while len(buffer) >= 5:
                        # 寻找帧头
                        start = -1
                        for i in range(len(buffer)):
                            if buffer[i] == 0x7A:
                                start = i
                                break
                        if start < 0:
                            buffer.clear()
                            break

                        # 寻找帧尾
                        end = -1
                        for i in range(start + 1, len(buffer)):
                            if buffer[i] == 0x7B:
                                end = i
                                break

                        if end < 0:
                            # 帧尾未找到, 保留等待
                            if start > 0:
                                buffer = buffer[start:]
                            break

                        # 提取完整帧
                        frame = bytes(buffer[start:end + 1])
                        buffer = buffer[end + 1:]

                        if self._on_data_received:
                            self._on_data_received(frame)
                else:
                    time.sleep(0.01)
            except Exception:
                if self._running:
                    time.sleep(0.05)

    @property
    def is_connected(self) -> bool:
        return self._connected
