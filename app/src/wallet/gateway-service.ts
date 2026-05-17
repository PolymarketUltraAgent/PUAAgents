import { randomBytes } from "crypto";
import { exec, parseJSON, type StepEmitter } from "./cli.js";
import { CHAINS, GATEWAY, USDC_BY_DOMAIN } from "../config/constants.js";
import { env } from "../config/env.js";
import { getBalance } from "./wallet-service.js";

// Move USDC from Arc Testnet to Polygon Amoy. Ported from agentic-wallet-testing:
// tries Circle Gateway (deposit + burn intent + mint), falls back to a CCTP bridge.

interface GatewayBalanceData {
  data?: { balances?: Array<{ amount: string }>; balance?: string };
}

async function depositToGateway(
  userId: string,
  address: string,
  amount: string,
  emit?: StepEmitter
): Promise<void> {
  const balances = await getBalance(userId, address, CHAINS.ARC_TESTNET, emit);
  const usdcBal = balances.find((b) => b.symbol === "USDC");
  const available = parseFloat(usdcBal?.amount ?? "0");
  if (available < parseFloat(amount)) {
    const msg = `Insufficient balance on Arc Testnet: ${available} USDC available, ${amount} USDC needed. Fund your wallet first.`;
    emit?.({ step: "gateway_deposit", status: "error", error: msg });
    throw new Error(msg);
  }

  emit?.({
    step: "gateway_deposit",
    status: "running",
    command: `circle gateway deposit --amount ${amount} --address ${address}`,
  });

  const result = await exec(userId, [
    "gateway",
    "deposit",
    "--amount",
    amount,
    "--address",
    address,
    "--chain",
    CHAINS.ARC_TESTNET,
    "--method",
    "direct",
  ]);

  if (result.exitCode !== 0 && !result.stdout.toLowerCase().includes("deposit")) {
    const error = result.stderr || result.stdout;
    emit?.({ step: "gateway_deposit", status: "error", error });
    throw new Error(`Gateway deposit failed: ${error}`);
  }

  emit?.({ step: "gateway_deposit", status: "success", output: "Deposited to Gateway" });
}

async function getGatewayBalance(
  userId: string,
  address: string,
  emit?: StepEmitter
): Promise<string> {
  const result = await exec(userId, [
    "gateway",
    "balance",
    "--address",
    address,
    "--chain",
    CHAINS.ARC_TESTNET,
    "--output",
    "json",
  ]);

  const parsed = parseJSON<GatewayBalanceData>(result);
  const balance = parsed?.data?.balance ?? parsed?.data?.balances?.[0]?.amount ?? "0";
  emit?.({ step: "gateway_balance", status: "success", output: `${balance} USDC in Gateway` });
  return balance;
}

/** CCTP bridge fallback used when the Gateway path fails. */
async function bridgeToPolygon(
  userId: string,
  address: string,
  amount: string,
  emit?: StepEmitter
): Promise<void> {
  emit?.({
    step: "bridge_transfer",
    status: "running",
    command: `circle bridge transfer ${CHAINS.POLYGON_AMOY} --amount ${amount} --address ${address}`,
  });

  const result = await exec(userId, [
    "bridge",
    "transfer",
    CHAINS.POLYGON_AMOY,
    "--amount",
    amount,
    "--address",
    address,
    "--chain",
    CHAINS.ARC_TESTNET,
  ]);

  if (result.exitCode !== 0) {
    const error = result.stderr || result.stdout;
    emit?.({ step: "bridge_transfer", status: "error", error });
    throw new Error(`Bridge transfer failed: ${error}`);
  }

  emit?.({ step: "bridge_transfer", status: "success", output: "Bridged to Polygon Amoy" });
}

/**
 * Move `amount` USDC from the agentic wallet on Arc Testnet to Polygon Amoy.
 * Prefers Circle Gateway; transparently falls back to the CCTP bridge.
 */
