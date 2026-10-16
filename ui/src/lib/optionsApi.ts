"use client";
import useSWR, { mutate as globalMutate } from "swr";
import { API_URL } from "@/lib/utils";

// The signed-in session token (from /api/auth/login or /api/auth/setup) lives in this browser only.
const TOKEN_KEY = "auth.session";
export const ME_KEY = "/api/auth/me";

export class AuthRequired extends Error {
  code: "login_required" | "setup_required";
  constructor(code: "login_required" | "setup_required" = "login_required", message = "Please log in.") {
    super(message);
    this.code = code;
  }
}

export class ApiError extends Error {
  status: number;
  code?: string;
  detail: Record<string, unknown>;
  constructor(status: number, message: string, code?: string, detail: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export function getToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; }
}

export function setToken(token: string) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* private mode: lasts until reload */ }
  globalMutate(() => true);                      // refetch everything with the new session
}

/** Drop the token without triggering refetches (used inside fetchers). */
export function forgetToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  globalMutate(() => true);
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function errorFrom(res: Response): Promise<ApiError | AuthRequired> {
  let detail: unknown = null;
  try { detail = (await res.json())?.detail; } catch { /* not JSON */ }
  const d = (detail && typeof detail === "object" ? detail : {}) as { code?: string; message?: string };
  const message = d.message ?? (typeof detail === "string" ? detail : `API error ${res.status}`);
  if (res.status === 401) {
    return new AuthRequired(d.code === "setup_required" ? "setup_required" : "login_required", message);
  }
  return new ApiError(res.status, message, d.code, d as Record<string, unknown>);
}

/** fetch() against the API with the session attached; a 401 sends the whole app back to the login screen. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: authHeaders((init.headers as Record<string, string>) ?? {}),
    cache: "no-store",
  });
  if (res.status === 401 && path !== ME_KEY) globalMutate(ME_KEY);
  return res;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<T>;
}

export function sendJson<T>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  return apiJson<T>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

const fetcher = <T,>(path: string) => apiJson<T>(path);

/** SWR hook for the API — keeps the last good data on screen while refetching. */
export function useOptionsApi<T>(path: string | null, refreshMs: number) {
  const { data, error, isLoading, mutate } = useSWR<T>(path, fetcher, {
    refreshInterval: refreshMs,
    keepPreviousData: true,
    shouldRetryOnError: (err: unknown) => !(err instanceof AuthRequired),
  });
  return { data, error: error as Error | undefined, isLoading, refresh: mutate, needsLogin: error instanceof AuthRequired };
}
