import type { TradeDecision } from "../pua/pua-agent.js";

// In-memory per-user bot state. Lost on restart by design: OTP requests are
// short-lived and scan results are cheap to regenerate.

export type ChatState =
  | { kind: "idle" }
  | { kind: "awaiting_otp"; email: string; requestId: string };

const states = new Map<string, ChatState>();
const decisionCache = new Map<string, TradeDecision[]>();

export function getState(userId: string): ChatState {
  return states.get(userId) ?? { kind: "idle" };
}

export function setState(userId: string, state: ChatState): void {
  states.set(userId, state);
}

export function clearState(userId: string): void {
  states.delete(userId);
}

/** Store the most recent /scan results so /trade and Join buttons can resolve them. */
export function cacheDecisions(userId: string, decisions: TradeDecision[]): void {
  decisionCache.set(userId, decisions);
}

export function getCachedDecisions(userId: string): TradeDecision[] {
  return decisionCache.get(userId) ?? [];
}

export function getCachedDecision(userId: string, marketId: string): TradeDecision | undefined {
  return getCachedDecisions(userId).find((d) => d.market_id === marketId);
}
