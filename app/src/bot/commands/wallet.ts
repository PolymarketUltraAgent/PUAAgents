import type { Context } from "grammy";
import { CHAINS } from "../../config/constants.js";
import { logger } from "../../utils/logger.js";
import { getBalance, fundTestnet, type TokenBalance } from "../../wallet/wallet-service.js";
import { requireUser, userIdOf } from "../helpers.js";

function formatBalances(balances: TokenBalance[]): string {
  if (balances.length === 0) return "0 USDC";
  return balances.map((b) => `${b.amount} ${b.symbol}`).join(", ");
}

/** /wallet — show the user's agentic wallet address. */
export async function handleWallet(ctx: Context): Promise<void> {
  const user = await requireUser(ctx);
  if (!user) return;

  await ctx.reply(
    `👛 Your agentic wallet\n\nAddress:\n${user.walletAddress}\nEmail: ${user.email}\n\n` +
      `Use /balance to see funds, /fund to top up testnet USDC.`
  );
}

/** /balance — show USDC balances on Arc Testnet and Polygon Amoy. */
export async function handleBalance(ctx: Context): Promise<void> {
  const user = await requireUser(ctx);
  if (!user) return;

  const userId = userIdOf(ctx);
  const msg = await ctx.reply("Fetching balances...");

  try {
    const [arc, polygon] = await Promise.all([
      getBalance(userId, user.walletAddress, CHAINS.ARC_TESTNET),
      getBalance(userId, user.walletAddress, CHAINS.POLYGON_AMOY),
    ]);

    await ctx.api.editMessageText(
      ctx.chat!.id,
      msg.message_id,
      `💰 Balances for ${user.walletAddress}\n\n` +
        `Arc Testnet: ${formatBalances(arc)}\n` +
        `Polygon Amoy: ${formatBalances(polygon)}`
    );
  } catch (e) {
    logger.error({ err: e, userId }, "balance lookup failed");
    await ctx.api.editMessageText(
      ctx.chat!.id,
      msg.message_id,
      `❌ Could not fetch balances: ${(e as Error).message}`
    );
  }
}

/** /fund — request testnet USDC from the Circle faucet on Arc Testnet. */
export async function handleFund(ctx: Context): Promise<void> {
  const user = await requireUser(ctx);
  if (!user) return;

  const userId = userIdOf(ctx);
  await ctx.reply("Requesting testnet USDC from the faucet (Arc Testnet)...");

  try {
    await fundTestnet(userId, user.walletAddress, CHAINS.ARC_TESTNET);
    await ctx.reply(
      "✅ Faucet request submitted. Funds usually arrive within a minute — check with /balance."
    );
  } catch (e) {
    logger.error({ err: e, userId }, "fund failed");
    await ctx.reply(`❌ Funding failed: ${(e as Error).message}`);
  }
}
