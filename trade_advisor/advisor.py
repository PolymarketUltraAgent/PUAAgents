from dataclasses import dataclass
from alpha_engine import AlphaSignal

MIN_CONFIDENCE = 0.60   # ignore signals where the LLM isn't confident enough
KELLY_FRACTION = 0.5    # half-Kelly for conservative sizing
MIN_EDGE = 0.05         # must match AlphaEngine EDGE_THRESHOLD


@dataclass
class TradeDecision:
    market_id: str
    question: str
    direction: str      # "YES" | "NO" | "PASS"
    entry_price: float
    kelly_fraction: float   # raw full-Kelly fraction
    size: float             # scaled position size (half-Kelly, clamped 0–1)
    expected_value: float
    rationale: str


def _kelly_yes(fair_prob: float, yes_price: float) -> float:
    """Kelly fraction for a YES bet. Positive means bet YES."""
    if yes_price >= 1.0:
        return 0.0
    return (fair_prob - yes_price) / (1.0 - yes_price)


def _kelly_no(fair_prob: float, yes_price: float) -> float:
    """Kelly fraction for a NO bet (at no_price = 1 - yes_price)."""
    if yes_price <= 0.0:
        return 0.0
    return (yes_price - fair_prob) / yes_price


def _expected_value(fair_prob: float, entry_price: float, direction: str) -> float:
    """EV per dollar staked."""
    if direction == "YES":
        return round(fair_prob * (1 - entry_price) - (1 - fair_prob) * entry_price, 4)
    if direction == "NO":
        no_price = 1 - entry_price
        return round((1 - fair_prob) * (1 - no_price) - fair_prob * no_price, 4)
    return 0.0


def decide(signal: AlphaSignal) -> TradeDecision:
    """Convert an AlphaSignal into a TradeDecision using Kelly criterion."""

    def _pass(reason: str) -> TradeDecision:
        return TradeDecision(
            market_id=signal.market_id,
            question=signal.question,
            direction="PASS",
            entry_price=signal.implied_prob,
            kelly_fraction=0.0,
            size=0.0,
            expected_value=0.0,
            rationale=reason,
        )

    if not signal.is_signal:
        return _pass(f"Edge {signal.edge:.2%} below threshold {MIN_EDGE:.2%}")

    if signal.confidence < MIN_CONFIDENCE:
        return _pass(f"Confidence {signal.confidence:.2%} below minimum {MIN_CONFIDENCE:.2%}")

    # Determine direction
    if signal.fair_prob > signal.implied_prob:
        direction = "YES"
        kelly = _kelly_yes(signal.fair_prob, signal.implied_prob)
        entry_price = signal.implied_prob
    else:
        direction = "NO"
        kelly = _kelly_no(signal.fair_prob, signal.implied_prob)
        entry_price = 1.0 - signal.implied_prob

    if kelly <= 0:
        return _pass("Kelly fraction non-positive — no edge after odds adjustment")

    size = round(min(kelly * KELLY_FRACTION, 1.0), 4)
    ev = _expected_value(signal.fair_prob, signal.implied_prob, direction)

    return TradeDecision(
        market_id=signal.market_id,
        question=signal.question,
        direction=direction,
        entry_price=round(entry_price, 4),
        kelly_fraction=round(kelly, 4),
        size=size,
        expected_value=ev,
        rationale=signal.rationale,
    )
