import type { Context } from "grammy";
import { getUser, isSessionValid, type User } from "../db/repositories/user-repo.js";
import type { StepEmitter } from "../wallet/cli.js";

export function userIdOf(ctx: Context): string {
  return String(ctx.from?.id ?? "");
}

/**
 * Resolve the calling user, or reply with the appropriate next step and
 * return null. Guarantees a non-null `walletAddress` and a live session.
 */
export async function requireUser(ctx: Context): Promise<(User & { walletAddress: string }) | null> {
  const id = userIdOf(ctx);
  const user = await getUser(id);

  if (!user) {
    await ctx.reply("You're not registered yet. Send /register <your-email> to create your agentic wallet.");
    return null;
  }
  if (!user.walletAddress) {
    await ctx.reply("Your wallet isn't set up yet. Send /register <your-email> to finish setup.");
    return null;
  }
  if (!(await isSessionValid(id))) {
    await ctx.reply("Your wallet session expired. Send /register <your-email> to log in again.");
    return null;
  }

  return user as User & { walletAddress: string };
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email);
}

/**
 * Build a StepEmitter that live-edits a Telegram message into a progress
 * checklist. Edits are best-effort: rate-limit / "not modified" errors are ignored.
 */
export function makeStepEmitter(ctx: Context, messageId: number): StepEmitter {
  const lines: string[] = [];
  let lastText = "";

  return (event) => {
    const icon = event.status === "success" ? "✅" : event.status === "error" ? "❌" : "⏳";
    const detail = event.error ?? event.output ?? event.command ?? "";
    lines.push(`${icon} ${event.step}${detail ? ` — ${detail}` : ""}`);

    const text = lines.slice(-12).join("\n");
    if (text === lastText || !ctx.chat) return;
    lastText = text;
    void ctx.api.editMessageText(ctx.chat.id, messageId, text).catch(() => {});
  };
}
