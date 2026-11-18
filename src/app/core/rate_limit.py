import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import Settings
from app.core.errors import RateLimitError


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                raise RateLimitError("Request rate limit exceeded")
            events.append(now)


async def enforce_rate_limit(request: Request) -> None:
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    address = request.client.host if request.client is not None else "unknown"
    await limiter.check(address)


def build_rate_limiter(settings: Settings) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
