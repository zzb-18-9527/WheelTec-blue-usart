"""BLE 连接管理器 (基于 bleak)

所有 BLE 操作统一在同一个后台事件循环中执行。
连接后自动发现可写特征，支持手动指定特征UUID。
"""
import asyncio
import threading
from typing import Callable
from concurrent.futures import Future

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

# Nordic UART Service UUIDs (常见)
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


class BLEManager:
    def __init__(self):
        self._client: BleakClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._write_uuid: str | None = None
        self._notify_uuid: str | None = None
        self._on_data_received: Callable[[bytes], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None
        self._connected = False
        self._device_name = ""
        self._discovered_services: list[dict] = []

    def start_event_loop(self):
        if self._thread and self._thread.is_alive():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def stop_event_loop(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=3)
            self._loop.close()
            self._loop = None
            self._thread = None

    def set_data_callback(self, callback: Callable[[bytes], None]):
        self._on_data_received = callback

    def set_disconnect_callback(self, callback: Callable[[], None]):
        self._on_disconnect = callback

    def _run_coro_sync(self, coro, timeout=15.0):
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("BLE事件循环未启动")
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ---- 扫描 ----

    async def _scan(self, timeout: float) -> list[tuple[str, str]]:
        devices = await BleakScanner.discover(timeout=timeout)
        result = []
        for d in devices:
            name = d.name or "未知设备"
            result.append((name, d.address))
        return result

    def scan_devices(self, timeout: float = 5.0) -> list[tuple[str, str]]:
        return self._run_coro_sync(self._scan(timeout), timeout=timeout + 5)

    # ---- 连接 ----

    async def _connect(self, address: str) -> bool:
        try:
            self._client = BleakClient(
                address,
                disconnected_callback=self._handle_disconnect,
            )
            await self._client.connect(timeout=10.0)
            self._connected = True
            self._device_name = address

            # 发现所有服务和特征
            self._discovered_services = []
            write_chars = []
            notify_chars = []

            for svc in self._client.services:
                svc_info = {"uuid": svc.uuid, "chars": []}
                for char in svc.characteristics:
                    props = list(char.properties)
                    svc_info["chars"].append({
                        "uuid": char.uuid,
                        "properties": props,
                    })
                    if "write" in props or "write-without-response" in props:
                        write_chars.append(char.uuid)
                    if "notify" in props:
                        notify_chars.append(char.uuid)
                self._discovered_services.append(svc_info)

            # 自动选择: 优先NUS, 否则最后一个可写特征(自定义透传服务通常排在最后)
            if NUS_WRITE_UUID in write_chars:
                self._write_uuid = NUS_WRITE_UUID
            elif write_chars:
                self._write_uuid = write_chars[-1]
            else:
                self._write_uuid = None

            if NUS_NOTIFY_UUID in notify_chars:
                self._notify_uuid = NUS_NOTIFY_UUID
            elif notify_chars:
                self._notify_uuid = notify_chars[0]
            else:
                self._notify_uuid = None

            # 订阅通知
            if self._notify_uuid:
                try:
                    await self._client.start_notify(
                        self._notify_uuid, self._handle_notify
                    )
                except Exception as e:
                    print(f"BLE: 订阅通知失败({self._notify_uuid}): {e}")

            print(f"BLE连接成功: {address}")
            print(f"  可写特征: {write_chars}")
            print(f"  选定写特征: {self._write_uuid}")
            return True
        except Exception as e:
            print(f"BLE连接失败: {e}")
            self._connected = False
            self._client = None
            return False

    def connect(self, address: str) -> bool:
        return self._run_coro_sync(self._connect(address), timeout=20)

    # ---- 手动设置特征 ----

    def set_write_characteristic(self, uuid: str):
        """手动设置写特征UUID (连接后由用户选择)"""
        self._write_uuid = uuid
        print(f"BLE: 写特征已手动设置为 {uuid}")

    def set_notify_characteristic(self, uuid: str):
        """手动设置通知特征UUID"""
        self._notify_uuid = uuid
        # 订阅通知
        if self._client and self._connected:
            try:
                self._run_coro_sync(
                    self._client.start_notify(uuid, self._handle_notify),
                    timeout=5
                )
            except Exception as e:
                print(f"BLE: 订阅通知失败: {e}")

    # ---- 断开回调 ----

    def _handle_disconnect(self, client: BleakClient):
        was_connected = self._connected
        self._connected = False
        self._client = None
        if was_connected and self._on_disconnect:
            try:
                self._on_disconnect()
            except Exception:
                pass

    # ---- 断开 ----

    async def _disconnect(self):
        if self._client and self._connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._client = None

    def disconnect(self):
        if self._loop and self._loop.is_running():
            try:
                self._run_coro_sync(self._disconnect(), timeout=5)
            except Exception:
                pass
        self._connected = False

    # ---- 发送 ----

    async def _send(self, data: bytes) -> bool:
        if not self._client or not self._connected or not self._write_uuid:
            return False
        try:
            await self._client.write_gatt_char(self._write_uuid, data, response=True)
            return True
        except BleakError:
            try:
                await self._client.write_gatt_char(self._write_uuid, data, response=False)
                return True
            except Exception as e:
                print(f"BLE发送失败: {e}")
                return False
        except Exception as e:
            print(f"BLE发送失败: {e}")
            return False

    def send_data(self, data: bytes) -> bool:
        if not self._connected or not self._loop:
            return False
        try:
            return self._run_coro_sync(self._send(data), timeout=5)
        except Exception as e:
            print(f"BLE发送异常: {e}")
            return False

    def send_data_async(self, data: bytes,
                        callback: Callable[[bool], None] | None = None):
        if not self._connected or not self._loop:
            if callback:
                callback(False)
            return

        async def _do():
            result = await self._send(data)
            if callback:
                callback(result)

        try:
            asyncio.run_coroutine_threadsafe(_do(), self._loop)
        except Exception as e:
            print(f"BLE异步发送异常: {e}")
            if callback:
                callback(False)

    # ---- 通知回调 ----

    def _handle_notify(self, sender: int, data: bytes):
        if self._on_data_received:
            try:
                self._on_data_received(data)
            except Exception:
                pass

    # ---- 属性 ----

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def write_uuid(self) -> str | None:
        return self._write_uuid

    @property
    def discovered_services(self) -> list[dict]:
        return self._discovered_services
