import pytest
from alpha_engine import AlphaSignal
from trade_advisor import TradeDecision, decide, MIN_CONFIDENCE, KELLY_FRACTION


def make_signal(**overrides) -> AlphaSignal:
    defaults = dict(
        market_id="m1",
        question="Will oil exceed $100?",
        implied_prob=0.40,
        fair_prob=0.65,
        edge=0.25,
        confidence=0.80,
        rationale="OPEC cuts support higher prices.",
        is_signal=True,
        provider="gemini",
    )
    return AlphaSignal(**{**defaults, **overrides})


# --- PASS conditions ---

def test_pass_when_no_signal():
    signal = make_signal(is_signal=False, edge=0.02)
    decision = decide(signal)
    assert decision.direction == "PASS"
    assert decision.size == 0.0


def test_pass_when_confidence_too_low():
    signal = make_signal(confidence=0.40)
    decision = decide(signal)
    assert decision.direction == "PASS"
    assert decision.size == 0.0


# --- YES bets ---

def test_yes_when_fair_prob_above_implied():
    signal = make_signal(implied_prob=0.40, fair_prob=0.65)
    decision = decide(signal)
    assert decision.direction == "YES"
    assert decision.entry_price == pytest.approx(0.40)


def test_yes_kelly_sizing():
    # kelly_yes = (0.65 - 0.40) / (1 - 0.40) = 0.25 / 0.60 = 0.4167
    # size = 0.4167 * 0.5 (half-Kelly) = 0.2083
    signal = make_signal(implied_prob=0.40, fair_prob=0.65)
    decision = decide(signal)
    assert decision.kelly_fraction == pytest.approx(0.4167, abs=0.001)
    assert decision.size == pytest.approx(0.4167 * KELLY_FRACTION, abs=0.001)


def test_yes_positive_expected_value():
    signal = make_signal(implied_prob=0.40, fair_prob=0.65)
    decision = decide(signal)
    assert decision.expected_value > 0


# --- NO bets ---

def test_no_when_fair_prob_below_implied():
    signal = make_signal(implied_prob=0.70, fair_prob=0.45, edge=0.25)
    decision = decide(signal)
    assert decision.direction == "NO"
    assert decision.entry_price == pytest.approx(0.30)  # no_price = 1 - 0.70


def test_no_kelly_sizing():
    # kelly_no = (0.70 - 0.45) / 0.70 = 0.25 / 0.70 = 0.3571
    signal = make_signal(implied_prob=0.70, fair_prob=0.45, edge=0.25)
    decision = decide(signal)
    assert decision.kelly_fraction == pytest.approx(0.3571, abs=0.001)
    assert decision.size == pytest.approx(0.3571 * KELLY_FRACTION, abs=0.001)


def test_no_positive_expected_value():
    signal = make_signal(implied_prob=0.70, fair_prob=0.45, edge=0.25)
    decision = decide(signal)
    assert decision.expected_value > 0


# --- size clamping ---

def test_size_clamped_to_1():
    # Extreme edge → Kelly > 1, size should still be <= 1
    signal = make_signal(implied_prob=0.10, fair_prob=0.90, edge=0.80)
    decision = decide(signal)
    assert decision.size <= 1.0


# --- output structure ---

def test_decision_has_rationale():
    signal = make_signal()
    decision = decide(signal)
    assert decision.rationale == signal.rationale


def test_decision_market_id_matches():
    signal = make_signal(market_id="abc-123")
    decision = decide(signal)
    assert decision.market_id == "abc-123"
