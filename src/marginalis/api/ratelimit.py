"""Per-IP sliding-window rate limit for /api/ask (it calls Groq, which costs money).

In-memory, so it is per process: fine for a single Render instance.
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_S = 60.0


def client_ip(request: Request) -> str:
    """The caller's IP behind Render's proxy.

    Render's edge appends the connecting address to X-Forwarded-For, so the right-most
    entry is the one a client cannot forge; left-most entries are client-supplied.
    """
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        return parts[-1]
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, per_minute: int, clock=time.monotonic):
        self.per_minute = per_minute
        self.clock = clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record a hit for `key`, or raise 429 with Retry-After if over the limit."""
        now = self.clock()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= WINDOW_S:
                q.popleft()
            if len(q) >= self.per_minute:
                retry = max(1, math.ceil(WINDOW_S - (now - q[0])))
                raise HTTPException(
                    429, f"Rate limit: {self.per_minute} questions per minute. Try again in {retry}s.",
                    headers={"Retry-After": str(retry)})
            q.append(now)
            if len(self.hits) > 10_000:  # drop idle keys so memory stays bounded
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= WINDOW_S]:
                    del self.hits[k]


ask_limiter = RateLimiter(int(os.environ.get("ASK_RATE_PER_MINUTE", "5")))


def limit_ask(request: Request) -> None:
    ask_limiter.check(client_ip(request))
