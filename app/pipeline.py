"""Async wrappers around the blocking orchestrator pipeline.

The underlying pipeline uses synchronous httpx and SDK calls. Each wrapper
offloads the call to a worker thread via `asyncio.to_thread` so the bot's
event loop stays responsive while a scan is in flight.

Centralising this means handlers never reach for `asyncio.to_thread`
themselves — there's one place to add caching or request coalescing later
if quota pressure shows up.
"""
from __future__ import annotations

import asyncio
import time

from market_fetcher import (
    MarketSnapshot,
    Tag,
    fetch_tags as _fetch_tags_blocking,
    get_market_snapshots as _get_market_snapshots_blocking,
)
from news_aggregator import NewsArticle, fetch_news as _fetch_news_blocking
from alpha_engine import AlphaSignal, analyze as _analyze_blocking
from trade_advisor import TradeDecision
from orchestrator import (
    run as _run_blocking,
    select_markets as _select_markets_blocking,
)


# --- Tag listing (cached) ----------------------------------------------------
# The tag list rarely changes — cache it for an hour to avoid hammering the
# Gamma API on every /tags call and to make /tags responsive.

_TAGS_TTL_S = 3600.0
_tags_cache: tuple[float, list[Tag]] | None = None
_tags_lock = asyncio.Lock()


async def fetch_tags() -> list[Tag]:
    global _tags_cache
    async with _tags_lock:
        if _tags_cache is not None:
            cached_at, tags = _tags_cache
            if time.monotonic() - cached_at < _TAGS_TTL_S:
                return tags
        tags = await asyncio.to_thread(_fetch_tags_blocking)
        _tags_cache = (time.monotonic(), tags)
        return tags


# --- One-shot wrappers -------------------------------------------------------


async def get_market_snapshots(
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[MarketSnapshot]:
    return await asyncio.to_thread(_get_market_snapshots_blocking, tags, limit)


async def select_markets(
    snapshots: list[MarketSnapshot],
    top_n: int = 20,
) -> list[MarketSnapshot]:
    # Pure CPU/filter work — to_thread is overkill but keeps the call site
    # uniform with the others.
    return await asyncio.to_thread(_select_markets_blocking, snapshots, top_n)


async def fetch_news(query: str, max_results: int = 5, days: int = 7) -> list[NewsArticle]:
    return await asyncio.to_thread(_fetch_news_blocking, query, max_results, days)


async def analyze(snapshot: MarketSnapshot, articles: list[NewsArticle]) -> AlphaSignal:
    return await asyncio.to_thread(_analyze_blocking, snapshot, articles)


async def analyze_market(snapshot: MarketSnapshot) -> AlphaSignal:
    """fetch_news + analyze for a single market — convenience for /signal."""
    articles = await fetch_news(snapshot.question)
    return await analyze(snapshot, articles)


async def run(tags: list[str] | None = None, top_n: int = 20) -> list[TradeDecision]:
    """Full pipeline. This is the expensive one (LLM + Tavily per market)."""
    return await asyncio.to_thread(_run_blocking, tags, top_n)