export async function transferToPolygon(
  userId: string,
  address: string,
  amount: string,
  emit?: StepEmitter
): Promise<void> {
  await depositToGateway(userId, address, amount, emit);

  emit?.({ step: "gateway_confirm", status: "running", output: "Waiting for deposit confirmation..." });
  await new Promise((r) => setTimeout(r, 3000));

  const balance = await getGatewayBalance(userId, address, emit);
  if (parseFloat(balance) <= 0) {
    emit?.({ step: "gateway_confirm", status: "error", error: "Gateway deposit not yet confirmed" });
    throw new Error("Gateway deposit not confirmed after waiting");
  }
  emit?.({ step: "gateway_confirm", status: "success", output: `Gateway balance: ${balance} USDC` });

  // Build and sign an EIP-712 burn intent.
  const salt = "0x" + randomBytes(32).toString("hex");
  const burnIntent = {
    domain: {
      name: "GatewayWallet",
      version: "1",
      chainId: "421614",
      verifyingContract: GATEWAY.WALLET,
    },
    message: {
      maxBlockHeight:
        "115792089237316195423570985008687907853269984665640564039457584007913129639935",
      maxFee: "2010000",
      spec: {
        version: 1,
        sourceDomain: GATEWAY.DOMAINS.ARC_TESTNET,
        destinationDomain: GATEWAY.DOMAINS.POLYGON_AMOY,
        sourceContract: GATEWAY.WALLET,
        destinationContract: GATEWAY.MINTER,
        sourceToken: USDC_BY_DOMAIN[GATEWAY.DOMAINS.ARC_TESTNET],
        destinationToken: USDC_BY_DOMAIN[GATEWAY.DOMAINS.POLYGON_AMOY],
        sourceDepositor: address,
        destinationRecipient: address,
        value: BigInt(Math.round(parseFloat(amount) * 1e6)).toString(),
        salt,
        hookData: "0x",
      },
    },
  };

  emit?.({ step: "gateway_sign", status: "running", command: "circle wallet sign typed-data <burn-intent>" });
  const signResult = await exec(userId, [
    "wallet",
    "sign",
    "typed-data",
    JSON.stringify(burnIntent),
    "--address",
    address,
    "--chain",
    CHAINS.ARC_TESTNET,
  ]);

  if (signResult.exitCode !== 0) {
    emit?.({ step: "gateway_sign", status: "error", error: signResult.stderr || signResult.stdout });
    emit?.({ step: "gateway_fallback", status: "running", output: "Signing failed — using CCTP bridge..." });
    await bridgeToPolygon(userId, address, amount, emit);
    return;
  }

  const signature = signResult.stdout.trim();
  emit?.({ step: "gateway_sign", status: "success", output: "Burn intent signed" });

  // Request an attestation from the Gateway API, then mint on Polygon Amoy.
  emit?.({ step: "gateway_attest", status: "running", command: `POST ${env.GATEWAY_API}/v1/transfer` });
  try {
    const response = await fetch(`${env.GATEWAY_API}/v1/transfer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        burnIntents: [
          {
            permit2Signature: signature,
            burnIntent: burnIntent.message,
            chainId: burnIntent.domain.chainId,
          },
        ],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      emit?.({ step: "gateway_attest", status: "error", error: `Gateway API ${response.status}: ${errorText}` });
      emit?.({ step: "gateway_fallback", status: "running", output: "Attestation failed — using CCTP bridge..." });
      await bridgeToPolygon(userId, address, amount, emit);
      return;
    }

    const attestData = (await response.json()) as { attestation: string; operatorSignature: string };
    emit?.({ step: "gateway_attest", status: "success", output: "Attestation received" });

    emit?.({ step: "gateway_mint", status: "running", command: `circle wallet execute ${GATEWAY.MINTER}` });
    const mintResult = await exec(userId, [
      "wallet",
      "execute",
      GATEWAY.MINTER,
      "--abi",
      "gatewayMint(bytes,bytes)",
      "--args",
      `${attestData.attestation},${attestData.operatorSignature}`,
      "--chain",
      CHAINS.POLYGON_AMOY,
    ]);

    if (mintResult.exitCode !== 0) {
      const error = mintResult.stderr || mintResult.stdout;
      emit?.({ step: "gateway_mint", status: "error", error });
      throw new Error(`Mint failed: ${error}`);
    }

    emit?.({ step: "gateway_mint", status: "success", output: "Minted USDC on Polygon Amoy" });
  } catch (error) {
    if ((error as Error).message.includes("Mint failed")) throw error;
    emit?.({
      step: "gateway_fallback",
      status: "running",
      output: `Gateway error: ${(error as Error).message}. Using CCTP bridge...`,
    });
    await bridgeToPolygon(userId, address, amount, emit);
  }
}
