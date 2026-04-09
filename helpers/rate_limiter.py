import asyncio
import time


class RateLimiter:
    """Async token bucket rate limiter."""

    def __init__(self, rate: float, capacity: float | None = None):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate  # tokens added per second
        self.capacity = capacity or rate
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last_refill = now

            if self._tokens < tokens:
                wait = (tokens - self._tokens) / self.rate
                await asyncio.sleep(wait)
                self._last_refill = time.monotonic()
                self._tokens = 0.0
            else:
                self._tokens -= tokens
