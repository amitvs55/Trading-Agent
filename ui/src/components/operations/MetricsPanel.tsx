"use client";
import { Gauge } from "lucide-react";
import type { MetricsResponse } from "@/types/auth";
import { cn } from "@/lib/utils";
import { Panel } from "@/components/connectors/SideCards";

function Stat({ label, value, sub, warn, wide }: { label: string; value: string; sub: string; warn?: boolean; wide?: boolean }) {
  return (
    <div className={cn("rounded-lg border border-[#1e2d45] bg-card px-3 py-2.5 min-w-0", wide && "col-span-2")}>
      <div className="text-[10px] tracking-widest text-[#8391a7]">{label}</div>
      <div className={cn("font-mono text-lg leading-7 truncate", warn ? "text-yellow" : "text-[#e2e8f0]")}>{value}</div>
      <div className="text-[11px] text-[#94a3b8] truncate">{sub}</div>
    </div>
  );
}

/** Is the recording machine keeping up? One row per minute of the session (last 8 hours). */
export function MetricsPanel({ data }: { data: MetricsResponse | undefined }) {
  const s = data?.summary;
  const evalP95 = s?.eval_ms?.p95;
  const delayP95 = s?.alert_delay_s?.p95;
  const liveP95 = s?.live_lag_ms?.p95;
  return (
    <Panel icon={<Gauge size={14} className="text-[#ff9933]" />} title="Session metrics (8 h)"
           subtitle="Recorded every minute while a session runs. Zero ticks means the feed stalled; slow checks mean the machine is overloaded.">
      {!data ? <div className="skeleton h-[226px] rounded-lg" /> : !s?.minutes ? (
        <p className="h-[226px] grid place-items-center text-[12px] text-[#94a3b8] text-center">No session in the last 8 hours. Metrics appear once recording starts.</p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Stat label="TICKS / MIN" value={String(s.ticks_per_min_last ?? 0)} sub={`last minute · ${s.minutes} minutes recorded`}
                warn={s.ticks_per_min_last === 0} />
          <Stat label="SIGNAL CHECK" value={evalP95 != null ? `${Math.round(evalP95)} ms` : "—"}
                sub={s.eval_ms ? `95% under this · slowest ${Math.round(s.eval_ms.max)} ms` : "no checks yet"} warn={(evalP95 ?? 0) > 2000} />
          <Stat label="ALERT DELAY" value={delayP95 != null ? `${delayP95.toFixed(1)} s` : "—"}
                sub={s.alert_delay_s ? `95% under this · slowest ${s.alert_delay_s.max.toFixed(1)} s` : "no alerts yet"} warn={(delayP95 ?? 0) > 30} />
          <Stat label="LIVE PRICE DELAY" value={liveP95 != null ? `${(liveP95 / 1000).toFixed(2)} s` : "—"}
                sub={s.live_lag_ms ? `exchange → dashboard, 95% under this` : "no live prices yet"} warn={(liveP95 ?? 0) > 1500} />
          <Stat label="BAD TICKS DROPPED" value={String(s.rejected_ticks)} sub="prices that jumped implausibly" warn={s.rejected_ticks > 0} wide />
        </div>
      )}
    </Panel>
  );
}
