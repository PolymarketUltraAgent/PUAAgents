# PUA Agent

An agent that reads from Polymarket, identifies mispriced prediction markets, and outputs trade decisions.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Project Structure

```
PUAAgents/
├── market_fetcher/
│   ├── __init__.py
│   └── fetcher.py          # Fetches live market data from Polymarket API
├── news_aggregator/
│   ├── __init__.py
│   └── aggregator.py       # Fetches relevant news via Tavily API
├── tests/
│   ├── test_market_fetcher.py
│   ├── test_market_fetcher_integration.py
│   ├── test_news_aggregator.py
│   └── test_news_aggregator_integration.py
├── .env                    # API keys (not committed)
├── .env.example            # Template for .env
├── requirements.txt
├── architecture.md
└── description.md
```

## Architecture

See [architecture.md](architecture.md) for the full system design. The pipeline is:

1. **MarketFetcher** — pulls live prices and order books from Polymarket
2. **AlphaEngine** — compares implied vs LLM-estimated fair probability to detect mispricing
3. **TradeAdvisor** — outputs a Kelly-sized `TradeDecision` (YES / NO / PASS)

## Usage

```python
from market_fetcher import get_market_snapshots

snapshots = get_market_snapshots(categories=["politics", "economics"], limit=20)
for s in snapshots:
    print(s.market_id, s.question, s.yes_price)
```
