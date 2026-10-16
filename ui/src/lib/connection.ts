"use client";
import { useSyncExternalStore } from "react";

/**
 * Which API reads are currently failing, fed by SWR's onError/onSuccess for every request.
 * One small floating notice reads it, so pages never push their content around with
 * inline "couldn't reach the API" banners that come and go with each poll.
 */
const failing = new Map<string, number>();     // SWR key → when it first failed
const listeners = new Set<() => void>();
let since: number | null = null;

function emit() {
  const first = failing.size ? Math.min(...Array.from(failing.values())) : null;
  if (first === since) return;
  since = first;
  listeners.forEach(l => l());
}

export function reportFailure(key: string) {
  if (!failing.has(key)) failing.set(key, Date.now());
  emit();
}

export function reportSuccess(key: string) {
  if (failing.delete(key)) emit();
}

export function clearFailures() {
  failing.clear();
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

/** Timestamp of the oldest still-failing read, or null when everything is answering. */
export function useFailingSince(): number | null {
  return useSyncExternalStore(subscribe, () => since, () => null);
}
