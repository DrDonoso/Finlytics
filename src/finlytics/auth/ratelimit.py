"""Authentication attempt limiting.

Without this, ``POST /api/auth/login`` accepts unlimited attempts: an attacker
can try passwords as fast as the network allows.  bcrypt makes each attempt
expensive, but it does not stop them.

Design
------
The counter is keyed **per IP**, not per user.  That is deliberate: limiting by
username would let anyone lock another account out just by failing guesses
against it (a denial of service on the legitimate user).  The IP is the one that
pays for its own attempts.

The window is an in-memory sliding window.  Finlytics is self-hosted and
single-user, so no shared storage is needed; if it ever runs with several
workers, this module is where to switch to Redis.

A successful login clears that IP's counter, so getting it wrong a couple of
times and then right leaves no trace.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

__all__ = ["RateLimiter", "RateLimitResult", "client_ip"]


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of querying the limiter."""

    allowed: bool
    """False when the request must be rejected with 429."""

    retry_after: int
    """Seconds until quota is available again. 0 when allowed."""

    remaining: int
    """Attempts left in the current window."""


@dataclass
class RateLimiter:
    """Thread-safe in-memory sliding window.

    Parameters
    ----------
    max_attempts:
        Attempts allowed within the window.
    window_seconds:
        Width of the window.
    """

    max_attempts: int
    window_seconds: int
    _hits: dict[str, deque[float]] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def check(self, key: str, *, now: float | None = None) -> RateLimitResult:
        """Record an attempt for ``key`` and report whether it is allowed.

        The attempt is counted ONLY if it is allowed: once blocked, an IP cannot
        extend its own punishment by hammering the endpoint, which is what would
        happen if every rejected request also pushed the window forward.
        """
        moment = time.monotonic() if now is None else now

        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits

            cutoff = moment - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_attempts:
                retry_after = max(1, int(hits[0] + self.window_seconds - moment) + 1)
                return RateLimitResult(allowed=False, retry_after=retry_after, remaining=0)

            hits.append(moment)
            return RateLimitResult(
                allowed=True,
                retry_after=0,
                remaining=self.max_attempts - len(hits),
            )

    def reset(self, key: str) -> None:
        """Forget the attempts for ``key`` (called after a successful login)."""
        with self._lock:
            self._hits.pop(key, None)

    def purge(self, *, now: float | None = None) -> int:
        """Drop keys whose window has expired completely.

        Stops the dict from growing without bound when many distinct IPs make
        the odd isolated attempt.  Returns how many keys were removed.
        """
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds

        with self._lock:
            stale = [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
            for k in stale:
                del self._hits[k]
            return len(stale)

    def clear(self) -> None:
        """Wipe all state. Intended to isolate tests from each other."""
        with self._lock:
            self._hits.clear()


def client_ip(request) -> str:  # noqa: ANN001 — avoids importing Starlette here
    """Client IP as the application sees it.

    Read from the connection, NOT from ``X-Forwarded-For``: anyone can set that
    header, so trusting it would reduce the limit to nothing (varying the value
    on each attempt would be enough).  Behind a reverse proxy, configure the
    proxy itself — or uvicorn with ``--proxy-headers`` — so the real IP arrives
    already resolved on the connection.
    """
    client = getattr(request, "client", None)
    if client is None or not getattr(client, "host", None):
        return "unknown"
    return str(client.host)
