import { desc, eq } from "drizzle-orm";
import { db } from "../index.js";
import { trades } from "../schema.js";

export interface Trade {
  id: number;
  userId: string;
  marketId: string;
  question: string;
  direction: string;
  entryPrice: number;
  size: number;
  notional: number;
  shares: number;
  expectedValue: number;
  status: string;
  createdAt: string | null;
}

export type NewTrade = Omit<Trade, "id" | "createdAt">;

export async function recordTrade(trade: NewTrade): Promise<Trade> {
  const inserted = await db.insert(trades).values(trade).returning().get();
  return inserted as Trade;
}

export async function getTradesForUser(userId: string): Promise<Trade[]> {
  const rows = await db
    .select()
    .from(trades)
    .where(eq(trades.userId, userId))
    .orderBy(desc(trades.createdAt))
    .all();
  return rows as Trade[];
}
