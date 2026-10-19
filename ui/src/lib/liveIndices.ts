"use client";
import { useSyncExternalStore } from "react";
import { API_URL } from "@/lib/utils";
import { authHeaders } from "@/lib/optionsApi";
import { serverNow } from "@/lib/clock";

/**
 * Live NIFTY 50 / SENSEX for every component on the page, over ONE stream.
 *
 * The API pushes each new level (≤ 4 a second) as a server-sent event; this store folds them in
 * and repaints on the next animation frame, so the numbers move without jank. Levels carry the
 * exchange's own timestamp and a level never goes backwards. Freshness is judged by components
 * against the server-synced clock (useNow), never the device's clock.
 *
 * Resilience: a dropped stream reconnects in 0.5–5 s, and until a stream delivers again (also when
 * one connects but stays silent for 3 s, e.g. behind a buffering proxy) the store reads the latest
 * levels every second, so the numbers never freeze. A hidden tab closes the
 * stream (battery); coming back shows the current levels at once and reconnects. The last levels
 * are kept in localStorage so a reload paints numbers immediately (marked as not yet live).
 */

export interface LiveLevel {
  symbol: string;
  ltp: number | null;
  ts: number | null;              // exchange time of the level, epoch ms
  prev_close: number | null;
  prev_source?: string | null;
}

export interface MarketWindow {
  open: boolean;
  opens_ms: number;               // next (or today's) open
  closes_ms: number;              // next (or today's) close
  last_session: string;
  last_close_ms: number;
}

export type LinkState = "connecting" | "live" | "reconnecting" | "polling" | "paused";

export interface LiveState {
  levels: Record<string, LiveLevel>;
  market: MarketWindow | null;
  link: LinkState;
  lagMs: number | null;           // how far the newest level trailed the exchange when it arrived
  fromCache: boolean;             // painted from the last visit, not yet confirmed live
  unavailable: boolean;           // this API has no live feed (404): show nothing, check again each minute
}

interface Payload {
  items?: LiveLevel[];
  market?: MarketWindow;
  server_ms?: number;
}

const EMPTY: LiveState = { levels: {}, market: null, link: "connecting", lagMs: null, fromCache: false, unavailable: false };
const CACHE_KEY = "live.indices.v1";
const BACKOFF_MS = [500, 1000, 2000, 5000];
const POLL_MS = 1000;
const SILENCE_MS = 35_000;        // no data and no heartbeat for this long: the stream is dead
const PROVE_MS = 3000;            // a new stream must deliver its first event within this, or we poll meanwhile
const MIN_PAINT_GAP_MS = 100;
const LINGER_MS = 5000;           // keep the stream open briefly after the last component unmounts
const PROBE_MS = 60_000;          // with no live feed on the server, look again this often

let state: LiveState = EMPTY;
const listeners = new Set<() => void>();

// ── State updates, painted on animation frames ────────────────────────────────

let pending: LiveState | null = null;
let paintTimer: ReturnType<typeof setTimeout> | null = null;
let paintFrame = 0;
let lastPaint = 0;

function current(): LiveState { return pending ?? state; }

function commit(next: LiveState) {
  pending = next;
  if (paintTimer != null || paintFrame) return;
  const wait = Math.max(0, MIN_PAINT_GAP_MS - (performance.now() - lastPaint));
  paintTimer = setTimeout(() => {
    paintTimer = null;
    paintFrame = requestAnimationFrame(() => {
      paintFrame = 0;
      lastPaint = performance.now();
      if (pending) { state = pending; pending = null; listeners.forEach(l => l()); saveCache(); }
    });
  }, wait);
}

function setLink(link: LinkState) {
  const s = current();
  if (s.link !== link) commit({ ...s, link });
}

