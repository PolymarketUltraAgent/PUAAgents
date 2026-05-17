import { execFile } from "child_process";
import { resolve } from "path";
import { env } from "../config/env.js";
import { logger } from "../utils/logger.js";

// Bridge to the Python PUA agent pipeline. Spawns app/pua_cli.py from the
// PUAAgents repo root and parses the JSON decision list it prints.

/** Mirrors trade_advisor.TradeDecision (snake_case, as emitted by pua_cli.py). */
export interface TradeDecision {
  market_id: string;
  question: string;
  direction: "YES" | "NO" | "PASS";
  entry_price: number;
  kelly_fraction: number;
  size: number;
  expected_value: number;
  rationale: string;
}

interface PuaResult {
  ok: boolean;
  decisions?: TradeDecision[];
  error?: string;
}

const repoRoot = resolve(process.cwd(), env.PUA_REPO_ROOT);
const cliPath = resolve(repoRoot, "app/pua_cli.py");

/** Extract the JSON payload from stdout, tolerating log lines printed before it. */
function parseResult(stdout: string): PuaResult {
  const lines = stdout.split("\n").map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      const parsed = JSON.parse(lines[i]) as PuaResult;
      if (typeof parsed.ok === "boolean") return parsed;
    } catch {
      /* not the JSON line — keep scanning upward */
    }
  }
  throw new Error("PUA agent produced no parseable JSON output");
}

/**
 * Run the PUA pipeline for the given tags. Resolves to ranked TradeDecisions
 * (including PASS entries). The pipeline hits Polymarket, Tavily, and an LLM,
 * so this can take a couple of minutes.
 */
export function scanMarkets(tags: string[], topN = 5): Promise<TradeDecision[]> {
  const args = [cliPath, "--tags", tags.join(","), "--top-n", String(topN)];

  return new Promise((resolvePromise, reject) => {
    logger.info({ tags, topN }, "running PUA pipeline");

    execFile(
      env.PYTHON_BIN,
      args,
      { cwd: repoRoot, timeout: 240000, maxBuffer: 4 * 1024 * 1024, env: process.env },
      (error, stdout, stderr) => {
        if (!stdout.trim()) {
          reject(
            new Error(
              `PUA agent failed to run (${env.PYTHON_BIN}): ${stderr.trim() || error?.message || "no output"}`
            )
          );
          return;
        }

        let result: PuaResult;
        try {
          result = parseResult(stdout);
        } catch (e) {
          reject(new Error(`${(e as Error).message}. stderr: ${stderr.trim()}`));
          return;
        }

        if (!result.ok) {
          reject(new Error(result.error || "PUA pipeline reported failure"));
          return;
        }

        resolvePromise(result.decisions ?? []);
      }
    );
  });
}
