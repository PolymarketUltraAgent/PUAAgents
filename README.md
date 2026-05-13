# PUA Agent

An agent that reads live Polymarket prediction markets, identifies mispriced opportunities using LLM-grounded news analysis, and outputs Kelly-sized trade decisions.

## How it works

```
Polymarket API → Market Filter → News (Tavily) → AlphaEngine (LLM) → TradeAdvisor → TradeDecision
```

1. **MarketFetcher** — fetches all tags and active markets from Polymarket
2. **Market Filter** — drops illiquid, inactive, or near-certain markets (volume, spread, price proximity)
3. **NewsAggregator** — pulls recent news for each candidate market via Tavily
4. **AlphaEngine** — asks an LLM to estimate the fair probability; computes `edge = |fair - implied|`
5. **TradeAdvisor** — applies Kelly criterion to size the position; outputs YES / NO / PASS

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

```env
TAVILY_API_KEY=your_tavily_api_key       # https://tavily.com
ANTHROPIC_API_KEY=your_anthropic_key     # https://console.anthropic.com  (optional)
GEMINI_API_KEY=your_gemini_key           # https://aistudio.google.com    (optional)
```

At least one LLM key is required. If both are set, Anthropic is used. If only Gemini is set, Gemini is used.

## Usage

### Run the full pipeline

```python
from orchestrator import run

# Scan specific tags (fast — recommended)
decisions = run(tags=["politics", "economics"], top_n=10)

# Omit tags to scan all ~100 Polymarket tags (exhaustive — slower, more API calls)
decisions = run(top_n=10)

for d in decisions:
    print(f"{d.direction:4s}  {d.market_id}  ev={d.expected_value:+.2f}  size={d.size:.2f}")
    print(f"      {d.question}")
    print(f"      {d.rationale}")
    print()
```

**Output example:**
```
YES   540817  ev=+0.18  size=0.21
      Will the Fed cut rates before end of 2025?
      Recent CPI data came in below expectations, increasing Fed easing probability.

PASS  540901  ev=+0.00  size=0.00
      Will Bitcoin hit $200k in 2025?
      Insufficient edge — market implied probability close to fair estimate.
```

### Fetch markets only

```python
from market_fetcher import fetch_tags, get_market_snapshots

# See all available tags
tags = fetch_tags()
print([t.slug for t in tags])

# Fetch snapshots for specific tags
snapshots = get_market_snapshots(tags=["politics", "economics"], limit=20)
for s in snapshots:
    print(s.market_id, s.question, f"YES={s.yes_price:.0%}")
```

### Fetch news for a market

```python
from news_aggregator import fetch_news

articles = fetch_news("Will the Federal Reserve cut rates in 2025?", max_results=5)
for a in articles:
    print(a.title, a.published_date)
    print(a.content)
```

### Run AlphaEngine on a single market

```python
from market_fetcher import get_market_snapshots
from news_aggregator import fetch_news
from alpha_engine import analyze

snapshots = get_market_snapshots(tags=["economics"], limit=1)
snapshot = snapshots[0]
articles = fetch_news(snapshot.question)

signal = analyze(snapshot, articles)
print(f"Implied: {signal.implied_prob:.0%}  Fair: {signal.fair_prob:.0%}  Edge: {signal.edge:.0%}")
print(f"Signal: {signal.is_signal}  Provider: {signal.provider}")
print(signal.rationale)
```

## Tests

```bash
# Unit tests only (no API calls, fast)
python -m pytest tests/ -m "not integration" -v

# Integration tests (hits real APIs — requires valid keys)
python -m pytest tests/ -m integration -v

# End-to-end pipeline test (fully mocked)
python -m pytest tests/test_e2e.py -v

# All tests
python -m pytest tests/ -v
```

## Project Structure

```
PUAAgents/
├── market_fetcher/          # Polymarket API client
│   ├── __init__.py
│   └── fetcher.py
├── news_aggregator/         # Tavily news search
│   ├── __init__.py
│   └── aggregator.py
├── alpha_engine/            # LLM fair-value estimation (Anthropic or Gemini)
│   ├── __init__.py
│   └── engine.py
├── trade_advisor/           # Kelly criterion sizing and direction logic
│   ├── __init__.py
│   └── advisor.py
├── orchestrator/            # Pipeline coordinator and market filter
│   ├── __init__.py
│   └── orchestrator.py
├── tests/
│   ├── test_e2e.py                          # End-to-end pipeline (mocked)
│   ├── test_orchestrator.py
│   ├── test_trade_advisor.py
│   ├── test_alpha_engine.py
│   ├── test_alpha_engine_integration.py
│   ├── test_market_fetcher.py
│   ├── test_market_fetcher_integration.py
│   ├── test_news_aggregator.py
│   └── test_news_aggregator_integration.py
├── .env                     # API keys (not committed)
├── .env.example             # Template
├── requirements.txt
├── architecture.md
└── description.md
```

## Architecture

See [architecture.md](architecture.md) for full design decisions including the market selection filter thresholds, data contracts between pipeline stages, and notes on framework choices.
