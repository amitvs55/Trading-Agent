"use client";
import { Loader2, RotateCcw, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

export interface WhatIfValues {
  amount: number;
  entry: number | null;
  horizon: "intraday" | "expiry";
  iv_shift: number;
  slippage_pct: number;
}

function Slider({ id, label, value, min, max, step, format, onChange }: {
  id: string; label: string; value: number; min: number; max: number; step: number;
  format: (v: number) => string; onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-[11px] text-[#94a3b8]">{label}</label>
        <span className="font-mono text-[12px] text-[#e2e8f0] tabular-nums">{format(value)}</span>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))}
             className="mt-1.5 w-full accent-[#ff9933]" />
    </div>
  );
}

/** Change an assumption and every number above updates (no new market data is needed). */
export function WhatIfPanel({ values, onChange, onReset, busy, defaultEntry, entryHint = "live ask" }: {
  values: WhatIfValues; onChange: (v: Partial<WhatIfValues>) => void; onReset: () => void; busy: boolean; defaultEntry: number | null;
  entryHint?: string;
}) {
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl p-5" aria-label="What if">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2">
          <SlidersHorizontal size={14} className="text-[#ff9933]" aria-hidden /> What if…
        </h3>
        <div className="flex items-center gap-2">
          <span className={cn("flex items-center gap-1 text-[11px] text-[#8391a7] transition-opacity", busy ? "opacity-100" : "opacity-0")} aria-hidden={!busy}>
            <Loader2 size={12} className="animate-spin" /> updating
          </span>
          <button type="button" onClick={onReset}
                  className="inline-flex items-center gap-1 h-7 px-2 rounded-md border border-[#1e2d45] text-[11px] text-[#94a3b8] hover:text-[#e2e8f0]">
            <RotateCcw size={12} aria-hidden /> Reset
          </button>
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4 mt-4">
        <div>
          <label htmlFor="wi-amount" className="text-[11px] text-[#94a3b8]">Amount</label>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="text-[#8391a7] text-sm">₹</span>
            <input id="wi-amount" type="number" inputMode="numeric" min={1000} step={1000} value={values.amount}
                   onChange={e => e.target.value && onChange({ amount: Math.max(1, Number(e.target.value)) })}
                   className="w-full bg-card border border-[#1e2d45] rounded-lg px-3 h-9 text-sm font-mono text-[#e2e8f0] focus:outline-none focus:border-[#ff9933]" />
          </div>
        </div>
        <div>
          <label htmlFor="wi-entry" className="text-[11px] text-[#94a3b8]">Your entry price (blank = {entryHint}{defaultEntry ? ` ₹${defaultEntry}` : ""})</label>
          <input id="wi-entry" type="number" inputMode="decimal" min={0.05} step={0.05} value={values.entry ?? ""}
                 placeholder={defaultEntry ? String(defaultEntry) : ""}
                 onChange={e => onChange({ entry: e.target.value ? Math.max(0.05, Number(e.target.value)) : null })}
                 className="mt-1.5 w-full bg-card border border-[#1e2d45] rounded-lg px-3 h-9 text-sm font-mono text-[#e2e8f0] focus:outline-none focus:border-[#ff9933]" />
        </div>
        <Slider id="wi-iv" label="Volatility change while you hold" value={values.iv_shift} min={-5} max={5} step={0.5}
                format={v => `${v > 0 ? "+" : ""}${v.toFixed(1)} pts`} onChange={v => onChange({ iv_shift: v })} />
        <Slider id="wi-slip" label="Extra slippage each way" value={values.slippage_pct} min={0} max={3} step={0.25}
                format={v => `${v.toFixed(2)}%`} onChange={v => onChange({ slippage_pct: v })} />
        <fieldset className="sm:col-span-2">
          <legend className="text-[11px] text-[#94a3b8]">Holding</legend>
          <div className="mt-1.5 inline-flex rounded-lg border border-[#1e2d45] p-0.5 bg-card">
            {(["intraday", "expiry"] as const).map(h => (
              <button key={h} type="button" aria-pressed={values.horizon === h} onClick={() => onChange({ horizon: h })}
                      className={cn("h-8 px-3 rounded-md text-[12px] font-medium transition-colors",
                                    values.horizon === h ? "bg-[#ff99331f] text-[#ff9933]" : "text-[#94a3b8] hover:text-[#e2e8f0]")}>
                {h === "intraday" ? "Intraday (out by 15:15)" : "Hold to expiry"}
              </button>
            ))}
          </div>
        </fieldset>
      </div>
    </section>
  );
}
