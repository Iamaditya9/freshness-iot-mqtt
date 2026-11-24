from collections import deque
import time
from typing import Optional, Dict, Any


class BaseTelemetryQueue:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer = deque()
        self.enqueued_count = 0
        self.dropped_overflow = 0
        self.dropped_stale = 0

    def push(self, msg: Dict[str, Any]) -> None:
        raise NotImplementedError

    def pop(self, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def __len__(self) -> int:
        return len(self.buffer)

    def stats(self) -> Dict[str, int]:
        return {
            "enqueued": self.enqueued_count,
            "dropped_overflow": self.dropped_overflow,
            "dropped_stale": self.dropped_stale,
            "remaining_in_queue": len(self.buffer),
        }


class FIFOQueue(BaseTelemetryQueue):
    """
    Baseline First-In, First-Out bounded queue.
    When full, newly arriving messages are dropped (tail-drop) and counted.
    """
    def push(self, msg: Dict[str, Any]) -> None:
        if len(self.buffer) >= self.capacity:
            self.dropped_overflow += 1
            return
        self.buffer.append(msg)
        self.enqueued_count += 1

    def pop(self, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        if not self.buffer:
            return None
        return self.buffer.popleft()


class FreshnessAwareQueue(BaseTelemetryQueue):
    """
    Bounded freshness-aware queue.
    - Overflow rule: evicts the oldest message to keep the newest reading.
    - Pop rule: serves the newest valid reading first (LIFO) and discards
      any reading whose age exceeds max_age_sec.
    """
    def __init__(self, capacity: int, max_age_sec: float):
        super().__init__(capacity)
        self.max_age_sec = max_age_sec

    def push(self, msg: Dict[str, Any]) -> None:
        if len(self.buffer) >= self.capacity:
            # Drop oldest reading to make room for fresher telemetry
            self.buffer.popleft()
            self.dropped_overflow += 1
        self.buffer.append(msg)
        self.enqueued_count += 1

    def pop(self, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        if now is None:
            now = time.time()

        # Serve newest first; evict anything older than max_age_sec
        while self.buffer:
            candidate = self.buffer.pop()
            age = now - candidate["gen_ts"]
            if age <= self.max_age_sec:
                return candidate
            self.dropped_stale += 1

        return None