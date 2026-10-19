"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { fmtClock, fmtClockDay, useNow } from "@/lib/clock";
import { fmtNum } from "@/lib/optionsFormat";
import { freshness, useLiveIndices, type Freshness, type LiveLevel, type LiveState } from "@/lib/liveIndices";

const INDICES = [
  { symbol: "NIFTY 50", short: "NIFTY" },
  { symbol: "SENSEX", short: "SENSEX" },
] as const;

/** Flashes green or red on each new level: the animation name alternates so every change replays it. */
function useTickFlash(ltp: number | null | undefined): string {
  const [seen, setSeen] = useState<{ ltp: number | null | undefined; cls: string; n: number }>({ ltp, cls: "", n: 0 });
  if (ltp !== seen.ltp) {
    const dir = seen.ltp == null || ltp == null ? "" : ltp > seen.ltp ? "up" : ltp < seen.ltp ? "down" : "";
    setSeen({ ltp, cls: dir ? `tick-${dir}-${seen.n % 2}` : "", n: seen.n + 1 });
  }
  return seen.cls;
}

function Level({ meta, level, dim, variant }: {
  meta: (typeof INDICES)[number]; level: LiveLevel | undefined; dim: boolean; variant: "bar" | "strip";
}) {
  const ltp = level?.ltp ?? null;
  const prev = level?.prev_close ?? null;
  const chg = ltp != null && prev ? ltp - prev : null;
  const pct = chg != null && prev ? (chg / prev) * 100 : null;
  const up = (chg ?? 0) > 0, down = (chg ?? 0) < 0;
  const flash = useTickFlash(ltp);
  const tone = up ? "text-green" : down ? "text-red" : "text-[#94a3b8]";
  const arrow = up ? "▲" : down ? "▼" : "";
  const pctText = pct != null ? `${arrow}${fmtNum(Math.abs(pct), 2)}%` : "";
  const fullText = chg != null ? `${arrow} ${fmtNum(Math.abs(chg), 2)} (${fmtNum(Math.abs(pct ?? 0), 2)}%)` : "";
  const label = ltp == null ? `${meta.symbol}: no level yet`
    : `${meta.symbol} ${fmtNum(ltp, 2)}` + (chg != null ? `, ${up ? "up" : down ? "down" : "unchanged"} ${fmtNum(Math.abs(chg), 2)} points, ${fmtNum(Math.abs(pct ?? 0), 2)} percent` : "");
  const strip = variant === "strip";
  return (
    <div className={cn("min-w-0 flex", strip ? "flex-col sm:flex-row sm:items-baseline sm:gap-2" : "items-baseline gap-2")}
         aria-label={label} role="group" title={variant === "bar" && fullText ? `${meta.symbol} ${fullText}` : undefined}>
      <div className="flex items-baseline gap-1.5 leading-4">
        <span className="text-[10px] font-medium tracking-wider text-[#8391a7]">
          {strip ? <><span className="sm:hidden">{meta.short}</span><span className="hidden sm:inline">{meta.symbol}</span></> : meta.symbol}
        </span>
        {/* phones: the % sits on the label line, so the price gets the full width below */}
        {strip && <span className={cn("sm:hidden font-mono tabular-nums text-[10px]", tone)} aria-hidden>{pctText}</span>}
      </div>
      <span aria-hidden className={cn("font-mono tabular-nums font-semibold leading-5 rounded px-0.5 -mx-0.5 min-w-[9ch]",
                                      strip ? "text-[14px] sm:text-[13px]" : "text-[13px]",
                                      dim ? "text-[#94a3b8]" : "text-[#e2e8f0]", flash)}>
        {ltp != null ? fmtNum(ltp, 2) : "—"}
      </span>
      {/* fixed widths, so a longer change never pushes the next index along */}
      <span aria-hidden className={cn("font-mono tabular-nums text-[11px] min-w-[7ch]", tone, strip ? "hidden sm:inline md:hidden" : "inline")}>
        {pctText}
      </span>
      {strip && <span aria-hidden className={cn("hidden md:inline font-mono tabular-nums text-[11px] min-w-[18ch]", tone)}>{fullText}</span>}
    </div>
  );
}

