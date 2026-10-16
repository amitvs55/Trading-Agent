"use client";
import useSWR from "swr";
import { apiJson } from "@/lib/optionsApi";

const fetcher = (path: string) => apiJson<{ records?: Record<string, unknown>[]; total?: number }>(path);

export function useTradeHistory(params?: { limit?: number; offset?: number; ticker?: string; status?: string }) {
  const q = new URLSearchParams();
  if (params?.limit)   q.set("limit",  String(params.limit));
  if (params?.offset)  q.set("offset", String(params.offset));
  if (params?.ticker)  q.set("ticker", params.ticker);
  if (params?.status)  q.set("status", params.status);

  const url = `/api/history?${q.toString()}`;
  const { data, error, isLoading, mutate } = useSWR(url, fetcher, { refreshInterval: 30_000 });

  return {
    records:    (data?.records ?? []) as Record<string, unknown>[],
    total:      (data?.total   ?? 0)  as number,
    isLoading,
    error,
    refresh:    mutate,
  };
}
