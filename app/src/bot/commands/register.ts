import type { Context } from "grammy";
import { CHAINS } from "../../config/constants.js";
import { logger } from "../../utils/logger.js";
import { createUser, updateWalletAddress, updateSessionExpiry } from "../../db/repositories/user-repo.js";
import {
  acceptTerms,
  getStatus,
  initLogin,
  completeLogin,
  listWallets,
  createWallet,
} from "../../wallet/wallet-service.js";
import { getState, setState, clearState } from "../session.js";
import { userIdOf, isValidEmail } from "../helpers.js";

/** /register <email> — accept terms, start email-OTP login, await the code. */
export async function handleRegister(ctx: Context): Promise<void> {
  const userId = userIdOf(ctx);
  const email = String(ctx.match ?? "").trim();

  if (!isValidEmail(email)) {
    await ctx.reply("Usage: /register <your-email>\nExample: /register alice@example.com");
    return;
  }

  await ctx.reply(`Setting up your agentic wallet for ${email}...`);

  try {
    const status = await getStatus(userId);
    if (status.needsTerms) {
      await acceptTerms(userId);
    }

    await createUser(userId, email);
    const { requestId } = await initLogin(userId, email);
    setState(userId, { kind: "awaiting_otp", email, requestId });

    await ctx.reply(
      `📧 An OTP code was sent to ${email}.\nReply with the code, or send /otp <code>.`
    );
  } catch (e) {
    logger.error({ err: e, userId }, "register failed");
    await ctx.reply(`❌ Registration failed: ${(e as Error).message}`);
  }
}

/** Verify the OTP, finish login, and provision the agentic wallet. */
export async function handleOtp(ctx: Context, codeArg?: string): Promise<void> {
  const userId = userIdOf(ctx);
  const state = getState(userId);

  if (state.kind !== "awaiting_otp") {
    await ctx.reply("Nothing to verify right now. Start with /register <your-email>.");
    return;
  }

  const code = String(codeArg ?? "").replace(/\D/g, "");
  if (code.length < 4) {
    await ctx.reply("Please send the numeric OTP code (or /otp <code>).");
    return;
  }

  await ctx.reply("Verifying code...");

  try {
    await completeLogin(userId, state.requestId, code);
    await updateSessionExpiry(userId);

    // Find the agentic wallet; provision one if the account has none yet.
    let wallets = await listWallets(userId, CHAINS.ARC_TESTNET);
    if (wallets.length === 0) {
      try {
        await createWallet(userId, CHAINS.ARC_TESTNET);
      } catch (e) {
        logger.warn({ err: e, userId }, "createWallet failed; relying on listWallets");
      }
      wallets = await listWallets(userId, CHAINS.ARC_TESTNET);
    }

    clearState(userId);

    const address = wallets[0]?.address;
    if (!address) {
      await ctx.reply("Logged in, but no agentic wallet could be found or created. Please try /register again.");
      return;
    }

    await updateWalletAddress(userId, address);
    await ctx.reply(
      `✅ Your agentic wallet is ready!\n\nAddress:\n${address}\n\n` +
        `Next: /fund to get testnet USDC, then /scan to find markets.`
    );
  } catch (e) {
    logger.error({ err: e, userId }, "otp verification failed");
    await ctx.reply(`❌ Verification failed: ${(e as Error).message}\nSend /register <your-email> to try again.`);
  }
}
