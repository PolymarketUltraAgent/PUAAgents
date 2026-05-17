import type { Context } from "grammy";
import { getTradesForUser } from "../../db/repositories/trade-repo.js";
import { userIdOf } from "../helpers.js";

/** /positions — list the markets this user has joined via the bot. */
export async function handlePositions(ctx: Context): Promise<void> {
  const userId = userIdOf(ctx);
  const trades = await getTradesForUser(userId);

  if (trades.length === 0) {
    await ctx.reply("No positions yet. Run /scan to find markets, then join one.");
    return;
  }

  const lines = trades.slice(0, 15).map((t) => {
    const question = t.question.length > 64 ? `${t.question.slice(0, 61)}...` : t.question;
    return (
      `• ${t.direction} ${t.shares} sh — ${question}\n` +
      `  ${t.notional} USDC @ ${t.entryPrice} · EV ${t.expectedValue} · ${t.status}`
    );
  });

  await ctx.reply(`📊 Your positions (${trades.length}):\n\n${lines.join("\n\n")}`);
}
