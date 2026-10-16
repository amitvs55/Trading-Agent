"use client";
import { useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import type { Confidence } from "@/types/options";
import { cn } from "@/lib/utils";
import { fmtR } from "@/lib/optionsFormat";
import { STATUS_STYLE, StatusIcon } from "./StatusBits";

const LEVEL_TONE: Record<Confidence["level"], { text: string; bar: string }> = {
  "Very high": { text: "text-[#ff9933]", bar: "bg-[#ff9933]" },
  High:        { text: "text-[#ffb366]", bar: "bg-[#ffb366]" },
  Moderate:    { text: "text-[#93c5fd]", bar: "bg-[#3987e5]" },
  Low:         { text: "text-[#94a3b8]", bar: "bg-[#64748b]" },
};

/** Score out of 100 on a track marked at the grade lines (B from 60, A from 75). */
export function ConfidenceMeter({ c, className }: { c: Confidence; className?: string }) {
  const tone = LEVEL_TONE[c.level];
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <span className="text-[10px] tracking-widest text-[#64748b]">CONFIDENCE</span>
        <span className="text-[11px] text-[#94a3b8]">
          <span className={cn("font-mono text-sm font-bold", tone.text)}>{c.score.toFixed(0)}</span>
          <span className="text-[#475569]">/100</span> · <span className={tone.text}>{c.level}</span>
        </span>
      </div>
      <div className="relative h-1.5 rounded-full bg-[#0b0f1a]" role="meter" aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={c.score} aria-label={`Confidence ${c.score.toFixed(0)} of 100, ${c.level}`}>
        <div className={cn("absolute inset-y-0 left-0 rounded-full transition-[width] duration-700", tone.bar)}
             style={{ width: `${Math.min(100, c.score)}%` }} />
        {[60, 75].map(x => <div key={x} className="absolute -top-0.5 -bottom-0.5 w-px bg-[#334155]" style={{ left: `${x}%` }} />)}
      </div>
    </div>
  );
}

function BandNote({ c }: { c: Confidence }) {
  const b = c.band;
  if (!b.enough) {
    return (
      <p className="text-[11px] text-[#64748b] leading-snug">
        Track record for grade {c.grade}: <span className="text-[#94a3b8]">building history</span> ({b.trades} of {b.min_trades} completed
        trades). A win rate from fewer trades would mostly be luck, so it isn&apos;t shown yet.
      </p>
    );
  }
  return (
    <p className="text-[11px] text-[#94a3b8] leading-snug">
      Grade {c.grade} so far: <span className="font-mono text-[#e2e8f0]">{b.trades}</span> trades ·{" "}
      <span className="font-mono text-[#e2e8f0]">{((b.win_rate ?? 0) * 100).toFixed(0)}%</span> won · average{" "}
      <span className="font-mono text-[#e2e8f0]">{fmtR(b.avg_r)}</span> per trade.
    </p>
  );
}

/** Where every point came from: the ten weighted checks, what helped, what cost points. */
export function ConfidenceBreakdown({ c }: { c: Confidence }) {
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1.5">
        {c.parts.map(p => {
          const S = STATUS_STYLE[p.status];
          return (
            <li key={p.pillar} className="grid grid-cols-[16px_minmax(0,1fr)_64px_44px] items-center gap-2 text-[11px]">
              <StatusIcon status={p.status} size={12} />
              <span className="min-w-0">
                <span className="text-[#e2e8f0]">{p.label}</span>
                <span className="text-[#64748b] truncate block" title={p.detail}>{p.detail}</span>
              </span>
              <span className="h-1 rounded-full bg-[#0b0f1a] overflow-hidden" aria-hidden>
                <span className={cn("block h-full rounded-full", p.status === "pass" ? "bg-green" : p.status === "fail" ? "bg-red" : "bg-yellow")}
                      style={{ width: `${(p.points / p.weight) * 100}%` }} />
              </span>
              <span className={cn("font-mono text-right tabular-nums", S.text)}>{p.points % 1 ? p.points.toFixed(1) : p.points}/{p.weight}</span>
            </li>
          );
        })}
      </ul>
      <BandNote c={c} />
      <p className="flex items-start gap-1.5 text-[10px] text-[#475569] leading-snug">
        <Info size={11} className="mt-px flex-shrink-0" />
        Confidence counts how much of the analysis agrees with the trade: full points for a pass, half for a caution or
        missing data, none when a check is against it. It is not a promise of winning; the track record above is.
      </p>
    </div>
  );
}

/** Meter plus a "why" toggle, for the signal card. */
export function ConfidenceRow({ c }: { c: Confidence }) {
  const [open, setOpen] = useState(false);
  const weak = c.weaknesses.filter(w => w.lost > 0).slice(0, 2);
  return (
    <div className="px-4 pb-3">
      <ConfidenceMeter c={c} />
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open}
              className="mt-1.5 w-full flex items-center justify-between gap-2 text-left text-[11px] text-[#64748b] hover:text-[#94a3b8] transition-colors">
        <span className="min-w-0 truncate">
          {c.strengths.length ? <>Strong: <span className="text-[#94a3b8]">{c.strengths.join(", ")}</span></> : "No strong pillar"}
          {weak.length > 0 && <> · lost: <span className="text-[#94a3b8]">{weak.map(w => `${w.label} −${w.lost}`).join(", ")}</span></>}
        </span>
        <span className="flex items-center gap-0.5 flex-shrink-0 text-[#ff9933]">
          Why <ChevronDown size={12} className={cn("transition-transform duration-200", open && "rotate-180")} />
        </span>
      </button>
      <div className={cn("grid transition-[grid-template-rows] duration-300 ease-out", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="overflow-hidden">
          <div className="pt-3"><ConfidenceBreakdown c={c} /></div>
        </div>
      </div>
    </div>
  );
}
