"use client";
import useSWR from "swr";
import { apiJson } from "@/lib/optionsApi";

/** One research run (GET /api/history, api/routes/history.py:record). */
export interface ResearchRecord {
  run_id: string;
  order_id: string | null;
  ticker: string;
  exchange: "NSE" | "BSE" | string;
  status: string;              // order status, or the run's status when it didn't finish
  run_status: string;
  action: string | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  size_pct: number | null;
  details: string | null;
  logged_at: string | null;
  started_at: string;
  requested_by: string | null;
  model: string | null;
  cost_usd: number | null;
  usage: { total_tokens?: number; cost_usd?: number } | null;
}

interface HistoryPage { records: ResearchRecord[]; total: number }

const fetcher = (path: string) => apiJson<HistoryPage>(path);

function url(params: { limit?: number; offset?: number; ticker?: string; status?: string }) {
  const q = new URLSearchParams();
  if (params.limit)  q.set("limit",  String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.ticker) q.set("ticker", params.ticker);
  if (params.status) q.set("status", params.status);
  return `/api/history?${q.toString()}`;
}

export function useTradeHistory(params: { limit: number; offset?: number; ticker?: string; status?: string }) {
  const { data, error, isLoading, mutate } = useSWR(url(params), fetcher, { refreshInterval: 30_000 });

  /** Every matching run (for the CSV export), fetched 500 at a time. */
  const fetchAll = async (): Promise<ResearchRecord[]> => {
    const out: ResearchRecord[] = [];
    for (let offset = 0; ; offset += 500) {
      const pageData = await fetcher(url({ ...params, limit: 500, offset }));
      out.push(...pageData.records);
      if (out.length >= pageData.total || pageData.records.length === 0) return out;
    }
  };

  return {
    records:   data?.records ?? [],
    total:     data?.total ?? 0,
    isLoading: isLoading && data === undefined,       // a page change keeps the old rows until the new ones arrive
    error,
    refresh:   mutate,
    fetchAll,
  };
}
