import os
import threading
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkerRuntime:
    thread: threading.Thread
    stop_event: threading.Event
    started_at: float = field(default_factory=time.time)

    @property
    def pid(self) -> int:
        return os.getpid()

    @property
    def worker_alive(self) -> bool:
        return self.thread.is_alive()

    @property
    def stop_requested(self) -> bool:
        return self.stop_event.is_set()

    def request_stop(self) -> None:
        self.stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self.thread.join(timeout=timeout)
