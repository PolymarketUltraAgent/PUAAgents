"""
Integration tests — hit the real Anthropic API.
Run with: pytest tests/test_alpha_engine_integration.py -v -m integration
"""
import pytest
from market_fetcher import MarketSnapshot
from news_aggregator import NewsArticle
from alpha_engine import AlphaSignal, analyze, EDGE_THRESHOLD

pytestmark = pytest.mark.integration


def make_snapshot(**overrides) -> MarketSnapshot:
    defaults = dict(
        market_id="m1", question="Will the Federal Reserve cut rates in 2025?", tag="economics",
        yes_price=0.55, no_price=0.45, volume_24h=50_000, liquidity=20_000,
        spread=0.02, competitive=0.95, accepting_orders=True,
    )
    return MarketSnapshot(**{**defaults, **overrides})


def make_articles() -> list[NewsArticle]:
    return [
        NewsArticle(
            title="Fed signals rate cuts possible in late 2025",
            url="https://example.com/fed-1",
            content="Federal Reserve officials hinted that rate cuts remain on the table for late 2025 if inflation continues to cool.",
            score=0.92,
            published_date="2025-05-01",
        ),
        NewsArticle(
            title="Inflation data shows continued progress",
            url="https://example.com/fed-2",
            content="CPI data came in below expectations, increasing expectations for Fed easing.",
            score=0.88,
            published_date="2025-05-05",
        ),
    ]


def test_analyze_returns_alpha_signal():
    signal = analyze(make_snapshot(), make_articles())

    assert isinstance(signal, AlphaSignal)


def test_analyze_fair_prob_is_valid():
    signal = analyze(make_snapshot(), make_articles())

    assert 0.0 <= signal.fair_prob <= 1.0


def test_analyze_confidence_is_valid():
    signal = analyze(make_snapshot(), make_articles())

    assert 0.0 <= signal.confidence <= 1.0


def test_analyze_edge_computed_correctly():
    snapshot = make_snapshot(yes_price=0.55)
    signal = analyze(snapshot, make_articles())

    assert signal.edge == pytest.approx(abs(signal.fair_prob - 0.55), abs=0.001)


def test_analyze_rationale_is_non_empty():
    signal = analyze(make_snapshot(), make_articles())

    assert signal.rationale.strip() != ""


def test_analyze_is_signal_flag_matches_edge():
    signal = analyze(make_snapshot(), make_articles())

    assert signal.is_signal == (signal.edge >= EDGE_THRESHOLD)


def test_analyze_no_news_returns_lower_confidence():
    signal_with_news = analyze(make_snapshot(), make_articles())
    signal_no_news = analyze(make_snapshot(), articles=[])

    assert signal_no_news.confidence <= signal_with_news.confidence
