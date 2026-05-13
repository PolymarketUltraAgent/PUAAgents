import pytest
from unittest.mock import patch
from market_fetcher import (
    compute_mid_price,
    build_snapshot,
    get_market_snapshots,
    MarketSnapshot,
    Tag,
)


# --- compute_mid_price ---

def test_compute_mid_price_normal():
    book = {"bids": [{"price": "0.40"}], "asks": [{"price": "0.60"}]}
    assert compute_mid_price(book) == 0.5


def test_compute_mid_price_no_bids():
    book = {"bids": [], "asks": [{"price": "0.70"}]}
    assert compute_mid_price(book) == pytest.approx(0.35)


def test_compute_mid_price_no_asks():
    book = {"bids": [{"price": "0.80"}], "asks": []}
    assert compute_mid_price(book) == pytest.approx(0.90)


def test_compute_mid_price_empty_book():
    assert compute_mid_price({}) == pytest.approx(0.5)


# --- build_snapshot ---

MOCK_MARKET = {
    "id": "market-123",
    "question": "Will oil price exceed $100 by end of 2025?",
    "clobTokenIds": '["token-yes-abc", "token-no-abc"]',
    "bestBid": 0.38,
    "bestAsk": 0.42,
    "volume24hr": "50000",
    "liquidity": "200000",
    "liquidityClob": "200000",
    "spread": 0.04,
    "competitive": 0.95,
    "acceptingOrders": True,
}


def test_build_snapshot_returns_snapshot():
    snapshot = build_snapshot(MOCK_MARKET, tag="economics")

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.market_id == "market-123"
    assert snapshot.yes_price == pytest.approx(0.40)
    assert snapshot.no_price == pytest.approx(0.60)
    assert snapshot.volume_24h == 50000.0
    assert snapshot.liquidity == 200000.0
    assert snapshot.tag == "economics"
    assert snapshot.spread == pytest.approx(0.04)
    assert snapshot.competitive == pytest.approx(0.95)
    assert snapshot.accepting_orders is True


def test_build_snapshot_no_clob_token_ids_returns_none():
    market = {**MOCK_MARKET, "clobTokenIds": "[]"}
    assert build_snapshot(market) is None


def test_build_snapshot_missing_bid_ask_returns_none():
    market = {k: v for k, v in MOCK_MARKET.items() if k not in ("bestBid", "bestAsk")}
    assert build_snapshot(market) is None


def test_build_snapshot_invalid_token_ids_json_returns_none():
    market = {**MOCK_MARKET, "clobTokenIds": "not-json"}
    assert build_snapshot(market) is None


# --- get_market_snapshots ---

MOCK_TAGS = [Tag(id="1", label="Politics", slug="politics")]


def test_get_market_snapshots_filters_none():
    valid_snapshot = MarketSnapshot(
        market_id="1", question="Q", tag="politics",
        yes_price=0.6, no_price=0.4, volume_24h=1000, liquidity=5000,
        spread=0.02, competitive=0.9, accepting_orders=True,
    )
    with patch("market_fetcher.fetcher.fetch_markets", return_value=[MOCK_MARKET, MOCK_MARKET]), \
         patch("market_fetcher.fetcher.build_snapshot", side_effect=[valid_snapshot, None]):
        results = get_market_snapshots(tags=["politics"], limit=2)

    assert len(results) == 1
    assert results[0].market_id == "1"


def test_get_market_snapshots_uses_api_tags_when_none_given():
    with patch("market_fetcher.fetcher.fetch_tags", return_value=MOCK_TAGS), \
         patch("market_fetcher.fetcher.fetch_markets", return_value=[]) as mock_fetch:
        get_market_snapshots(tags=None)

    mock_fetch.assert_called_once_with(tag="politics", limit=20)


def test_get_market_snapshots_multiple_tags():
    with patch("market_fetcher.fetcher.fetch_markets", return_value=[]), \
         patch("market_fetcher.fetcher.build_snapshot") as mock_build:
        get_market_snapshots(tags=["politics", "economics"])

    mock_build.assert_not_called()
