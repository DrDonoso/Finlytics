"""The shared per-user sliding window for chat and automatic analysis."""

from finlytics.auth.ratelimit import RateLimiter

message_limiters: dict[tuple[int, int], RateLimiter] = {}


def limiter_for(max_attempts: int, window_seconds: int) -> RateLimiter:
    key = (max_attempts, window_seconds)
    limiter = message_limiters.get(key)
    if limiter is None:
        limiter = RateLimiter(max_attempts=max_attempts, window_seconds=window_seconds)
        message_limiters[key] = limiter
    return limiter
