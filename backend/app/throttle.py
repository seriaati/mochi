"""An in-memory sliding-window limiter, used to slow down password guessing at login.

State lives in this process only: a restart clears it, and several workers each keep their own.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class Limiter:
    """Allows `per_key` attempts per key (a client IP) and `total` attempts overall in any
    `window` seconds."""

    def __init__(
        self,
        per_key: int,
        total: int,
        window: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_key = per_key
        self.total = total
        self.window = window
        self.clock = clock
        self._by_key: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Records an attempt, or, when over a limit, returns the whole seconds to wait
        instead (and records nothing)."""
        with self._lock:
            now = self.clock()
            self._forget_before(now - self.window)
            mine = self._by_key.get(key, deque())
            waits = []
            if len(mine) >= self.per_key:
                waits.append(mine[0] + self.window - now)
            if len(self._all) >= self.total:
                waits.append(self._all[0] + self.window - now)
            if waits:
                return max(1, math.ceil(max(waits)))
            self._by_key[key] = mine
            mine.append(now)
            self._all.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._by_key.clear()
            self._all.clear()

    def _forget_before(self, cutoff: float) -> None:
        while self._all and self._all[0] <= cutoff:
            self._all.popleft()
        for key, attempts in list(self._by_key.items()):
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self._by_key[key]
