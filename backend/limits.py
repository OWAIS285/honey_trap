"""In-memory abuse limits for the public demo URL (per Cloud Run instance)."""

import time
from collections import defaultdict, deque

import config


class Limiter:
    def __init__(self, per_hour: int, max_concurrent: int) -> None:
        self.per_hour = per_hour
        self.max_concurrent = max_concurrent
        self.active = 0
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, ip: str) -> str | None:
        """Return a user-facing reason if this session must be refused, else None."""
        now = time.time()
        hits = self._hits[ip]
        while hits and now - hits[0] > 3600:
            hits.popleft()
        if len(hits) >= self.per_hour:
            return "Too many sessions from your network this hour. Please try again later or use the replay."
        if self.active >= self.max_concurrent:
            return "All demo lines are busy right now. Please try again in a minute or use the replay."
        return None

    def enter(self, ip: str) -> None:
        self._hits[ip].append(time.time())
        self.active += 1

    def leave(self) -> None:
        self.active = max(0, self.active - 1)


limiter = Limiter(config.CALLS_PER_HOUR_PER_IP, config.MAX_CONCURRENT_SESSIONS)
