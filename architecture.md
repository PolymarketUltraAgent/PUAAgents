# PUA Agent Architecture

## Overview

An agent pipeline that reads live Polymarket data, identifies mispriced markets using LLM-grounded analysis, and outputs structured trade decisions.

## Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                      Orchestrator Agent                  │
│  - Fetches all tags from Polymarket                      │
│  - Fetches markets across all tags                       │
│  - Applies market filter (see Market Selection Filter)   │
│  - Fans out to AlphaEngine for filtered markets only     │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────▼────────┐
    │   Data Layer     │
    │                  │
    │  MarketFetcher   │  ←── Polymarket Gamma + CLOB API
    │  - all tags      │
    │  - markets list  │
    │  - order books   │
    └────────┬────────┘
             │
    ┌────────▼──────────────────────────────────────────┐
    │              Market Selection Filter               │
    │                                                    │
    │  Hard filters (Option 1 — liquidity/activity):     │
    │  - volume_24h > 10,000                             │
    │  - liquidity  > 5,000                              │
    │  - spread     < 0.10                               │
    │  - competitive > 0.80                              │
    │  - acceptingOrders = true                          │
    │                                                    │
    │  Soft filter (Option 2 — price proximity):         │
    │  - 0.05 < yes_price < 0.95                         │
    │    (markets near 50/50 have the most alpha)        │
    │                                                    │
    │  Sort by volume_24h desc, take top N (default 20)  │
    └────────┬──────────────────────────────────────────┘
             │
    ┌────────▼────────────────────────────────┐
    │           Analysis Layer                 │
    │                                          │
    │  ┌──────────────┐  ┌─────────────────┐  │
    │  │ PricingModel │  │  NewsAggregator │  │
    │  │ - implied    │  │  - recent news  │  │
    │  │   probability│  │  - sentiment    │  │
    │  │ - fair value │  │  - resolution   │  │
    │  └──────┬───────┘  │    criteria     │  │
    │         │          └────────┬────────┘  │
    │         └──────────┬────────┘           │
    │              ┌─────▼──────┐             │
    │              │ AlphaEngine│             │
    │              │ - mispricing│            │
    │              │   detection │            │
    │              │ - edge calc │            │
    │              └─────┬──────┘             │
    └────────────────────┼────────────────────┘
                         │
    ┌────────────────────▼────────────────────┐
    │           Decision Layer                 │
    │                                          │
    │  TradeAdvisor                            │
    │  - position sizing (Kelly criterion)     │
    │  - confidence threshold gating           │
    │  - outputs structured TradeDecision      │
    └─────────────────────────────────────────┘
```

## Data Contracts

Each stage passes a typed schema to the next:

```
MarketSnapshot → AlphaSignal → TradeDecision
```

### MarketSnapshot
- `market_id`, `question`, `tag`
- `yes_price`, `no_price` (implied probabilities from order book mid)
- `volume_24h`, `liquidity`
- `spread` — `best_ask - best_bid`, liquidity quality signal
- `competitive` — Polymarket's activity score (0–1)
- `accepting_orders` — whether the market is currently tradeable

### AlphaSignal
- `market_id`
- `implied_prob` — from order book
- `fair_prob` — LLM estimate grounded in news
- `edge` — `abs(fair_prob - implied_prob)`
- `confidence` — model confidence (0–1)
- `rationale` — free-text reasoning

### TradeDecision
- `market_id`, `direction` (`YES` | `NO` | `PASS`)
- `size` — Kelly-sized position
- `entry_price`, `expected_value`
- `rationale`

## Component: MarketFetcher

Thin I/O wrapper around the Polymarket CLOB API. No LLM involved — pure HTTP calls that return normalized data.

**Responsibilities**
- List active markets filtered by category (`politics`, `economy`)
- Fetch order book for a given market → compute mid-price as implied probability
- Fetch recent trade history for volume/liquidity signals

**Key API endpoints used**
- `GET /markets` — paginated list of active markets with metadata
- `GET /book?token_id=<id>` — order book (bids/asks) for YES token
- `GET /trades?market=<id>` — recent fills for volume context

**Output**: `MarketSnapshot` (see Data Contracts below)

**Design notes**
- Stateless — called fresh each scan cycle, no caching
- Rate-limit aware: Polymarket CLOB API has a 10 req/s limit; add a small delay between batch calls
- `implied_prob = (best_ask + best_bid) / 2` on the YES token order book

## Alpha Detection Logic

The `AlphaEngine` compares market implied probability against an LLM-estimated fair probability:

1. Fetch current order book → compute `implied_prob` from mid-price
2. Pull recent news via search API → ground LLM estimate
3. LLM estimates `fair_prob` given news + resolution criteria
4. `edge = abs(fair_prob - implied_prob)`
5. Signal only if `edge > threshold` (recommended starting point: 0.05)

## Data Sources

| Data | Source | Reason |
|------|--------|--------|
| Live prices & order books | Polymarket CLOB API (direct calls) | Always fresh — staleness kills alpha |
| News & context | Tavily or Perplexity API | Real-time grounding for fair value |
| Market descriptions | Polymarket API | Structured, no vector DB needed |

**Note on Vector DB**: Not used for core pipeline. Only worth adding if semantic discovery across 100s of markets becomes a requirement.

## Technology Stack

| Component | Choice |
|-----------|--------|
| Agent framework | Anthropic SDK (direct tool-use + structured output) |
| Language | Python |
| Polymarket client | `py-clob-client` or raw `httpx` |
| News grounding | Tavily / Perplexity API |
| Scheduling | Cron or `/loop` for periodic scans |
| Output | JSON `TradeDecision` — auditable, actionable |

**Note on LangChain**: Not recommended. Abstractions obscure LLM calls (bad for auditability in a financial context) and API churn introduces instability. Use LangGraph only if the workflow grows to need parallel branches or complex state management.

## Recommended Starting Scope

- Fetch all tags dynamically from the API (no hardcoded list)
- Apply Market Selection Filter to reduce ~2000 markets to top 20
- Deep per-market analysis (NewsAggregator + AlphaEngine) on filtered set only
- Expand filter thresholds or top-N once pipeline is validated
