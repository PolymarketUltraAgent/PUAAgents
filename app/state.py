"""In-memory per-user state.

Volatile by design: subscriptions and cached snapshots reset when the bot
restarts. That's a deliberate v1 choice — swap this module for a
SQLite-backed implementation later without touching the handlers.

All access is gated by a single asyncio.Lock so concurrent handlers can read
and mutate the store safely.
"""
import asyncio
from dataclasses import dataclass, field

from market_fetcher import MarketSnapshot
from trade_advisor import TradeDecision


@dataclass
class UserState:
    user_id: int
    subscribed_tags: set[str] = field(default_factory=set)
    # Most recent market snapshots, keyed by market_id, so users can drill in
    # with /news <id> and /signal <id> after a /scan or /search.
    last_snapshots: dict[str, MarketSnapshot] = field(default_factory=dict)
    last_decisions: list[TradeDecision] = field(default_factory=list)
    # Market IDs we've already alerted this user about — prevents repeat pings
    # from the periodic scheduler.
    seen_alert_market_ids: set[str] = field(default_factory=set)


_users: dict[int, UserState] = {}
_lock = asyncio.Lock()


async def get_or_create(user_id: int) -> UserState:
    async with _lock:
        user = _users.get(user_id)
        if user is None:
            user = UserState(user_id=user_id)
            _users[user_id] = user
        return user


async def all_users() -> list[UserState]:
    """Snapshot of every known user. Returns a list copy so callers can
    iterate without holding the lock."""
    async with _lock:
        return list(_users.values())


async def remember_snapshots(user_id: int, snapshots: list[MarketSnapshot]) -> None:
    """Cache the snapshots a user just saw so /news <id> and /signal <id> work."""
    user = await get_or_create(user_id)
    async with _lock:
        user.last_snapshots = {s.market_id: s for s in snapshots}


async def remember_decisions(user_id: int, decisions: list[TradeDecision]) -> None:
    user = await get_or_create(user_id)
    async with _lock:
        user.last_decisions = list(decisions)


async def subscribe(user_id: int, tag: str) -> bool:
    """Add a tag. Returns True if it was newly added."""
    user = await get_or_create(user_id)
    async with _lock:
        if tag in user.subscribed_tags:
            return False
        user.subscribed_tags.add(tag)
        return True


async def unsubscribe(user_id: int, tag: str) -> bool:
    """Remove a tag. Returns True if it was present."""
    user = await get_or_create(user_id)
    async with _lock:
        if tag not in user.subscribed_tags:
            return False
        user.subscribed_tags.discard(tag)
        return True


async def mark_alerted(user_id: int, market_ids: list[str]) -> None:
    user = await get_or_create(user_id)
    async with _lock:
        user.seen_alert_market_ids.update(market_ids)


async def clear_all() -> None:
    """Test hook — wipe the entire store."""
    async with _lock:
        _users.clear()
