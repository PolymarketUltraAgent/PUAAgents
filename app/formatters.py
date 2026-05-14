"""Format pipeline outputs into Telegram HTML messages.

Why HTML instead of MarkdownV2: MarkdownV2 demands escaping `.`, `-`, `+`,
`(`, `)`, `=`, `!`, etc. — every market question would need defensive
escaping. HTML mode only needs `<`, `>`, `&` escaped, which `html.escape`
handles in one call.
"""
from __future__ import annotations

import html

from market_fetcher import MarketSnapshot, Tag
from news_aggregator import NewsArticle
from alpha_engine import AlphaSignal
from trade_advisor import TradeDecision

# Telegram hard limit is 4096; leave headroom for any trailing footer.
TELEGRAM_MAX_LEN = 4000

DIRECTION_EMOJI = {"YES": "✅", "NO": "❌", "PASS": "⏸"}


def _e(text: str) -> str:
    """Escape a single string for safe inclusion in HTML mode."""
    return html.escape(str(text), quote=False)


def format_decision(d: TradeDecision) -> str:
    emoji = DIRECTION_EMOJI.get(d.direction, "•")
    lines = [
        f"{emoji} <b>{_e(d.direction)}</b> — {_e(d.question)}",
        f"<code>{_e(d.market_id)}</code>",
        f"Entry: <b>{d.entry_price:.2%}</b> · "
        f"Size: <b>{d.size:.3f}</b> · "
        f"EV: <b>{d.expected_value:+.2%}</b>",
        f"<i>{_e(d.rationale)}</i>",
    ]
    return "\n".join(lines)


def format_decisions(decisions: list[TradeDecision]) -> str:
    if not decisions:
        return "<i>No markets passed the filters.</i>"

    actionable = [d for d in decisions if d.direction != "PASS"]
    skipped = len(decisions) - len(actionable)

    header = (
        f"<b>📊 Scan results</b> — {len(actionable)} actionable, {skipped} passed"
    )
    body = "\n\n".join(format_decision(d) for d in decisions)
    return f"{header}\n\n{body}"


def format_recommendations(decisions: list[TradeDecision], top: int = 5) -> str:
    actionable = [d for d in decisions if d.direction != "PASS"]
    if not actionable:
        return "<i>No actionable picks in your last scan. Run /scan first.</i>"

    ranked = sorted(actionable, key=lambda d: d.expected_value, reverse=True)[:top]
    header = f"<b>⭐ Top {len(ranked)} recommendations</b> (by EV)"
    body = "\n\n".join(format_decision(d) for d in ranked)
    return f"{header}\n\n{body}"


def format_snapshot(s: MarketSnapshot) -> str:
    return (
        f"• {_e(s.question)}\n"
        f"  <code>{_e(s.market_id)}</code> · "
        f"YES <b>{s.yes_price:.0%}</b> · "
        f"vol24h <b>${s.volume_24h:,.0f}</b> · "
        f"tag <i>{_e(s.tag)}</i>"
    )


def format_snapshots(snapshots: list[MarketSnapshot], header: str) -> str:
    if not snapshots:
        return f"<b>{header}</b>\n\n<i>No matches.</i>"
    body = "\n\n".join(format_snapshot(s) for s in snapshots)
    return f"<b>{header}</b>\n\n{body}"


def format_signal(s: AlphaSignal) -> str:
    badge = "🎯 SIGNAL" if s.is_signal else "💤 no signal"
    return (
        f"<b>{badge}</b> — {_e(s.question)}\n"
        f"<code>{_e(s.market_id)}</code>\n"
        f"Implied: <b>{s.implied_prob:.0%}</b> · "
        f"Fair: <b>{s.fair_prob:.0%}</b> · "
        f"Edge: <b>{s.edge:.2%}</b> · "
        f"Confidence: <b>{s.confidence:.0%}</b>\n"
        f"<i>{_e(s.rationale)}</i>\n"
        f"<sub>via {_e(s.provider)}</sub>"
    )


def format_news(articles: list[NewsArticle], question: str) -> str:
    header = f"<b>📰 News for:</b> {_e(question)}"
    if not articles:
        return f"{header}\n\n<i>No recent articles found.</i>"
    items = []
    for i, a in enumerate(articles, 1):
        date = f" ({_e(a.published_date)})" if a.published_date else ""
        items.append(
            f"{i}. <a href=\"{_e(a.url)}\">{_e(a.title)}</a>{date}\n"
            f"   {_e(a.content)}"
        )
    return f"{header}\n\n" + "\n\n".join(items)


def format_tags(tags: list[Tag], limit: int = 50) -> str:
    if not tags:
        return "<i>No tags returned by the API.</i>"
    shown = tags[:limit]
    body = ", ".join(f"<code>{_e(t.slug)}</code>" for t in shown)
    suffix = f"\n\n…and {len(tags) - len(shown)} more." if len(tags) > limit else ""
    return f"<b>🏷 Available tags</b>\n\n{body}{suffix}"


def format_alert(tag: str, decisions: list[TradeDecision]) -> str:
    if not decisions:
        return ""
    header = f"<b>🔔 New picks for <code>{_e(tag)}</code></b>"
    body = "\n\n".join(format_decision(d) for d in decisions)
    return f"{header}\n\n{body}"


def chunk(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Split a long message into Telegram-safe chunks.

    Prefers splitting on blank lines so card-style entries stay intact;
    falls back to hard-cutting if a single segment is too long.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        if len(block) > limit:
            # Single block is over the limit — flush, then hard-cut it.
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(block), limit):
                chunks.append(block[i : i + limit])
            continue

        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit:
            chunks.append(current)
            current = block
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks
