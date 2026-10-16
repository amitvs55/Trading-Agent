"use client";
import { useEffect, useState, type ReactNode } from "react";
import { SWRConfig, type SWRConfiguration } from "swr";
import { Loader2 } from "lucide-react";
import { AuthRequired, apiJson } from "@/lib/optionsApi";
import { reportFailure, reportSuccess, useFailingSince } from "@/lib/connection";

// One configuration for every read in the app. keepPreviousData: a refetch (or a changed key,
// like the next page of a table) keeps the current data on screen until the new data is in.
// SWR compares responses deeply, so a poll that returns the same data doesn't re-render anything.
const CONFIG: SWRConfiguration = {
  fetcher: (path: string) => apiJson(path),
  keepPreviousData: true,
  dedupingInterval: 2_000,
  focusThrottleInterval: 10_000,
  errorRetryInterval: 4_000,
  errorRetryCount: 6,
  shouldRetryOnError: (err: unknown) => !(err instanceof AuthRequired),
  onError: (err: unknown, key: string) => { if (!(err instanceof AuthRequired)) reportFailure(key); },
  onSuccess: (_data: unknown, key: string) => reportSuccess(key),
};

const SHOW_AFTER_MS = 4_000;           // a single slow or dropped poll isn't worth a notice

/** Floats over the page (never shifts it) while API reads keep failing. */
function ConnectionNotice() {
  const since = useFailingSince();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (since == null) { setVisible(false); return; }
    const wait = Math.max(0, since + SHOW_AFTER_MS - Date.now());
    const t = setTimeout(() => setVisible(true), wait);
    return () => clearTimeout(t);
  }, [since]);
  if (!visible) return null;
  return (
    <div role="status" aria-live="polite"
         className="fade-in fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-2 rounded-full border border-[#f59e0b44] bg-[#1a2233f2] px-4 py-2 text-xs text-yellow shadow-[0_12px_32px_rgba(0,0,0,.5)] backdrop-blur">
      <Loader2 size={13} className="animate-spin" />
      Reconnecting to the API… showing the last data received
    </div>
  );
}

export function DataProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={CONFIG}>
      {children}
      <ConnectionNotice />
    </SWRConfig>
  );
}
