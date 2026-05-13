"""
Integration tests — hit the real Polymarket API.
Run with: pytest tests/test_market_fetcher_integration.py -v -m integration
"""
import json
import pytest
from market_fetcher import (
    fetch_tags,
    fetch_markets,
    fetch_order_book,
    get_market_snapshots,
    Tag,
    MarketSnapshot,
)

pytestmark = pytest.mark.integration


# --- fetch_tags ---

def test_fetch_tags_returns_list_of_tags():
    tags = fetch_tags()

    assert isinstance(tags, list)
    assert len(tags) > 0
    assert all(isinstance(t, Tag) for t in tags)


def test_fetch_tags_have_slug_and_label():
    tags = fetch_tags()
    for tag in tags:
        assert tag.slug.strip() != ""
        assert tag.label.strip() != ""


# --- fetch_markets ---

def test_fetch_markets_returns_list():
    markets = fetch_markets(tag="politics", limit=5)

    assert isinstance(markets, list)
    assert len(markets) > 0


def test_fetch_markets_have_expected_fields():
    markets = fetch_markets(tag="politics", limit=5)
    market = markets[0]

    assert "id" in market
    assert "question" in market
    assert "clobTokenIds" in market
    assert "bestBid" in market
    assert "bestAsk" in market


def test_fetch_markets_no_tag_returns_results():
    markets = fetch_markets(tag=None, limit=5)
    assert isinstance(markets, list)
    assert len(markets) > 0


# --- fetch_order_book ---

def test_fetch_order_book_returns_bids_and_asks():
    markets = fetch_markets(tag="politics", limit=5)

    yes_token_id = None
    for market in markets:
        try:
            ids = json.loads(market.get("clobTokenIds", "[]"))
            if ids:
                yes_token_id = ids[0]
                break
        except (json.JSONDecodeError, IndexError):
            continue

    assert yes_token_id is not None, "No YES token ID found in first 5 markets"

    book = fetch_order_book(yes_token_id)

    assert "bids" in book
    assert "asks" in book


# --- get_market_snapshots ---

def test_get_market_snapshots_explicit_tags():
    snapshots = get_market_snapshots(tags=["politics"], limit=5)

    assert isinstance(snapshots, list)
    assert len(snapshots) > 0
    assert all(isinstance(s, MarketSnapshot) for s in snapshots)


def test_snapshot_prices_are_valid_probabilities():
    snapshots = get_market_snapshots(tags=["politics"], limit=5)

    for s in snapshots:
        assert 0.0 <= s.yes_price <= 1.0, f"Invalid yes_price: {s.yes_price}"
        assert 0.0 <= s.no_price <= 1.0, f"Invalid no_price: {s.no_price}"
        assert abs(s.yes_price + s.no_price - 1.0) < 0.01, (
            f"Prices don't sum to ~1: {s.yes_price} + {s.no_price}"
        )


def test_snapshot_has_non_empty_question():
    snapshots = get_market_snapshots(tags=["politics"], limit=5)

    for s in snapshots:
        assert s.question.strip() != "", f"Empty question for market {s.market_id}"
