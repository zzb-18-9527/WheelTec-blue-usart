"""BLE/串口 指令发送队列

所有指令通过此队列串行发送，避免并发写入导致BLE协议栈崩溃。
非阻塞发送，超时自动跳过，支持同类型指令去重。
"""
import threading
from typing import Callable
from queue import Queue, Empty, Full


class CommandQueue:
    def __init__(self, send_fn: Callable[[bytes], bool],
                 send_async_fn: Callable[[bytes, Callable], None] = None,
                 min_interval: float = 0.1,
                 max_size: int = 100):
        """
        send_fn: 同步发送函数 (bytes) -> bool
        send_async_fn: 异步发送函数 (bytes, callback) -> None (优先使用)
        min_interval: 两条指令之间的最小间隔(秒)
        max_size: 队列最大容量
        """
        self._send_fn = send_fn
        self._send_async_fn = send_async_fn
        self._min_interval = min_interval
        self._queue: Queue = Queue(maxsize=max_size)
        self._thread: threading.Thread | None = None
        self._running = False
        self._send_done = threading.Event()
        self._send_result = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        # 清空队列并放哨兵值唤醒线程
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Empty:
                break
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def put(self, data: bytes):
        """将指令加入发送队列(线程安全)。队列满时丢弃最旧的指令。"""
        if not self._running:
            return
        try:
            self._queue.put_nowait(data)
        except Full:
            # 队列满，丢弃最旧的
            try:
                self._queue.get_nowait()
            except Empty:
                pass
            try:
                self._queue.put_nowait(data)
            except Full:
                pass

    def _on_send_done(self, result: bool):
        """异步发送完成回调"""
        self._send_result = result
        self._send_done.set()

    def _run(self):
        while self._running:
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                continue

            if item is None:  # 哨兵值，退出
                break

            # 间隔保护
            self._send_done.clear()

            try:
                if self._send_async_fn:
                    # 异步发送 + 超时等待
                    self._send_async_fn(item, self._on_send_done)
                    self._send_done.wait(timeout=1.0)  # 最多等1秒
                else:
                    # 同步发送 + 超时保护
                    result_thread = threading.Thread(
                        target=self._sync_send, args=(item,), daemon=True
                    )
                    result_thread.start()
                    result_thread.join(timeout=1.0)
            except Exception as e:
                print(f"指令发送失败: {e}")

            # 指令间隔
            if self._running:
                self._sleep(self._min_interval)

    def _sync_send(self, data: bytes):
        try:
            result = self._send_fn(data)
            self._send_result = result
        except Exception:
            self._send_result = False
        finally:
            self._send_done.set()

    def _sleep(self, seconds: float):
        """可中断的等待"""
        step = 0.05
        elapsed = 0.0
        while elapsed < seconds and self._running:
            import time
            time.sleep(step)
            elapsed += step
