import json
import httpx
from dataclasses import dataclass

CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"

RATE_LIMIT_DELAY = 0.12  # 10 req/s → 100ms between calls, 20% buffer


@dataclass
class Tag:
    id: str
    label: str
    slug: str


@dataclass
class MarketSnapshot:
    market_id: str
    question: str
    tag: str
    yes_price: float        # implied probability from order book mid
    no_price: float
    volume_24h: float
    liquidity: float
    spread: float           # best_ask - best_bid, lower = better liquidity
    competitive: float      # Polymarket activity score 0–1
    accepting_orders: bool  # whether the market is currently tradeable


def fetch_tags() -> list[Tag]:
    """Return all Polymarket tags."""
    with httpx.Client(timeout=10) as client:
        response = client.get(f"{GAMMA_BASE}/tags")
        response.raise_for_status()
        raw = response.json()

    return [Tag(id=t["id"], label=t["label"], slug=t["slug"]) for t in raw]


def fetch_markets(tag: str | None = None, limit: int = 20) -> list[dict]:
    """Return active markets, optionally filtered by tag slug."""
    params: dict = {
        "active": "true",
        "closed": "false",
        "limit": limit,
    }
    if tag:
        params["tag"] = tag

    with httpx.Client(timeout=10) as client:
        response = client.get(f"{GAMMA_BASE}/markets", params=params)
        response.raise_for_status()
        return response.json()


def fetch_order_book(token_id: str) -> dict:
    """Return raw order book for a YES token from the CLOB API."""
    with httpx.Client(timeout=10) as client:
        response = client.get(f"{CLOB_BASE}/book", params={"token_id": token_id})
        response.raise_for_status()
        return response.json()


def compute_mid_price(order_book: dict) -> float:
    """Compute mid-price from best bid and best ask as implied probability."""
    bids = order_book.get("bids", [])
    asks = order_book.get("asks", [])

    best_bid = float(bids[0]["price"]) if bids else 0.0
    best_ask = float(asks[0]["price"]) if asks else 1.0

    return (best_bid + best_ask) / 2


def build_snapshot(market: dict, tag: str = "") -> MarketSnapshot | None:
    """Build a MarketSnapshot from a raw Gamma API market dict, or None if data is missing."""
    try:
        clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
        yes_token_id = clob_token_ids[0] if clob_token_ids else None
    except (json.JSONDecodeError, IndexError):
        return None

    if not yes_token_id:
        return None

    best_bid = market.get("bestBid")
    best_ask = market.get("bestAsk")

    if best_bid is None or best_ask is None:
        return None

    best_bid_f = float(best_bid)
    best_ask_f = float(best_ask)
    yes_price = round((best_bid_f + best_ask_f) / 2, 4)

    return MarketSnapshot(
        market_id=market.get("id", ""),
        question=market.get("question", ""),
        tag=tag,
        yes_price=yes_price,
        no_price=round(1.0 - yes_price, 4),
        volume_24h=float(market.get("volume24hr", 0)),
        liquidity=float(market.get("liquidityClob", market.get("liquidity", 0))),
        spread=round(best_ask_f - best_bid_f, 4),
        competitive=float(market.get("competitive", 0.0)),
        accepting_orders=bool(market.get("acceptingOrders", False)),
    )


def get_market_snapshots(tags: list[str] | None = None, limit: int = 20) -> list[MarketSnapshot]:
    """Fetch MarketSnapshots for the given tag slugs.

    If tags is None, fetches across all available tags from the API.
    """
    if tags is None:
        tags = [t.slug for t in fetch_tags()]

    snapshots = []
    for tag in tags:
        markets = fetch_markets(tag=tag, limit=limit)
        for market in markets:
            snapshot = build_snapshot(market, tag=tag)
            if snapshot:
                snapshots.append(snapshot)

    return snapshots
