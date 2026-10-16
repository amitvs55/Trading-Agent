"use client";
import useSWR from "swr";
import { API_URL } from "@/lib/utils";
import type { UsageReport } from "@/types/pipeline";

const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
});

export function useUsageReport() {
  const { data, error, isLoading, mutate } = useSWR<UsageReport>(`${API_URL}/api/usage`, fetcher, { refreshInterval: 30_000 });
  return { report: data ?? null, error, isLoading, refresh: mutate };
}