function merge(p: Payload, link: LinkState) {
  const s = current();
  const levels = { ...s.levels };
  let lagMs = s.lagMs;
  const arrived = serverNow();
  for (const it of p.items ?? []) {
    if (!it?.symbol) continue;
    const cur = levels[it.symbol];
    if (cur?.ts != null && it.ts != null && it.ts < cur.ts) continue;       // never backwards
    if (it.ltp == null && cur?.ltp != null) {                              // no level yet today: keep the last
      levels[it.symbol] = { ...cur, prev_close: it.prev_close ?? cur.prev_close };
      continue;
    }
    if (!cur || cur.ltp !== it.ltp || cur.ts !== it.ts || cur.prev_close !== it.prev_close) {
      levels[it.symbol] = it;
      if (it.ts != null && (!cur || cur.ts !== it.ts)) lagMs = Math.max(0, arrived - it.ts);
    }
  }
  if (s.unavailable || document.documentElement.classList.contains("live-off")) setOff(false);
  // A snapshot or poll that lands after the stream came up must not flip the state back
  commit({ levels, market: p.market ?? s.market, link: streamUp ? "live" : link, lagMs, fromCache: false, unavailable: false });
}

// ── Cache (per browser, best effort) ──────────────────────────────────────────

let lastSave = 0;
function saveCache() {
  const now = Date.now();
  if (now - lastSave < 5000) return;
  lastSave = now;
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ levels: state.levels, market: state.market })); } catch { /* private mode */ }
}

function loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return;
    const c = JSON.parse(raw) as Pick<LiveState, "levels" | "market">;
    if (c && typeof c.levels === "object") state = { ...EMPTY, levels: c.levels ?? {}, market: c.market ?? null, fromCache: true };
  } catch { /* corrupt or blocked: start empty */ }
}

// ── The stream ────────────────────────────────────────────────────────────────

let ctrl: AbortController | null = null;
let failures = 0;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let lingerTimer: ReturnType<typeof setTimeout> | null = null;
let running = false;
let signedOut = false;
let probeTimer: ReturnType<typeof setTimeout> | null = null;
let streamUp = false;
let rotating = false;               // the server ended the stream on purpose (every 10 min)
let generation = 0;                 // bumped by stop(): a stream from before it never acts afterwards

const OFF_KEY = "live.indices.off";   // read before first paint (app/layout.tsx), so a hidden strip never flashes

/** Remembers whether this server has a live feed, and applies it at once (html.live-off hides the strip). */
function setOff(off: boolean) {
  try { if (off) localStorage.setItem(OFF_KEY, "1"); else localStorage.removeItem(OFF_KEY); } catch { /* private mode */ }
  document.documentElement.classList.toggle("live-off", off);
}

/** The server has no live feed (an API from before it existed): hide the strip, look again each minute. */
function markUnavailable() {
  stop("paused");
  const s = current();
  if (!s.unavailable) commit({ ...s, unavailable: true });
  setOff(true);
  if (probeTimer == null) probeTimer = setTimeout(probe, PROBE_MS);
}

async function probe() {
  probeTimer = null;
  if (!listeners.size) return;
  try {
    const res = await fetch(`${API_URL}/api/options/live/indices`, { headers: authHeaders(), cache: "no-store" });
    if (res.ok) { merge(await res.json() as Payload, "connecting"); start(); return; }
  } catch { /* try again later */ }
  probeTimer = setTimeout(probe, PROBE_MS);
}

async function snapshot(link: LinkState) {
  try {
    const res = await fetch(`${API_URL}/api/options/live/indices`, { headers: authHeaders(), cache: "no-store" });
    if (res.status === 401) { signedOut = true; stop("paused"); return; }
    if (res.status === 404) { markUnavailable(); return; }
    if (res.ok) merge(await res.json() as Payload, link);
  } catch { /* the stream or the next poll will catch up */ }
}

function startPolling() {
  if (pollTimer != null) return;
  pollTimer = setInterval(() => { void snapshot("polling"); }, POLL_MS);
}

function stopPolling() {
  if (pollTimer != null) { clearInterval(pollTimer); pollTimer = null; }
}

function handleBlock(block: string) {
  let event = "message", data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  let p: Payload;
  try { p = JSON.parse(data) as Payload; } catch { return; }
  if (event === "levels") merge(p, "live");
  else if (event === "bye") rotating = true;
  else if (event === "ping") {
    const s = current();
    commit({ ...s, market: p.market ?? s.market, link: "live" });
  }
}

