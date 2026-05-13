"""
End-to-end pipeline test — all external calls mocked.
Exercises the full path: fetch tags → fetch markets → filter → news →
AlphaEngine (LLM) → TradeAdvisor → TradeDecision.
"""
import pytest
from unittest.mock import patch, MagicMock

from market_fetcher import MarketSnapshot
from news_aggregator import NewsArticle
from alpha_engine import AlphaSignal
from trade_advisor import TradeDecision
from orchestrator import run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _snapshot(market_id: str, question: str, yes_price: float, volume: float) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=question,
        tag="politics",
        yes_price=yes_price,
        no_price=round(1 - yes_price, 4),
        volume_24h=volume,
        liquidity=50_000,
        spread=0.02,
        competitive=0.95,
        accepting_orders=True,
    )


MOCK_SNAPSHOTS = [
    # passes filter, high volume — should be analyzed first
    _snapshot("m1", "Will the Fed cut rates in 2025?", yes_price=0.55, volume=200_000),
    # passes filter, lower volume
    _snapshot("m2", "Will oil exceed $100 by end of 2025?", yes_price=0.40, volume=80_000),
    # fails filter — yes_price too high
    _snapshot("m3", "Will gravity exist tomorrow?", yes_price=0.98, volume=500_000),
    # fails filter — volume too low
    _snapshot("m4", "Will a coin flip land heads?", yes_price=0.50, volume=100),
]

MOCK_ARTICLES = [
    NewsArticle(
        title="Fed signals possible rate cuts",
        url="https://example.com/fed",
        content="Federal Reserve officials hinted at rate cuts in late 2025.",
        score=0.92,
        published_date="2025-05-10",
    )
]


def _llm_tool_response(fair_prob: float, confidence: float, rationale: str):
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"fair_prob": fair_prob, "confidence": confidence, "rationale": rationale}
    response = MagicMock()
    response.content = [block]
    return response


# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------

@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=MOCK_SNAPSHOTS)
@patch("orchestrator.orchestrator.fetch_news", return_value=MOCK_ARTICLES)
@patch("alpha_engine.engine.anthropic.Anthropic")
def test_e2e_returns_trade_decisions(mock_anthropic, mock_news, mock_markets):
    mock_anthropic.return_value.messages.create.return_value = (
        _llm_tool_response(0.70, 0.85, "Strong signals for rate cuts.")
    )

    decisions = run(tags=["politics"], top_n=10)

    assert isinstance(decisions, list)
    assert all(isinstance(d, TradeDecision) for d in decisions)


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=MOCK_SNAPSHOTS)
@patch("orchestrator.orchestrator.fetch_news", return_value=MOCK_ARTICLES)
@patch("alpha_engine.engine.anthropic.Anthropic")
def test_e2e_only_analyzes_filtered_markets(mock_anthropic, mock_news, mock_markets):
    mock_anthropic.return_value.messages.create.return_value = (
        _llm_tool_response(0.70, 0.85, "rationale")
    )

    run(tags=["politics"], top_n=10)

    # m3 (yes_price=0.98) and m4 (low volume) should be filtered out
    # only m1 and m2 pass → fetch_news called exactly twice
    assert mock_news.call_count == 2


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=MOCK_SNAPSHOTS)
@patch("orchestrator.orchestrator.fetch_news", return_value=MOCK_ARTICLES)
@patch("alpha_engine.engine.anthropic.Anthropic")
def test_e2e_markets_analyzed_in_volume_order(mock_anthropic, mock_news, mock_markets):
    mock_anthropic.return_value.messages.create.return_value = (
        _llm_tool_response(0.70, 0.85, "rationale")
    )

    run(tags=["politics"], top_n=10)

    # fetch_news should be called with m1's question first (higher volume)
    calls = [c.args[0] for c in mock_news.call_args_list]
    assert calls[0] == "Will the Fed cut rates in 2025?"
    assert calls[1] == "Will oil exceed $100 by end of 2025?"


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=MOCK_SNAPSHOTS)
@patch("orchestrator.orchestrator.fetch_news", return_value=MOCK_ARTICLES)
@patch("alpha_engine.engine.anthropic.Anthropic")
def test_e2e_yes_signal_produces_yes_decision(mock_anthropic, mock_news, mock_markets):
    # fair_prob (0.70) > implied_prob (0.55) → should recommend YES
    mock_anthropic.return_value.messages.create.return_value = (
        _llm_tool_response(0.70, 0.85, "Strong signals for rate cuts.")
    )

    decisions = run(tags=["politics"], top_n=1)

    assert decisions[0].direction == "YES"
    assert decisions[0].market_id == "m1"
    assert decisions[0].size > 0


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=MOCK_SNAPSHOTS)
@patch("orchestrator.orchestrator.fetch_news", return_value=MOCK_ARTICLES)
@patch("alpha_engine.engine.anthropic.Anthropic")
def test_e2e_low_confidence_produces_pass(mock_anthropic, mock_news, mock_markets):
    # confidence below MIN_CONFIDENCE → TradeAdvisor should PASS
    mock_anthropic.return_value.messages.create.return_value = (
        _llm_tool_response(0.70, 0.30, "Uncertain signals.")
    )

    decisions = run(tags=["politics"], top_n=10)

    assert all(d.direction == "PASS" for d in decisions)


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=MOCK_SNAPSHOTS)
@patch("orchestrator.orchestrator.fetch_news", return_value=MOCK_ARTICLES)
@patch("alpha_engine.engine.anthropic.Anthropic")
def test_e2e_no_edge_produces_pass(mock_anthropic, mock_news, mock_markets):
    # fair_prob ≈ implied_prob → tiny edge → PASS
    mock_anthropic.return_value.messages.create.return_value = (
        _llm_tool_response(0.55, 0.85, "Market seems fairly priced.")
    )

    decisions = run(tags=["politics"], top_n=1)

    assert decisions[0].direction == "PASS"


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key", "GEMINI_API_KEY": ""})
@patch("orchestrator.orchestrator.get_market_snapshots", return_value=[])
def test_e2e_empty_markets_returns_empty_list(mock_markets):
    decisions = run(tags=["politics"])
    assert decisions == []
