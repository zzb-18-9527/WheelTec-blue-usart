"""BLE/串口 指令发送队列

所有指令通过此队列串行发送，避免并发写入导致BLE协议栈崩溃。
"""
import threading
import time
from typing import Callable
from queue import Queue, Empty


class CommandQueue:
    def __init__(self, send_fn: Callable[[bytes], bool], min_interval: float = 0.01):
        """
        send_fn: 底层发送函数 (bytes) -> bool
        min_interval: 两条指令之间的最小间隔(秒)
        """
        self._send_fn = send_fn
        self._min_interval = min_interval
        self._queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_send_time = 0.0
        self._lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        # 放一个哨兵值唤醒队列
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def put(self, data: bytes):
        """将指令加入发送队列(线程安全，可从任意线程调用)"""
        if self._running:
            self._queue.put(data)

    def _run(self):
        while self._running:
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                continue

            if item is None:  # 哨兵值，退出
                break

            # 确保发送间隔
            with self._lock:
                elapsed = time.monotonic() - self._last_send_time
                if elapsed < self._min_interval:
                    time.sleep(self._min_interval - elapsed)

                try:
                    self._send_fn(item)
                except Exception as e:
                    print(f"指令发送失败: {e}")

                self._last_send_time = time.monotonic()
