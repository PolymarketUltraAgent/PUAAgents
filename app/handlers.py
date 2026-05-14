"""Command callbacks.

Every handler follows the same shape:
  1. Resolve user_id and rate-limit check.
  2. Send a placeholder "working" message.
  3. Await the async pipeline wrapper (which off-loads to a thread).
  4. Edit the placeholder with the formatted result, chunking if needed.

Long-running calls never block the event loop, so concurrent users keep
flowing through other handlers while one user's /scan is in flight.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import formatters, pipeline, rate_limit, state

log = logging.getLogger(__name__)

HELP_TEXT = (
    "<b>🤖 PUAAgents — Polymarket trade scout</b>\n\n"
    "<b>Discovery</b>\n"
    "/scan [tag] — run the full pipeline; returns trade decisions\n"
    "/search &lt;query&gt; — match markets by question keyword\n"
    "/recommend — top picks from your last scan, ranked by EV\n"
    "/tags — list available Polymarket tags\n\n"
    "<b>Drill in</b>\n"
    "/news &lt;market_id&gt; — recent news for a market\n"
    "/signal &lt;market_id&gt; — AlphaEngine fair-value estimate\n\n"
    "<b>Subscriptions</b>\n"
    "/subscribe &lt;tag&gt; — get alerts when new picks land for a tag\n"
    "/unsubscribe &lt;tag&gt;\n"
    "/subscriptions — show your tags\n\n"
    "<i>Rate limits apply per user. Decisions are model output, not "
    "investment advice.</i>"
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

async def _enforce_cooldown(update: Update, command: str) -> bool:
    """Return True if the command may proceed; otherwise reply and return False."""
    user_id = update.effective_user.id
    allowed, retry_after = await rate_limit.check(user_id, command)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Slow down — try /{command} again in {retry_after:.0f}s."
        )
        return False
    return True


async def _send_chunks(update: Update, message_id: int | None, text: str) -> None:
    """Send `text` chunked to Telegram's limit. If `message_id` is given,
    edit it with the first chunk, then send the rest as new messages.
    """
    chunks = formatters.chunk(text)
    chat = update.effective_chat

    if message_id is not None:
        await chat.send_chat_action("typing")
        await update.get_bot().edit_message_text(
            chat_id=chat.id,
            message_id=message_id,
            text=chunks[0],
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        chunks = chunks[1:]

    for c in chunks:
        await chat.send_message(c, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def _placeholder(update: Update, text: str) -> int:
    """Send a 'working' placeholder; return its message_id for later edit."""
    msg = await update.message.reply_text(text)
    return msg.message_id


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Ensure user is registered the moment they first interact.
    await state.get_or_create(update.effective_user.id)
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "tags"):
        return
    msg_id = await _placeholder(update, "🏷 Fetching tags…")
    try:
        all_tags = await pipeline.fetch_tags()
        await _send_chunks(update, msg_id, formatters.format_tags(all_tags))
    except Exception:
        log.exception("tags failed")
        await _send_chunks(update, msg_id, "❌ Could not fetch tags. Try again later.")


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "scan"):
        return

    user_id = update.effective_user.id
    args = context.args or []
    tag_arg = args[0].lower() if args else None
    tags_filter = [tag_arg] if tag_arg else None
    label = tag_arg or "all tags"

    msg_id = await _placeholder(
        update,
        f"🔍 Scanning {label}… this can take ~30–60s while the LLM weighs in.",
    )

    try:
        # Use the lower-level wrappers so we can cache snapshots for later
        # /news and /signal drill-downs without re-fetching markets.
        snapshots = await pipeline.get_market_snapshots(tags=tags_filter)
        candidates = await pipeline.select_markets(snapshots)
        await state.remember_snapshots(user_id, candidates)

        decisions = await pipeline.run(tags=tags_filter)
        await state.remember_decisions(user_id, decisions)

        await _send_chunks(update, msg_id, formatters.format_decisions(decisions))
    except Exception as exc:
        log.exception("scan failed for user %s", user_id)
        await _send_chunks(update, msg_id, f"❌ Scan failed: {_short_err(exc)}")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "search"):
        return

    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text(
            "Usage: <code>/search &lt;keyword&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    user_id = update.effective_user.id
    msg_id = await _placeholder(update, f"🔎 Searching for “{query}”…")
    try:
        # Search across all tags. The fetcher returns up to 20 per tag, which
        # is plenty for keyword matching on the question text.
        snapshots = await pipeline.get_market_snapshots()
        q = query.lower()
        matches = [s for s in snapshots if q in s.question.lower()]
        matches.sort(key=lambda s: s.volume_24h, reverse=True)
        top = matches[:10]
        await state.remember_snapshots(user_id, top)
        await _send_chunks(
            update,
            msg_id,
            formatters.format_snapshots(
                top, header=f"🔎 Matches for “{query}” ({len(matches)} total)"
            ),
        )
    except Exception as exc:
        log.exception("search failed for user %s", user_id)
        await _send_chunks(update, msg_id, f"❌ Search failed: {_short_err(exc)}")


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "recommend"):
        return
    user_id = update.effective_user.id
    user = await state.get_or_create(user_id)
    if not user.last_decisions:
        await update.message.reply_text(
            "No prior scan in memory. Run /scan first.", parse_mode=ParseMode.HTML
        )
        return
    await _send_chunks(
        update, None, formatters.format_recommendations(user.last_decisions)
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "news"):
        return
    snapshot = await _resolve_market(update, context)
    if snapshot is None:
        return
    msg_id = await _placeholder(update, "📰 Fetching news…")
    try:
        articles = await pipeline.fetch_news(snapshot.question)
        await _send_chunks(update, msg_id, formatters.format_news(articles, snapshot.question))
    except Exception as exc:
        log.exception("news failed")
        await _send_chunks(update, msg_id, f"❌ News fetch failed: {_short_err(exc)}")


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "signal"):
        return
    snapshot = await _resolve_market(update, context)
    if snapshot is None:
        return
    msg_id = await _placeholder(update, "🎯 Running AlphaEngine…")
    try:
        sig = await pipeline.analyze_market(snapshot)
        await _send_chunks(update, msg_id, formatters.format_signal(sig))
    except Exception as exc:
        log.exception("signal failed")
        await _send_chunks(update, msg_id, f"❌ Signal failed: {_short_err(exc)}")


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "subscribe"):
        return
    tag = _single_arg(context, lower=True)
    if not tag:
        await update.message.reply_text("Usage: <code>/subscribe &lt;tag&gt;</code>", parse_mode=ParseMode.HTML)
        return
    added = await state.subscribe(update.effective_user.id, tag)
    if added:
        await update.message.reply_text(
            f"✅ Subscribed to <code>{tag}</code>. You'll get alerts on new picks.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"You're already subscribed to <code>{tag}</code>.",
            parse_mode=ParseMode.HTML,
        )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "unsubscribe"):
        return
    tag = _single_arg(context, lower=True)
    if not tag:
        await update.message.reply_text("Usage: <code>/unsubscribe &lt;tag&gt;</code>", parse_mode=ParseMode.HTML)
        return
    removed = await state.unsubscribe(update.effective_user.id, tag)
    if removed:
        await update.message.reply_text(
            f"🗑 Unsubscribed from <code>{tag}</code>.", parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"You weren't subscribed to <code>{tag}</code>.", parse_mode=ParseMode.HTML
        )


async def subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_cooldown(update, "subscriptions"):
        return
    user = await state.get_or_create(update.effective_user.id)
    if not user.subscribed_tags:
        await update.message.reply_text(
            "No subscriptions yet. Try <code>/subscribe politics</code>.",
            parse_mode=ParseMode.HTML,
        )
        return
    tags_list = ", ".join(f"<code>{t}</code>" for t in sorted(user.subscribed_tags))
    await update.message.reply_text(
        f"<b>Your subscriptions:</b> {tags_list}", parse_mode=ParseMode.HTML
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _single_arg(context: ContextTypes.DEFAULT_TYPE, lower: bool = False) -> str | None:
    args = context.args or []
    if not args:
        return None
    arg = args[0].strip()
    return arg.lower() if lower else arg


async def _resolve_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Look up a market the user previously saw by ID.

    Returns the MarketSnapshot or None (after replying to the user) if the
    argument is missing or unknown.
    """
    market_id = _single_arg(context)
    if not market_id:
        await update.message.reply_text(
            "Usage: <code>/news &lt;market_id&gt;</code> or "
            "<code>/signal &lt;market_id&gt;</code>. "
            "Get IDs from a recent /scan or /search.",
            parse_mode=ParseMode.HTML,
        )
        return None

    user = await state.get_or_create(update.effective_user.id)
    snapshot = user.last_snapshots.get(market_id)
    if snapshot is None:
        await update.message.reply_text(
            f"Don't have <code>{market_id}</code> in your recent results. "
            "Run /scan or /search first.",
            parse_mode=ParseMode.HTML,
        )
        return None
    return snapshot


def _short_err(exc: Exception) -> str:
    """Trim exception messages to something safe to put in a chat bubble."""
    msg = str(exc) or exc.__class__.__name__
    return msg[:200]