async function connect() {
  if (!running || ctrl) return;
  const mine = new AbortController();
  const gen = generation;
  ctrl = mine;
  let silence: ReturnType<typeof setTimeout> | null = null;
  const alive = () => { if (silence) clearTimeout(silence); silence = setTimeout(() => mine.abort(), SILENCE_MS); };
  const prove = setTimeout(() => { if (!streamUp && running && gen === generation) { startPolling(); setLink("polling"); } }, PROVE_MS);
  try {
    const res = await fetch(`${API_URL}/api/options/live/indices/stream`, {
      headers: authHeaders({ Accept: "text/event-stream" }), cache: "no-store", signal: mine.signal,
    });
    if (res.status === 401) { signedOut = true; stop("paused"); return; }
    if (res.status === 404) { markUnavailable(); return; }
    if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
    alive();
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      alive();
      if (!streamUp) { streamUp = true; failures = 0; clearTimeout(prove); stopPolling(); }   // it delivers
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let cut: number;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        handleBlock(buffer.slice(0, cut));
        buffer = buffer.slice(cut + 2);
      }
    }
  } catch { /* dropped, timed out, or aborted: decided below */ }
  finally {
    if (silence) clearTimeout(silence);
    clearTimeout(prove);
    if (ctrl === mine) { ctrl = null; streamUp = false; }
  }
  if (!running || gen !== generation) return;
  if (rotating) {                                // planned: straight back, nothing changes on screen
    rotating = false;
    void connect();
    return;
  }
  failures += 1;
  setLink(failures >= 3 ? "polling" : "reconnecting");
  startPolling();                                // keep the numbers moving while we reconnect
  retryTimer = setTimeout(() => { retryTimer = null; void connect(); }, BACKOFF_MS[Math.min(failures, BACKOFF_MS.length) - 1]);
}

function start() {
  if (running || signedOut || probeTimer != null || document.visibilityState === "hidden") return;
  running = true;
  if (current().link === "paused") setLink("connecting");
  void snapshot("connecting");                                        // current levels at once
  void connect();
}

function stop(link: LinkState) {
  running = false;
  generation += 1;
  streamUp = false;
  rotating = false;
  if (retryTimer != null) { clearTimeout(retryTimer); retryTimer = null; }
  stopPolling();
  ctrl?.abort();
  ctrl = null;
  setLink(link);
}

function onVisibility() {
  if (document.visibilityState === "hidden") stop("paused");
  else { failures = 0; start(); }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (lingerTimer != null) { clearTimeout(lingerTimer); lingerTimer = null; }
  if (listeners.size === 1) {
    if (state === EMPTY) loadCache();
    signedOut = false;
    document.addEventListener("visibilitychange", onVisibility);
    start();
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size) return;
    lingerTimer = setTimeout(() => {
      lingerTimer = null;
      if (listeners.size) return;
      document.removeEventListener("visibilitychange", onVisibility);
      if (probeTimer != null) { clearTimeout(probeTimer); probeTimer = null; }
      stop("paused");
    }, LINGER_MS);
  };
}

/** The live levels; components re-render only when a new level is painted. */
export function useLiveIndices(): LiveState {
  return useSyncExternalStore(subscribe, () => state, () => EMPTY);
}

export type Freshness = "live" | "delayed" | "stale" | "waiting" | "closed" | "preopen";

export const DELAYED_AFTER_MS = 5000;
export const STALE_AFTER_MS = 60_000;

/** Is the market open at `now` (server-synced ms)? Counted locally, so it flips at 09:15:00 / 15:30:00. */
export function marketOpenAt(m: MarketWindow | null, now: number): boolean {
  if (!m || !now) return false;
  return now >= m.opens_ms && now < m.closes_ms;
}

export function freshness(level: LiveLevel | undefined, m: MarketWindow | null, now: number): Freshness {
  if (!m || !now) return "waiting";
  if (!marketOpenAt(m, now)) {
    // Before 09:15 on a trading day the next open is under 9 h 15 m away (it's later after a close)
    return now < m.opens_ms && m.opens_ms - now <= 9.25 * 3600_000 ? "preopen" : "closed";
  }
  if (!level?.ts || level.ts < m.opens_ms) return "waiting";
  const age = now - level.ts;
  return age <= DELAYED_AFTER_MS ? "live" : age <= STALE_AFTER_MS ? "delayed" : "stale";
}
