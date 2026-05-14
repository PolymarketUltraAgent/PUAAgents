"""Periodic scan + push-alerts to subscribed users.

Runs as a single JobQueue task. Each tick:
  1. Gathers the union of tags across all users.
  2. Runs the pipeline once per tag (deduplicates work across users).
  3. For each user subscribed to that tag, sends decisions for markets that
     resolved to YES/NO and that we haven't alerted that user about yet.

Defensive on purpose: one user's bad chat state must not bring down the job.
"""
from __future__ import annotations

import logging

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import formatters, pipeline, state

log = logging.getLogger(__name__)

# 1h default. Tune at registration time in bot.py.
DEFAULT_INTERVAL_S = 3600


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    users = await state.all_users()
    subscribed: dict[str, list[int]] = {}
    for u in users:
        for tag in u.subscribed_tags:
            subscribed.setdefault(tag, []).append(u.user_id)

    if not subscribed:
        log.debug("scheduled_scan: no subscriptions, skipping")
        return

    log.info(
        "scheduled_scan: %d tags, %d users", len(subscribed), len(users)
    )

    for tag, user_ids in subscribed.items():
        try:
            decisions = await pipeline.run(tags=[tag], top_n=10)
        except Exception:
            log.exception("scheduled_scan: pipeline failed for tag=%s", tag)
            continue

        actionable = [d for d in decisions if d.direction != "PASS"]
        if not actionable:
            continue

        for uid in user_ids:
            try:
                await _push_new_picks(context, uid, tag, actionable)
            except Exception:
                log.exception(
                    "scheduled_scan: push failed user=%s tag=%s", uid, tag
                )


async def _push_new_picks(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    tag: str,
    actionable,
) -> None:
    user = await state.get_or_create(user_id)
    new_picks = [d for d in actionable if d.market_id not in user.seen_alert_market_ids]
    if not new_picks:
        return

    # Cache snapshots-by-id-less data so the user can still /signal on these
    # — but we don't have MarketSnapshots here, only TradeDecisions. The user
    # can run /scan <tag> to refresh and unlock /signal drill-ins.
    await state.mark_alerted(user_id, [d.market_id for d in new_picks])

    text = formatters.format_alert(tag, new_picks)
    if not text:
        return
    for chunk in formatters.chunk(text):
        await context.bot.send_message(
            chat_id=user_id,
            text=chunk,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
