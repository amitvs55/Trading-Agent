"use client";
import { useEffect, useSyncExternalStore } from "react";
import { API_URL } from "@/lib/utils";

/**
 * One clock for the whole app: a single timer aligned to the second, corrected to the server's
 * time (/api/time), so a phone whose clock drifts still shows exchange time. Components read it
 * with useNow(step): they re-render only when their step rolls over (1 s for the navbar clock,
 * 10 s for "updated 3m ago" labels), never because of each other.
 */
let offsetMs = 0;
let now = Date.now();
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function schedule() {
  now = Date.now() + offsetMs;
  listeners.forEach(l => l());
  timer = setTimeout(schedule, 1000 - (now % 1000) + 8);    // land just after each whole second
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (timer == null) schedule();
  return () => {
    listeners.delete(listener);
    if (!listeners.size && timer != null) { clearTimeout(timer); timer = null; }
  };
}

/** Server-corrected epoch ms right now (outside React, e.g. to time a message's arrival). */
export function serverNow(): number {
  return Date.now() + offsetMs;
}

/** Server-corrected epoch ms, rounded down to `stepMs`. 0 during server rendering. */
export function useNow(stepMs = 1000): number {
  return useSyncExternalStore(subscribe, () => Math.floor(now / stepMs) * stepMs, () => 0);
}

let lastSync = 0;

async function syncOnce() {
  try {
    const t0 = Date.now();
    const res = await fetch(`${API_URL}/api/time`, { cache: "no-store" });
    const t1 = Date.now();
    if (!res.ok || t1 - t0 > 3000) return;                 // a slow answer would make the offset wrong
    const { epoch_ms } = (await res.json()) as { epoch_ms: number };
    offsetMs = epoch_ms + (t1 - t0) / 2 - t1;
    lastSync = t1;
  } catch { /* keep the device clock */ }
}

/** Mounted once (navbar): sync now, every 10 minutes, and when the tab comes back. */
export function useClockSync() {
  useEffect(() => {
    syncOnce();
    const id = setInterval(syncOnce, 10 * 60_000);
    const onVisible = () => { if (document.visibilityState === "visible" && Date.now() - lastSync > 60_000) syncOnce(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVisible); };
  }, []);
}

const IST_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});
const IST_DAY = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short" });

export function fmtClock(ms: number): string {
  return IST_PARTS.format(ms);
}

export function fmtClockDay(ms: number): string {
  return IST_DAY.format(ms);
}

/** "2d 4h", "1h 12m", "12m 05s", "45s" */
export function fmtCountdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
}
