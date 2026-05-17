import { sqliteTable, text, integer, real } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

// One row per Telegram user. `userId` is the Telegram user id as a string.
export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: text("user_id").notNull().unique(),
  email: text("email").notNull(),
  walletAddress: text("wallet_address"),
  sessionDir: text("session_dir").notNull(),
  sessionExpires: text("session_expires"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});

// One row per market the user joined via the bot.
export const trades = sqliteTable("trades", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: text("user_id").notNull(),
  marketId: text("market_id").notNull(),
  question: text("question").notNull(),
  direction: text("direction").notNull(),
  entryPrice: real("entry_price").notNull(),
  size: real("size").notNull(),
  notional: real("notional").notNull(),
  shares: real("shares").notNull(),
  expectedValue: real("expected_value").notNull(),
  status: text("status").notNull(),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
});
