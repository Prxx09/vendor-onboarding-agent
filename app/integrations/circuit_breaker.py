from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import TypeVar

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    consecutive_failures: int = 0
    is_open: bool = False

    def __post_init__(self):
        self._lock = Lock()

    def call(self, operation: Callable[[], T], on_open: Callable[[], T]) -> T:
        with self._lock:
            if self.is_open:
                return on_open()
        try:
            value = operation()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return value

    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                self.is_open = True

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.is_open = False
