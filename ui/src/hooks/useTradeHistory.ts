"use client";
import useSWR from "swr";
import { API_URL } from "@/lib/utils";

const fetcher = (url: string) => fetch(url).then(r => r.json());

export function useTradeHistory(params?: { limit?: number; offset?: number; ticker?: string; status?: string }) {
  const q = new URLSearchParams();
  if (params?.limit)   q.set("limit",  String(params.limit));
  if (params?.offset)  q.set("offset", String(params.offset));
  if (params?.ticker)  q.set("ticker", params.ticker);
  if (params?.status)  q.set("status", params.status);

  const url = `${API_URL}/api/history?${q.toString()}`;
  const { data, error, isLoading, mutate } = useSWR(url, fetcher, { refreshInterval: 30_000 });

  return {
    records:    (data?.records ?? []) as Record<string, unknown>[],
    total:      (data?.total   ?? 0)  as number,
    isLoading,
    error,
    refresh:    mutate,
  };
}
