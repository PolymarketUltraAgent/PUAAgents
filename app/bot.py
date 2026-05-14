"""Bot assembly: builds the Application, registers handlers, starts polling."""
from __future__ import annotations

import logging
import os

from telegram.ext import Application, CommandHandler

from . import handlers, scheduler

log = logging.getLogger(__name__)


def build_application(token: str, scan_interval_s: int = scheduler.DEFAULT_INTERVAL_S) -> Application:
    """Construct the Application with handlers and the periodic job wired up.

    Separated from `run()` so tests can inspect the wiring without polling.
    """
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("tags", handlers.tags))
    app.add_handler(CommandHandler("scan", handlers.scan))
    app.add_handler(CommandHandler("search", handlers.search))
    app.add_handler(CommandHandler("recommend", handlers.recommend))
    app.add_handler(CommandHandler("news", handlers.news))
    app.add_handler(CommandHandler("signal", handlers.signal))
    app.add_handler(CommandHandler("subscribe", handlers.subscribe))
    app.add_handler(CommandHandler("unsubscribe", handlers.unsubscribe))
    app.add_handler(CommandHandler("subscriptions", handlers.subscriptions))

    if app.job_queue is not None:
        # Stagger the first run by `scan_interval_s` so the bot finishes
        # starting up before the first heavy LLM call.
        app.job_queue.run_repeating(
            scheduler.scheduled_scan,
            interval=scan_interval_s,
            first=scan_interval_s,
            name="scheduled_scan",
        )
    else:
        log.warning(
            "JobQueue unavailable — install python-telegram-bot[job-queue] "
            "to enable scheduled alerts."
        )

    return app


def run() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    interval = int(os.getenv("SCAN_INTERVAL_S", scheduler.DEFAULT_INTERVAL_S))
    app = build_application(token, scan_interval_s=interval)
    log.info("Bot starting (poll mode, scan interval %ds)…", interval)
    app.run_polling(close_loop=False)
