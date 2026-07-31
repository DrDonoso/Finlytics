"""Tests for the authentication attempt rate limiter.

Cover the sliding-window mechanics independently of the endpoint, so a failure
points directly to whether the problem is in the algorithm or in how the API uses it.
"""

from __future__ import annotations

from finlytics.auth.ratelimit import RateLimiter, client_ip


class _FakeClient:
    def __init__(self, host: str | None) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str | None = "203.0.113.7", *, no_client: bool = False) -> None:
        self.client = None if no_client else _FakeClient(host)


# ── Sliding window ────────────────────────────────────────────────────────────

def test_allows_up_to_the_limit():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)

    results = [limiter.check("ip", now=0.0) for _ in range(3)]

    assert [r.allowed for r in results] == [True, True, True]
    assert [r.remaining for r in results] == [2, 1, 0]


def test_blocks_once_the_limit_is_exceeded():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.check("ip", now=0.0)

    verdict = limiter.check("ip", now=0.0)

    assert verdict.allowed is False
    assert verdict.remaining == 0
    assert verdict.retry_after > 0


def test_blocked_attempts_do_not_extend_the_penalty():
    """Hammering the endpoint while blocked must not extend the punishment window.

    If each rejected attempt also pushed the window, a blocked IP would stay
    blocked indefinitely just by retrying.
    """
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("ip", now=0.0)
    limiter.check("ip", now=0.0)

    # Rejected repeatedly during the window...
    for t in (10.0, 20.0, 30.0, 50.0):
        assert limiter.check("ip", now=t).allowed is False

    # ...and quota is restored once the first attempt expires.
    assert limiter.check("ip", now=61.0).allowed is True


def test_window_slides():
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("ip", now=0.0)
    limiter.check("ip", now=30.0)

    assert limiter.check("ip", now=45.0).allowed is False
    # At t=61 the attempt from t=0 has expired, freeing one slot.
    assert limiter.check("ip", now=61.0).allowed is True
    # But the t=30 attempt is still alive, so there is no second slot.
    assert limiter.check("ip", now=61.0).allowed is False


def test_keys_are_independent():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)

    assert limiter.check("ip-a", now=0.0).allowed is True
    assert limiter.check("ip-a", now=0.0).allowed is False
    # A different IP does not inherit the block from the first.
    assert limiter.check("ip-b", now=0.0).allowed is True


def test_reset_clears_a_single_key():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip-a", now=0.0)
    limiter.check("ip-b", now=0.0)

    limiter.reset("ip-a")

    assert limiter.check("ip-a", now=0.0).allowed is True
    assert limiter.check("ip-b", now=0.0).allowed is False


def test_retry_after_is_at_least_one_second():
    """Retry-After must never be 0 — that would suggest retrying immediately."""
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip", now=0.0)

    # At the very end of the window, where rounding could produce 0.
    verdict = limiter.check("ip", now=59.99)

    assert verdict.allowed is False
    assert verdict.retry_after >= 1


# ── Memory cleanup ────────────────────────────────────────────────────────────

def test_purge_drops_expired_keys_only():
    limiter = RateLimiter(max_attempts=5, window_seconds=60)
    limiter.check("old", now=0.0)
    limiter.check("recent", now=100.0)

    removed = limiter.purge(now=120.0)

    assert removed == 1
    # The recent key retains its history.
    assert limiter.check("recent", now=120.0).remaining == 3


def test_clear_wipes_everything():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip-a", now=0.0)
    limiter.check("ip-b", now=0.0)

    limiter.clear()

    assert limiter.check("ip-a", now=0.0).allowed is True
    assert limiter.check("ip-b", now=0.0).allowed is True


# ── IP extraction ─────────────────────────────────────────────────────────────

def test_client_ip_reads_the_connection():
    assert client_ip(_FakeRequest("198.51.100.4")) == "198.51.100.4"


def test_client_ip_falls_back_when_absent():
    assert client_ip(_FakeRequest(no_client=True)) == "unknown"
    assert client_ip(_FakeRequest(host=None)) == "unknown"


def test_client_ip_ignores_forwarded_headers():
    """X-Forwarded-For is spoofable: trusting it would nullify the limit.

    Sending a different value on each attempt would give unlimited quota,
    so the IP is always taken from the connection.
    """
    request = _FakeRequest("198.51.100.4")
    request.headers = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}

    assert client_ip(request) == "198.51.100.4"
