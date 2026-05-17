# PUA Telegram Bot

A Telegram interface to the PUA Agent. Users register an agentic wallet, ask
the agent to scan Polymarket, and join surfaced markets — all from chat.

```
Telegram user
   │  /register, /scan, /trade ...
   ▼
PUA Telegram Bot (this app, TypeScript)
   ├─ wallet/   → Circle CLI  → agentic wallet (Arc Testnet), bridge to Polygon Amoy
   ├─ pua/      → pua_cli.py  → PUA pipeline (Polymarket → news → LLM → Kelly sizing)
   └─ trade/    → bridge USDC + simulated Polymarket fill, persisted in SQLite
```

## What it does

- **Agentic wallet** — on first `/register`, creates a Circle agent wallet for
  the user, verified by email OTP. Reused from `../agentic-wallet-testing`.
- **Session keys** — each user's Circle CLI session lives under
  `SESSION_DIR/<telegramUserId>`; the DB tracks a 7-day expiry and re-prompts
  login when it lapses. (On macOS, sessions share the host keychain — see Notes.)
- **PUA agent** — `/scan` runs the Python pipeline and returns Kelly-sized
  YES/NO/PASS decisions.
- **Joining a market** — `/trade` bridges USDC from Arc Testnet to Polygon Amoy
  (a real testnet transaction) and records a **simulated** Polymarket fill.
  Polymarket settles on Polygon mainnet, which the testnet wallet can't reach.

## Prerequisites

1. **Node.js 22+**
2. **Circle CLI** on `PATH`:
   ```bash
   npm install -g @circle-fin/cli
   ```
3. **PUA Python pipeline** — set up the repo venv so `pua_cli.py` can import it:
   ```bash
   cd ..                       # PUAAgents repo root
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env        # add TAVILY_API_KEY + an LLM key
   ```
4. A **Telegram bot token** from [@BotFather](https://t.me/BotFather).

## Setup

```bash
cd app
npm install
cp .env.example .env
```

Edit `.env`:

| Variable             | Purpose                                                        |
|----------------------|----------------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather (required)                               |
| `PUA_REPO_ROOT`      | Path to the PUAAgents repo root (default `..`)                 |
| `PYTHON_BIN`         | Python interpreter — point at the repo venv, e.g. `../.venv/bin/python` |
| `TRADE_BANKROLL`     | Demo bankroll in USDC; trade notional = `size × TRADE_BANKROLL` |
| `DATABASE_URL`       | SQLite path (default `./data/bot.sqlite`)                      |
| `SESSION_DIR`        | Per-user Circle CLI session storage                            |
| `GATEWAY_API`        | Circle Gateway API base URL                                    |

## Run

```bash
npm run dev     # watch mode
npm start       # one-off
```

## Commands

| Command            | Description                                          |
|--------------------|------------------------------------------------------|
| `/start`, `/help`  | Welcome and usage                                    |
| `/register <email>`| Create the agentic wallet (email-OTP login)          |
| `/otp <code>`      | Submit the OTP (or just send the code as plain text) |
| `/wallet`          | Show wallet address                                  |
| `/balance`         | Show USDC balances (Arc Testnet + Polygon Amoy)      |
| `/fund`            | Request testnet USDC from the faucet                 |
| `/scan [tags]`     | Run the PUA agent (default tags: politics economics crypto) |
| `/trade <id>`      | Join a scanned market (or tap a Join button)         |
| `/positions`       | List markets joined via the bot                      |

## Project structure

```
app/
├── pua_cli.py                  JSON entrypoint for the PUA Python pipeline
└── src/
    ├── index.ts                bot bootstrap + routing
    ├── config/                 env + chain/gateway constants
    ├── db/                     SQLite (drizzle) — users + trades
    ├── wallet/                 Circle CLI wallet & gateway services
    ├── pua/pua-agent.ts        spawns pua_cli.py, parses decisions
    ├── trade/trade-executor.ts bridge + simulated fill
    └── bot/                    session state, helpers, command handlers
```

## Notes & limitations

- **macOS sessions are shared.** The Circle CLI relies on the host keychain, so
  per-user `HOME` isolation only applies on Linux/Docker. Run one user at a time
  on macOS, or deploy in Docker for true multi-user isolation.
- **Trades are simulated.** The bridge leg is a real testnet transaction; the
  Polymarket order is mocked because the market settles on Polygon mainnet.
- **OTP state is in memory.** A bot restart mid-registration means re-running
  `/register`. Persisted wallet/session data survives restarts.
