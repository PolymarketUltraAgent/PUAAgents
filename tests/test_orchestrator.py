import pytest
from unittest.mock import patch
from market_fetcher import MarketSnapshot
from orchestrator import is_worth_analyzing, select_markets


def make_snapshot(**overrides) -> MarketSnapshot:
    defaults = dict(
        market_id="m1", question="Q", tag="politics",
        yes_price=0.50, no_price=0.50,
        volume_24h=50_000, liquidity=20_000,
        spread=0.02, competitive=0.95,
        accepting_orders=True,
    )
    return MarketSnapshot(**{**defaults, **overrides})


# --- is_worth_analyzing ---

def test_passes_all_filters():
    assert is_worth_analyzing(make_snapshot()) is True


def test_rejects_low_volume():
    assert is_worth_analyzing(make_snapshot(volume_24h=5_000)) is False


def test_rejects_low_liquidity():
    assert is_worth_analyzing(make_snapshot(liquidity=1_000)) is False


def test_rejects_wide_spread():
    assert is_worth_analyzing(make_snapshot(spread=0.15)) is False


def test_rejects_low_competitive():
    assert is_worth_analyzing(make_snapshot(competitive=0.50)) is False


def test_rejects_not_accepting_orders():
    assert is_worth_analyzing(make_snapshot(accepting_orders=False)) is False


def test_rejects_yes_price_too_low():
    assert is_worth_analyzing(make_snapshot(yes_price=0.03)) is False


def test_rejects_yes_price_too_high():
    assert is_worth_analyzing(make_snapshot(yes_price=0.97)) is False


def test_accepts_price_at_boundary():
    assert is_worth_analyzing(make_snapshot(yes_price=0.06)) is True
    assert is_worth_analyzing(make_snapshot(yes_price=0.94)) is True


# --- select_markets ---

def test_select_markets_returns_top_n_by_volume():
    snapshots = [
        make_snapshot(market_id="a", volume_24h=10_000),
        make_snapshot(market_id="b", volume_24h=50_000),
        make_snapshot(market_id="c", volume_24h=30_000),
    ]
    result = select_markets(snapshots, top_n=2)

    assert len(result) == 2
    assert result[0].market_id == "b"
    assert result[1].market_id == "c"


def test_select_markets_filters_before_ranking():
    snapshots = [
        make_snapshot(market_id="good", volume_24h=50_000),
        make_snapshot(market_id="bad", volume_24h=100_000, accepting_orders=False),
    ]
    result = select_markets(snapshots, top_n=10)

    assert len(result) == 1
    assert result[0].market_id == "good"


def test_select_markets_empty_input():
    assert select_markets([]) == []


def test_select_markets_fewer_than_top_n():
    snapshots = [make_snapshot(market_id="only")]
    result = select_markets(snapshots, top_n=20)

    assert len(result) == 1
