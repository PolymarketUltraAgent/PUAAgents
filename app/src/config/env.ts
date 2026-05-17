import { z } from "zod";
import { config } from "dotenv";
import { resolve } from "path";

config({ path: resolve(process.cwd(), ".env") });

const envSchema = z.object({
  TELEGRAM_BOT_TOKEN: z.string().min(1, "TELEGRAM_BOT_TOKEN is required"),
  DATABASE_URL: z.string().default("./data/bot.sqlite"),
  SESSION_DIR: z.string().default("./data/sessions"),
  PUA_REPO_ROOT: z.string().default(resolve(process.cwd(), "..")),
  PYTHON_BIN: z.string().default("python3"),
  GATEWAY_API: z.string().default("https://gateway-api-testnet.circle.com"),
  TRADE_BANKROLL: z.coerce.number().positive().default(10),
  LOG_LEVEL: z.string().default("info"),
});

export const env = envSchema.parse(process.env);
