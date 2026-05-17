import type { Context } from "grammy";
import { logger } from "../../utils/logger.js";
import { joinMarket } from "../../trade/trade-executor.js";
import { getCachedDecision } from "../session.js";
import { requireUser, userIdOf, makeStepEmitter } from "../helpers.js";

/**
 * /trade <id> (or a Join button) — join a market the PUA agent surfaced.
 * `marketId` is passed explicitly from callback queries; otherwise read from
 * the command argument.
 */
export async function handleTrade(ctx: Context, marketId?: string): Promise<void> {
  const user = await requireUser(ctx);
  if (!user) return;

  const userId = userIdOf(ctx);
  const id = (marketId ?? (typeof ctx.match === "string" ? ctx.match : "")).trim();

  if (!id) {
    await ctx.reply("Usage: /trade <market_id>\nRun /scan first, then tap a Join button or pass the id.");
    return;
  }

  const decision = getCachedDecision(userId, id);
  if (!decision) {
    await ctx.reply("I don't have that market cached. Run /scan first, then try again.");
    return;
  }

  const progress = await ctx.reply(`Joining market ${id}...\n${decision.direction} — ${decision.question}`);
  const emit = makeStepEmitter(ctx, progress.message_id);

  try {
    const { trade, bridged } = await joinMarket(userId, user.walletAddress, decision, emit);

    const note = bridged
      ? "USDC bridged to Polygon Amoy; Polymarket fill simulated."
      : "Bridge unavailable on testnet; fill recorded as simulated-only.";

    await ctx.reply(
      `✅ Joined market ${trade.marketId}\n\n` +
        `${trade.direction} — ${trade.question}\n` +
        `Notional: ${trade.notional} USDC @ ${trade.entryPrice}\n` +
        `Shares: ${trade.shares} · EV: ${trade.expectedValue}\n` +
        `Status: ${trade.status}\n\n${note}\n\nSee all positions with /positions.`
    );
  } catch (e) {
    logger.error({ err: e, userId, marketId: id }, "trade failed");
    await ctx.reply(`❌ Could not join market: ${(e as Error).message}`);
  }
}
