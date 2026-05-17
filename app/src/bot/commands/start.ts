import type { Context } from "grammy";

const WELCOME = `👋 Welcome to the PUA Agent bot.

I run an AI agent that scans Polymarket prediction markets, finds mispriced
opportunities, and helps you join them with your own agentic wallet.

How to use me:
1. /register <email> — create your Circle agentic wallet (verified by email OTP)
2. /fund — get testnet USDC from the faucet
3. /scan <tags> — find tradeable markets (e.g. /scan politics economics)
4. /trade <id> — join a market (or tap a Join button after /scan)

Other commands:
/wallet — show your wallet address
/balance — show USDC balances
/positions — list markets you've joined
/help — show this message

Note: trades use testnet funds. The on-chain bridge is real; the Polymarket
fill is simulated, since Polymarket settles on mainnet.`;

export async function handleStart(ctx: Context): Promise<void> {
  await ctx.reply(WELCOME);
}
