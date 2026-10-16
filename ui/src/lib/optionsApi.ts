"use client";
import useSWR, { mutate as globalMutate } from "swr";
import { API_URL } from "@/lib/utils";

// The dashboard password (DASHBOARD_TOKEN on the API) lives in this browser only.
const TOKEN_KEY = "options.dashboardToken";

export class AuthRequired extends Error {
  constructor() { super("Dashboard login required"); }
}

export function getToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}

export function setToken(token: string) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* private mode: token lasts this tab only */ }
  globalMutate(() => true);                      // refetch everything with the new token
}

export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  globalMutate(() => true);
}

async function fetcher<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    cache: "no-store",
  });
  if (res.status === 401) throw new AuthRequired();
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<T>;
}

/** SWR hook for /api/options/* — keeps the last good data on screen while refetching. */
export function useOptionsApi<T>(path: string | null, refreshMs: number) {
  const { data, error, isLoading, mutate } = useSWR<T>(path, fetcher, {
    refreshInterval: refreshMs,
    keepPreviousData: true,
    shouldRetryOnError: (err: unknown) => !(err instanceof AuthRequired),
  });
  return { data, error: error as Error | undefined, isLoading, refresh: mutate, needsLogin: error instanceof AuthRequired };
}