const DOT: Record<Freshness, string> = {
  live: "bg-green", delayed: "bg-yellow", stale: "bg-red", waiting: "bg-[#64748b]", closed: "bg-[#64748b]", preopen: "bg-[#64748b]",
};

function statusText(f: Freshness, s: LiveState, ts: number | null | undefined, now: number): { short: string; long: string } {
  const m = s.market;
  if (f === "closed" && m) {
    const sameDay = fmtClockDay(m.last_close_ms) === fmtClockDay(now);
    const when = sameDay ? fmtClock(m.last_close_ms).slice(0, 5) : `${fmtClockDay(m.last_close_ms)} ${fmtClock(m.last_close_ms).slice(0, 5)}`;
    return { short: "Closed", long: `Closed · ${when}` };
  }
  if (f === "preopen" && m) return { short: "Pre-open", long: `Opens ${fmtClock(m.opens_ms).slice(0, 5)}` };
  if (s.link === "reconnecting" || s.link === "connecting") {
    if (f === "live") return { short: "Live", long: `Live · ${fmtClock(ts!)}` };
    return { short: "…", long: s.link === "connecting" ? "Connecting…" : "Reconnecting…" };
  }
  if (f === "waiting") return { short: "Waiting", long: "Waiting for ticks" };
  if (f === "live") return { short: "Live", long: `Live · ${fmtClock(ts!)}` };
  const age = Math.round((now - (ts ?? now)) / 1000);
  if (f === "delayed") return { short: `${age}s`, long: `Delayed ${age}s · ${fmtClock(ts!)}` };
  return { short: "Stale", long: `Stale · last ${fmtClock(ts!)}` };
}

/**
 * NIFTY 50 and SENSEX, pushed live. `bar` sits inside the wide navbar; `strip` is the slim row under
 * the navbar on phones, tablets and laptops. Both hold a fixed footprint (tabular digits, fixed
 * widths), so a new level never moves anything; "as of" is the exchange's time, and freshness is
 * judged against the server-synced clock.
 */
export function LiveTicker({ variant }: { variant: "bar" | "strip" }) {
  const s = useLiveIndices();
  const now = useNow(1000);
  const nifty = s.levels["NIFTY 50"];
  const f = freshness(nifty, s.market, now);
  const st = statusText(f, s, nifty?.ts, now);
  const dim = s.fromCache || f === "stale";
  const lag = s.lagMs != null && f === "live" ? ` · ${(s.lagMs / 1000).toFixed(1)} s behind the exchange` : "";
  const title = `${st.long}${lag}${s.link === "polling" ? " · live stream unavailable, refreshing every second" : ""}`;

  const status = (
    // Fixed width, text anchored left: "Live · 10:42:07" turning into "Delayed 6s · …" moves nothing
    <div className={cn("flex items-center gap-1.5 flex-shrink-0 text-[11px] text-[#94a3b8] whitespace-nowrap overflow-hidden",
                       variant === "bar" ? "w-[25ch]" : "w-[10ch] sm:w-[25ch]")} title={title}>
      <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", DOT[f], f === "live" && s.link === "live" && "live-pulse")} aria-hidden />
      <span className="font-mono tabular-nums">
        <span className="sm:hidden">{st.short}</span>
        <span className="hidden sm:inline">{st.long}</span>
      </span>
      <span className="sr-only">{title}</span>
    </div>
  );

  if (variant === "bar") {
    return (
      <div className="flex items-center gap-5" role="group" aria-label="Live index levels">
        {INDICES.map((meta, i) => (
          <div key={meta.symbol} className="flex items-center gap-5">
            {i > 0 && <div className="w-px h-3.5 bg-[#1e2d45]" />}
            <Level meta={meta} level={s.levels[meta.symbol]} dim={dim} variant="bar" />
          </div>
        ))}
        <div className="w-px h-3.5 bg-[#1e2d45]" />
        {status}
      </div>
    );
  }
  return (
    <div className="border-t border-[#1e2d45] bg-[#0b1220]">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-10 sm:h-8 flex items-center justify-between gap-3"
           role="group" aria-label="Live index levels">
        <div className="flex items-center gap-4 sm:gap-6 min-w-0">
          {INDICES.map(meta => <Level key={meta.symbol} meta={meta} level={s.levels[meta.symbol]} dim={dim} variant="strip" />)}
        </div>
        {status}
      </div>
    </div>
  );
}
