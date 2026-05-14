"""Per-user, per-command cooldowns.

In-memory dict keyed by (user_id, command) → last successful call timestamp.
Cooldown values are tuned to the cost of the underlying pipeline call:
expensive LLM/network commands get longer cooldowns; bookkeeping commands
are cheap.
"""
import asyncio
import time

# Cooldowns (seconds) per command. Commands not listed here have no cooldown.
COOLDOWNS: dict[str, float] = {
    "scan": 60.0,
    "signal": 30.0,
    "news": 10.0,
    "search": 10.0,
    "recommend": 5.0,
    "tags": 5.0,
    "subscribe": 2.0,
    "unsubscribe": 2.0,
    "subscriptions": 2.0,
}

_last_call: dict[tuple[int, str], float] = {}
_lock = asyncio.Lock()


async def check(user_id: int, command: str) -> tuple[bool, float]:
    """Return (allowed, retry_after_seconds).

    On allowed=True the call is recorded as happening now. On allowed=False
    the stored timestamp is untouched so the user can retry as soon as the
    cooldown elapses.
    """
    cooldown = COOLDOWNS.get(command)
    if cooldown is None:
        return True, 0.0

    now = time.monotonic()
    key = (user_id, command)

    async with _lock:
        last = _last_call.get(key, 0.0)
        elapsed = now - last
        if elapsed < cooldown:
            return False, cooldown - elapsed
        _last_call[key] = now
        return True, 0.0


async def clear_all() -> None:
    """Test hook — wipe all recorded calls."""
    async with _lock:
        _last_call.clear()
