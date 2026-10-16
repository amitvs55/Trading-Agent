"use client";
import useSWR from "swr";
import { apiJson } from "@/lib/optionsApi";
import type { UsageReport } from "@/types/pipeline";

const fetcher = (path: string) => apiJson<UsageReport>(path);

export function useUsageReport() {
  const { data, error, isLoading, mutate } = useSWR<UsageReport>("/api/usage", fetcher, { refreshInterval: 30_000 });
  return { report: data ?? null, error, isLoading, refresh: mutate };
}
