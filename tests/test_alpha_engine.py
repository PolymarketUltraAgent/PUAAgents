import pytest
from unittest.mock import patch, MagicMock
from market_fetcher import MarketSnapshot
from news_aggregator import NewsArticle
from alpha_engine import AlphaSignal, analyze, EDGE_THRESHOLD


def make_snapshot(**overrides) -> MarketSnapshot:
    defaults = dict(
        market_id="m1", question="Will oil exceed $100 by end of 2025?", tag="economics",
        yes_price=0.40, no_price=0.60, volume_24h=50_000, liquidity=20_000,
        spread=0.02, competitive=0.95, accepting_orders=True,
    )
    return MarketSnapshot(**{**defaults, **overrides})


def make_articles() -> list[NewsArticle]:
    return [
        NewsArticle(
            title="OPEC cuts production sharply",
            url="https://example.com/1",
            content="OPEC announced a 2mb/d production cut effective immediately.",
            score=0.95,
            published_date="2025-05-10",
        )
    ]


def mock_anthropic_response(fair_prob: float, confidence: float, rationale: str):
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = {"fair_prob": fair_prob, "confidence": confidence, "rationale": rationale}
    response = MagicMock()
    response.content = [tool_use_block]
    return response


def mock_gemini_response(fair_prob: float, confidence: float, rationale: str):
    fc = MagicMock()
    fc.args = {"fair_prob": fair_prob, "confidence": confidence, "rationale": rationale}
    part = MagicMock()
    part.function_call = fc
    candidate = MagicMock()
    candidate.content.parts = [part]
    response = MagicMock()
    response.candidates = [candidate]
    return response


# --- provider selection ---

def test_uses_anthropic_when_key_set():
    mock_resp = mock_anthropic_response(0.65, 0.80, "rationale")
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key", "GEMINI_API_KEY": ""}), \
         patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_resp
        signal = analyze(make_snapshot(), make_articles())
    assert signal.provider == "anthropic"


def test_uses_gemini_when_only_gemini_key_set():
    mock_resp = mock_gemini_response(0.60, 0.75, "rationale")
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "key"}), \
         patch("alpha_engine.engine.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = mock_resp
        signal = analyze(make_snapshot(), make_articles())
    assert signal.provider == "gemini"


def test_raises_when_no_key_set():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False), \
         patch("alpha_engine.engine.load_dotenv"):
        with pytest.raises(EnvironmentError, match="No LLM API key"):
            analyze(make_snapshot(), make_articles())


# --- analyze (via Anthropic) ---

def test_analyze_returns_alpha_signal():
    mock_resp = mock_anthropic_response(0.65, 0.80, "OPEC cuts support higher prices.")
    with patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_resp
        signal = analyze(make_snapshot(), make_articles())
    assert isinstance(signal, AlphaSignal)


def test_analyze_computes_edge_correctly():
    mock_resp = mock_anthropic_response(0.65, 0.80, "rationale")
    with patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_resp
        signal = analyze(make_snapshot(yes_price=0.40), make_articles())
    assert signal.implied_prob == pytest.approx(0.40)
    assert signal.fair_prob == pytest.approx(0.65)
    assert signal.edge == pytest.approx(0.25)


def test_analyze_is_signal_true_when_edge_above_threshold():
    mock_resp = mock_anthropic_response(0.65, 0.80, "rationale")
    with patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_resp
        signal = analyze(make_snapshot(yes_price=0.40), make_articles())
    assert signal.is_signal is True


def test_analyze_is_signal_false_when_edge_below_threshold():
    mock_resp = mock_anthropic_response(0.41, 0.80, "rationale")
    with patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_resp
        signal = analyze(make_snapshot(yes_price=0.40), make_articles())
    assert signal.edge < EDGE_THRESHOLD
    assert signal.is_signal is False


def test_analyze_passes_question_in_prompt():
    captured = {}

    def capture_create(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return mock_anthropic_response(0.5, 0.7, "neutral")

    with patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.side_effect = capture_create
        analyze(make_snapshot(question="Will X happen?"), make_articles())

    assert "Will X happen?" in captured["messages"][0]["content"]


def test_analyze_empty_articles_still_runs():
    mock_resp = mock_anthropic_response(0.50, 0.40, "No news available.")
    with patch("alpha_engine.engine.anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_resp
        signal = analyze(make_snapshot(), articles=[])
    assert isinstance(signal, AlphaSignal)
    assert signal.confidence == pytest.approx(0.40)
