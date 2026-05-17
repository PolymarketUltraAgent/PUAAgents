import type { Context } from "grammy";
import { InlineKeyboard } from "grammy";
import { logger } from "../../utils/logger.js";
import { scanMarkets, type TradeDecision } from "../../pua/pua-agent.js";
import { cacheDecisions } from "../session.js";
import { requireUser, userIdOf } from "../helpers.js";

const DEFAULT_TAGS = ["politics", "economics", "crypto"];
const TOP_N = 5;

function formatDecision(d: TradeDecision, index: number): string {
  const ev = d.expected_value >= 0 ? `+${d.expected_value}` : `${d.expected_value}`;
  const rationale = d.rationale.length > 220 ? `${d.rationale.slice(0, 217)}...` : d.rationale;
  return (
    `${index + 1}. ${d.direction} — ${d.question}\n` +
    `   entry ${d.entry_price} · size ${d.size} · EV ${ev}\n` +
    `   ${rationale}\n` +
    `   id: ${d.market_id}`
  );
}

/** /scan [tags] — run the PUA pipeline and present tradeable markets. */
export async function handleScan(ctx: Context): Promise<void> {
  const user = await requireUser(ctx);
  if (!user) return;

  const userId = userIdOf(ctx);
  const raw = String(ctx.match ?? "").trim();
  const tags = raw ? raw.split(/[,\s]+/).filter(Boolean) : DEFAULT_TAGS;

  const status = await ctx.reply(
    `🔍 Scanning Polymarket for: ${tags.join(", ")}\n` +
      `The agent is fetching markets, news, and running analysis — this can take a couple of minutes...`
  );

  try {
    const decisions = await scanMarkets(tags, TOP_N);
    cacheDecisions(userId, decisions);

    const actionable = decisions.filter((d) => d.direction !== "PASS");
    if (actionable.length === 0) {
      await ctx.api.editMessageText(
        ctx.chat!.id,
        status.message_id,
        `No actionable edges found (analyzed ${decisions.length} market(s)).\nTry different tags, e.g. /scan sports tech.`
      );
      return;
    }

    const body = actionable.map(formatDecision).join("\n\n");
    const keyboard = new InlineKeyboard();
    actionable.forEach((d, i) => {
      keyboard.text(`Join ${i + 1}`, `trade:${d.market_id}`);
      if ((i + 1) % 3 === 0) keyboard.row();
    });

    await ctx.api.editMessageText(
      ctx.chat!.id,
      status.message_id,
      `🎯 Found ${actionable.length} actionable market(s):\n\n${body}\n\n` +
        `Tap a button below or use /trade <id> to join.`,
      { reply_markup: keyboard }
    );
  } catch (e) {
    logger.error({ err: e, userId }, "scan failed");
    await ctx.api.editMessageText(
      ctx.chat!.id,
      status.message_id,
      `❌ Scan failed: ${(e as Error).message}`
    );
  }
}
