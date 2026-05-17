import { CHAINS } from "../config/constants.js";
import { env } from "../config/env.js";
import { getBalance } from "../wallet/wallet-service.js";
import { transferToPolygon } from "../wallet/gateway-service.js";
import type { StepEmitter } from "../wallet/cli.js";
import type { TradeDecision } from "../pua/pua-agent.js";
import { recordTrade, type Trade } from "../db/repositories/trade-repo.js";

// Joins a Polymarket market with the agentic wallet.
//
// Polymarket settles on Polygon mainnet while the Circle agentic wallet is
// testnet-only, so the on-chain leg (bridge USDC to Polygon Amoy) is real but
// the market fill is simulated: we record the decision and a mock fill.

export interface JoinResult {
  trade: Trade;
  bridged: boolean;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * Execute a TradeDecision for a user's wallet.
 *
 * 1. Size the position: notional = decision.size * TRADE_BANKROLL.
 * 2. Bridge that USDC from Arc Testnet to Polygon Amoy (real testnet tx).
 * 3. Simulate the Polymarket fill at the decision's entry price.
 * 4. Persist the trade.
 */
export async function joinMarket(
  userId: string,
  walletAddress: string,
  decision: TradeDecision,
  emit?: StepEmitter
): Promise<JoinResult> {
  if (decision.direction === "PASS" || decision.size <= 0) {
    throw new Error("This market is a PASS — no edge to trade.");
  }

  const notional = round2(decision.size * env.TRADE_BANKROLL);
  if (notional <= 0) {
    throw new Error("Computed position size is below the minimum notional.");
  }

  // Check the wallet can cover the notional on Arc Testnet before bridging.
  emit?.({ step: "check_balance", status: "running", output: "Checking wallet balance..." });
  const balances = await getBalance(userId, walletAddress, CHAINS.ARC_TESTNET);
  const usdc = parseFloat(balances.find((b) => b.symbol === "USDC")?.amount ?? "0");
  if (usdc < notional) {
    emit?.({
      step: "check_balance",
      status: "error",
      error: `Need ${notional} USDC, wallet has ${usdc}.`,
    });
    throw new Error(
      `Insufficient USDC: need ${notional}, have ${usdc}. Run /fund to get testnet USDC first.`
    );
  }
  emit?.({ step: "check_balance", status: "success", output: `${usdc} USDC available` });

  // Real testnet leg: move the notional to Polygon Amoy.
  let bridged = false;
  try {
    await transferToPolygon(userId, walletAddress, String(notional), emit);
    bridged = true;
  } catch (e) {
    // Keep the simulated fill meaningful even if the bridge fails on testnet.
    emit?.({
      step: "bridge_skipped",
      status: "error",
      error: `Bridge failed (${(e as Error).message}); recording a simulated-only fill.`,
    });
  }

  // Simulated Polymarket fill.
  const shares = round2(notional / decision.entry_price);
  emit?.({
    step: "simulate_fill",
    status: "running",
    output: `Simulating ${decision.direction} fill at ${decision.entry_price}...`,
  });

  const trade = await recordTrade({
    userId,
    marketId: decision.market_id,
    question: decision.question,
    direction: decision.direction,
    entryPrice: decision.entry_price,
    size: decision.size,
    notional,
    shares,
    expectedValue: decision.expected_value,
    status: bridged ? "simulated_filled" : "simulated_no_bridge",
  });

  emit?.({
    step: "simulate_fill",
    status: "success",
    output: `Filled ${shares} ${decision.direction} shares (simulated)`,
  });

  return { trade, bridged };
}
