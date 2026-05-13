from dataclasses import dataclass
from market_fetcher import MarketSnapshot, get_market_snapshots
from news_aggregator import fetch_news
from alpha_engine import AlphaSignal, analyze

# Thresholds for Option 1 (liquidity/activity) + Option 2 (price proximity)
MIN_VOLUME_24H = 10_000
MIN_LIQUIDITY = 5_000
MAX_SPREAD = 0.10
MIN_COMPETITIVE = 0.80
MIN_YES_PRICE = 0.05
MAX_YES_PRICE = 0.95
DEFAULT_TOP_N = 20


@dataclass
class TradeDecision:
    market_id: str
    question: str
    direction: str      # "YES" | "NO" | "PASS"
    size: float         # Kelly-sized position
    entry_price: float
    expected_value: float
    rationale: str


def is_worth_analyzing(snapshot: MarketSnapshot) -> bool:
    """Apply Option 1 (liquidity) + Option 2 (price proximity) filters."""
    return (
        snapshot.accepting_orders
        and snapshot.volume_24h >= MIN_VOLUME_24H
        and snapshot.liquidity >= MIN_LIQUIDITY
        and snapshot.spread <= MAX_SPREAD
        and snapshot.competitive >= MIN_COMPETITIVE
        and MIN_YES_PRICE < snapshot.yes_price < MAX_YES_PRICE
    )


def select_markets(
    snapshots: list[MarketSnapshot],
    top_n: int = DEFAULT_TOP_N,
) -> list[MarketSnapshot]:
    """Filter and rank markets, returning top N by volume."""
    filtered = [s for s in snapshots if is_worth_analyzing(s)]
    ranked = sorted(filtered, key=lambda s: s.volume_24h, reverse=True)
    return ranked[:top_n]


def analyze_market(snapshot: MarketSnapshot) -> AlphaSignal:
    """Fetch news and run AlphaEngine for a single market."""
    articles = fetch_news(snapshot.question)
    return analyze(snapshot, articles)


def decide_trade(signal: AlphaSignal) -> TradeDecision:
    """Run TradeAdvisor for a single AlphaSignal. (stub)"""
    raise NotImplementedError("TradeAdvisor not yet built")


def run(tags: list[str] | None = None, top_n: int = DEFAULT_TOP_N) -> list[TradeDecision]:
    """Full pipeline: fetch → filter → analyze → decide."""
    snapshots = get_market_snapshots(tags=tags)
    candidates = select_markets(snapshots, top_n=top_n)

    decisions = []
    for snapshot in candidates:
        signal = analyze_market(snapshot)
        decision = decide_trade(signal)
        decisions.append(decision)

    return decisions
