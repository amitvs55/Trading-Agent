"use client";
import { cn } from "@/lib/utils";
import { fmtClock, fmtClockDay, fmtCountdown, useClockSync, useNow } from "@/lib/clock";
import { useOptionsApi } from "@/lib/optionsApi";
import type { OptionsStatus } from "@/types/options";

/** Navbar clock: IST time to the second, and how long until NSE opens or closes. */
export function LiveClock() {
  useClockSync();
  const now = useNow(1000);
  const { data } = useOptionsApi<OptionsStatus>("/api/options/status", 60_000);

  const opens = data ? new Date(data.market_opens_at).getTime() : null;
  const closes = data ? new Date(data.market_closes_at).getTime() : null;
  const open = !!(now && opens && closes && now >= opens && now < closes);
  const label = !now || !opens || !closes ? null
    : open ? `closes in ${fmtCountdown(closes - now)}`
    : now < opens ? `opens in ${fmtCountdown(opens - now)}` : null;

  return (
    <div className="flex items-center gap-2 h-[34px] text-xs px-2.5 sm:px-3 rounded-lg bg-card border border-[#1e2d45]"
         title={now ? `${fmtClockDay(now)} · India Standard Time` : "India Standard Time"}>
      <span className={cn("w-2 h-2 rounded-full flex-shrink-0 transition-colors", open ? "bg-green animate-pulse" : "bg-[#475569]")} />
      <span className="font-mono font-semibold text-[#e2e8f0] tabular-nums w-[64px]" suppressHydrationWarning>
        {now ? fmtClock(now) : "--:--:--"}
      </span>
      <span className="hidden sm:inline text-[#8391a7]">IST</span>
      {label && (
        <span className={cn("hidden md:inline tabular-nums whitespace-nowrap", open ? "text-green" : "text-[#94a3b8]")}>
          · NSE {label}
        </span>
      )}
    </div>
  );
}
