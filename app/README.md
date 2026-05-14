# Telegram Portal

A multi-user Telegram bot that wraps the PUAAgents Polymarket pipeline. Users
can scan markets on-demand, drill into news and AlphaEngine signals, and
subscribe to tags for periodic alerts.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram and copy
   the token.
2. Copy `.env.example` → `.env` and fill in `TELEGRAM_BOT_TOKEN`. The bot
   reuses the project-root `.env` for `TAVILY_API_KEY` and
   `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`.
3. From the project root:
   ```sh
   pip install -r requirements.txt
   pip install -r app/requirements.txt
   ```

## Run

From the project root:

```sh
python -m app
```

The bot uses long-polling — no webhook, no public IP, no reverse proxy
required. Stop it with Ctrl-C.

## Commands

**Discovery**
- `/scan [tag]` — full pipeline, returns trade decisions
- `/search <query>` — match markets by question keyword
- `/recommend` — top picks from your last scan, ranked by EV
- `/tags` — list available Polymarket tags

**Drill in**
- `/news <market_id>` — recent news for a market
- `/signal <market_id>` — AlphaEngine fair-value estimate

**Subscriptions**
- `/subscribe <tag>` — get alerts when new picks land for a tag
- `/unsubscribe <tag>`
- `/subscriptions` — show your tags

`<market_id>` values come from the output of a recent `/scan` or `/search`.

## Multi-user model

- **Open + rate-limited.** Anyone who finds the bot can DM it. Each command
  has a per-user cooldown (see `app/rate_limit.py`) so one user can't
  monopolize shared API quota.
- **Non-blocking.** Long-running calls (LLM, news API) run on a worker
  thread; the bot stays responsive to other users while one user's scan is
  in flight.
- **In-memory state.** Subscriptions, rate-limit counters, and cached
  snapshots live in RAM. **Restarting the bot wipes them** — a v1 trade-off.
  See `app/state.py` for the data model.

## File tour

| File | Purpose |
|---|---|
| `main.py` / `__main__.py` | Entry point; loads `.env`, checks required keys, hands off to `bot.run()`. |
| `bot.py` | Builds the `telegram.ext.Application`, registers handlers and the periodic job. |
| `handlers.py` | One async callback per command. |
| `pipeline.py` | `asyncio.to_thread` wrappers around the synchronous orchestrator. |
| `state.py` | In-memory user store (lock-protected). |
| `rate_limit.py` | Per-user, per-command cooldowns. |
| `scheduler.py` | The periodic job that pushes alerts to subscribers. |
| `formatters.py` | Telegram HTML formatting for decisions, signals, news. |

## Disclaimer

Trade decisions are model output, not investment advice.
