import { Bot } from "grammy";
import { env } from "./config/env.js";
import { logger } from "./utils/logger.js";
import "./db/index.js";
import { handleStart } from "./bot/commands/start.js";
import { handleRegister, handleOtp } from "./bot/commands/register.js";
import { handleWallet, handleBalance, handleFund } from "./bot/commands/wallet.js";
import { handleScan } from "./bot/commands/scan.js";
import { handleTrade } from "./bot/commands/trade.js";
import { handlePositions } from "./bot/commands/positions.js";
import { getState } from "./bot/session.js";
import { userIdOf } from "./bot/helpers.js";

const bot = new Bot(env.TELEGRAM_BOT_TOKEN);

bot.command(["start", "help"], handleStart);
bot.command("register", handleRegister);
bot.command("otp", (ctx) => handleOtp(ctx, String(ctx.match ?? "")));
bot.command("wallet", handleWallet);
bot.command("balance", handleBalance);
bot.command("fund", handleFund);
bot.command("scan", handleScan);
bot.command("trade", (ctx) => handleTrade(ctx));
bot.command("positions", handlePositions);

// Plain text: interpret as the OTP code when we're awaiting one.
bot.on("message:text", async (ctx) => {
  if (ctx.message.text.startsWith("/")) return;
  if (getState(userIdOf(ctx)).kind === "awaiting_otp") {
    await handleOtp(ctx, ctx.message.text.trim());
    return;
  }
  await ctx.reply("Send /help to see what I can do.");
});

// Inline "Join" buttons emitted by /scan.
bot.callbackQuery(/^trade:(.+)$/, async (ctx) => {
  await ctx.answerCallbackQuery();
  await handleTrade(ctx, ctx.match[1]);
});

bot.catch((err) => {
  logger.error({ err: err.error, update: err.ctx.update.update_id }, "unhandled bot error");
});

await bot.api.setMyCommands([
  { command: "start", description: "Welcome + how to use the bot" },
  { command: "register", description: "Create your agentic wallet (email OTP)" },
  { command: "wallet", description: "Show your wallet address" },
  { command: "balance", description: "Show USDC balances" },
  { command: "fund", description: "Get testnet USDC from the faucet" },
  { command: "scan", description: "Find tradeable Polymarket markets" },
  { command: "trade", description: "Join a market by id" },
  { command: "positions", description: "List markets you've joined" },
  { command: "help", description: "Show help" },
]);

await bot.start({
  onStart: (info) => logger.info({ username: info.username }, "PUA Telegram bot started"),
});
