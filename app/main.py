"""Entry point: `python -m app`.

Loads environment from the project-root `.env` first (shared API keys for
the underlying pipeline) and then `app/.env` (Telegram-specific overrides),
validates that the required keys are present, and hands control to bot.run().
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    here = Path(__file__).resolve().parent
    root_env = here.parent / ".env"
    app_env = here / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    if app_env.exists():
        load_dotenv(app_env, override=True)


def _require_env() -> list[str]:
    """Return a list of missing required env vars."""
    missing = []
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("TAVILY_API_KEY"):
        missing.append("TAVILY_API_KEY")
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY")):
        missing.append("ANTHROPIC_API_KEY or GEMINI_API_KEY")
    return missing


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    _load_env()

    missing = _require_env()
    if missing:
        print(
            "Missing required environment variables:\n  - "
            + "\n  - ".join(missing)
            + "\nSee app/.env.example.",
            file=sys.stderr,
        )
        return 2

    # Imported here so that env vars are already loaded when underlying
    # modules (alpha_engine, news_aggregator) call `load_dotenv()` at import.
    from . import bot

    bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
