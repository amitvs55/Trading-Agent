"use client";
import { memo } from "react";
import { FlaskConical, Scale } from "lucide-react";
import type { Evidence, RecordStats } from "@/types/options";
import { cn } from "@/lib/utils";
import { PILLAR_LABELS, fmtPct, fmtR } from "@/lib/optionsFormat";

type Verdict = { label: string; tone: "good" | "warn" | "bad" | "muted"; note: string };

function verdict(s: RecordStats): Verdict {
  if (s.trades < 2) return { label: "No data yet", tone: "muted", note: "Results appear after the first completed trades." };
  if (!s.enough) return { label: `Too few trades (${s.trades} of ${s.min_trades})`, tone: "muted",
    note: `Fewer than ${s.min_trades} trades: the numbers are mostly noise, whatever they show.` };
  if (s.significant) return { label: "Edge proven (95%)", tone: "good", note: "Even the low end of the interval is above zero." };
  if (s.mean_r != null && s.mean_r <= 0) return { label: "No edge so far", tone: "bad", note: "Averaging a loss after costs over enough trades to matter." };
  if (s.trades_needed != null) return { label: `Not proven: ~${s.trades_needed} more trades`, tone: "warn",
    note: "Positive so far, but the interval still includes zero. At today's average and spread this many more trades would settle it." };
  return { label: "Not proven", tone: "warn", note: "The interval still includes zero." };
}

const TONE: Record<Verdict["tone"], string> = {
  good: "text-green border-[#22c55e44] bg-[#22c55e10]",
  warn: "text-yellow border-[#f59e0b44] bg-[#f59e0b10]",
  bad: "text-[#fca5a5] border-[#ef444444] bg-[#ef444410]",
  muted: "text-[#94a3b8] border-[#1e2d45] bg-card",
};

/** The 95% interval of the average R per trade, on a shared −2R…+2R scale with zero marked. */
function IntervalBar({ s, scale }: { s: RecordStats; scale: number }) {
  if (!s.ci_r || s.mean_r == null) return <div className="h-5" aria-hidden />;
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v + scale) / (2 * scale)) * 100))}%`;
  const [lo, hi] = s.ci_r;
  return (
    <div className="relative h-5" role="img"
         aria-label={`Average ${fmtR(s.mean_r)} per trade, 95% interval ${fmtR(lo)} to ${fmtR(hi)}`}>
      <div className="absolute inset-x-0 top-1/2 h-px bg-[#1e2d45]" />
      <div className="absolute top-0 bottom-0 w-px bg-[#8391a7]" style={{ left: pos(0) }} title="zero: no edge" />
      <div className={cn("absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full", s.significant ? "bg-green/70" : lo < 0 && hi > 0 ? "bg-yellow/70" : "bg-[#ef4444]/70")}
           style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />
      <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full bg-[#e2e8f0] ring-2 ring-[#111827]"
           style={{ left: pos(s.mean_r) }} />
    </div>
  );
}

const Row = memo(function Row({ name, s, scale }: { name: string; s: RecordStats; scale: number }) {
  const v = verdict(s);
  return (
    <li className="py-3 grid gap-x-4 gap-y-2 grid-cols-1 md:grid-cols-[minmax(0,180px)_minmax(0,1fr)_auto] md:items-center">
      <div className="min-w-0">
        <div className="text-[13px] text-[#e2e8f0] truncate">{name}</div>
        <div className="text-[11px] text-[#94a3b8] font-mono">{s.trades} trades · avg {fmtR(s.mean_r)}
          {s.ci_r && <> · 95% {fmtR(s.ci_r[0])} to {fmtR(s.ci_r[1])}</>}</div>
      </div>
      <IntervalBar s={s} scale={scale} />
      <div className="md:text-right">
        <span className={cn("inline-block text-[11px] font-semibold px-2 py-1 rounded-md border", TONE[v.tone])} title={v.note}>{v.label}</span>
        {s.dsr != null && s.trades >= s.min_trades && (
          <div className="text-[11px] text-[#94a3b8] mt-1">{fmtPct(s.dsr)} sure it isn&apos;t luck</div>
        )}
      </div>
    </li>
  );
});

export function EvidencePanel({ ev, labels }: { ev: Evidence | undefined; labels: Record<string, string> }) {
  if (!ev) return <div className="skeleton h-56 rounded-xl" />;
  const rows: [string, RecordStats][] = [["All setups", ev.overall], ...Object.entries(ev.by_setup).map(([k, s]) => [labels[k] ?? k, s] as [string, RecordStats])];
  const scale = Math.max(1, ...rows.flatMap(([, s]) => s.ci_r ? s.ci_r.map(Math.abs) : []).map(v => Math.min(3, Math.ceil(v))));
  const a = ev.account, b = ev.benchmark;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e2d45] flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-[#e2e8f0] flex items-center gap-2"><Scale size={13} className="text-[#ff9933]" aria-hidden /> Is the edge real?</span>
        <span className="text-[11px] text-[#94a3b8]">average result per trade with its 95% interval · bar crosses the line = not proven</span>
      </div>
      <ul className="px-4 divide-y divide-[#1e2d45]">
        {rows.map(([name, s]) => <Row key={name} name={name} s={s} scale={scale} />)}
      </ul>
      <div className="px-4 py-3 border-t border-[#1e2d45] grid grid-cols-2 md:grid-cols-4 gap-3 text-[12px]">
        <div><div className="text-[10px] tracking-widest text-[#8391a7]">SHARPE (ANNUAL)</div><div className="font-mono text-[#e2e8f0] mt-0.5">{a.sharpe != null ? a.sharpe.toFixed(2) : "—"}</div></div>
        <div><div className="text-[10px] tracking-widest text-[#8391a7]">SORTINO (ANNUAL)</div><div className="font-mono text-[#e2e8f0] mt-0.5">{a.sortino != null ? a.sortino.toFixed(2) : "—"}</div></div>
        <div><div className="text-[10px] tracking-widest text-[#8391a7]">RETURN ON CAPITAL</div>
          <div className="font-mono text-[#e2e8f0] mt-0.5">{a.return_pct.toFixed(1)}%{a.annualised_pct != null && <span className="text-[#94a3b8]"> · {a.annualised_pct.toFixed(0)}%/yr</span>}</div></div>
        <div><div className="text-[10px] tracking-widest text-[#8391a7]">NIFTY, SAME PERIOD</div>
          <div className="font-mono text-[#e2e8f0] mt-0.5">{b ? `${b.return_pct >= 0 ? "+" : ""}${b.return_pct.toFixed(1)}%` : "—"}</div></div>
      </div>
      <p className="px-4 pb-3 text-[11px] text-[#94a3b8] leading-snug">
        Sharpe and Sortino use daily P&amp;L over {a.days} trading day{a.days === 1 ? "" : "s"} (days without a trade count as zero).
        &ldquo;Sure it isn&apos;t luck&rdquo; is the Deflated Sharpe Ratio: it discounts the best setup for the number of setups tried.
      </p>
    </section>
  );
}

export function CalibrationPanel({ ev }: { ev: Evidence | undefined }) {
  if (!ev) return null;
  const c = ev.calibration;
  const pillars = Object.entries(c.by_pillar).filter(([, v]) => v.lift_r != null).sort((x, y) => (y[1].lift_r ?? 0) - (x[1].lift_r ?? 0));
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e2d45] flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-[#e2e8f0] flex items-center gap-2"><FlaskConical size={13} className="text-[#ff9933]" aria-hidden /> Is the confidence score honest?</span>
        <span className="text-[11px] text-[#94a3b8]">{c.enough ? "results by score band and by pillar" : `meaningful from ${20} trades (${c.trades} so far)`}</span>
      </div>
      <div className="grid gap-5 md:grid-cols-2 p-4">
        <div>
          <table className="w-full text-[12px] tabular-nums">
            <caption className="text-left text-[11px] text-[#94a3b8] pb-2">By confidence score{c.enough && c.score_monotonic != null &&
              <span className={c.score_monotonic ? "text-green" : "text-yellow"}> · {c.score_monotonic ? "higher scores did better" : "higher scores did NOT do better"}</span>}</caption>
            <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
              <th scope="col" className="py-1 font-medium">SCORE</th><th scope="col" className="py-1 font-medium text-right">TRADES</th>
              <th scope="col" className="py-1 font-medium text-right">WIN %</th><th scope="col" className="py-1 font-medium text-right">AVG R</th></tr></thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {c.by_score.map(b => (
                <tr key={b.band}><td className="py-1.5 text-[#e2e8f0]">{b.band}</td>
                  <td className="py-1.5 text-right font-mono text-[#94a3b8]">{b.trades}</td>
                  <td className="py-1.5 text-right font-mono text-[#94a3b8]">{fmtPct(b.win_rate)}</td>
                  <td className="py-1.5 text-right font-mono text-[#94a3b8]">{fmtR(b.avg_r)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <table className="w-full text-[12px] tabular-nums">
            <caption className="text-left text-[11px] text-[#94a3b8] pb-2">What a passed pillar added (avg R when it passed minus when it didn&apos;t)</caption>
            <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
              <th scope="col" className="py-1 font-medium">PILLAR</th><th scope="col" className="py-1 font-medium text-right">PASSED</th>
              <th scope="col" className="py-1 font-medium text-right">LIFT</th></tr></thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {pillars.length === 0 ? <tr><td colSpan={3} className="py-4 text-center text-[#94a3b8]">Not enough completed trades yet.</td></tr> :
                pillars.map(([k, v]) => (
                  <tr key={k}><td className="py-1.5 text-[#e2e8f0]">{PILLAR_LABELS[k] ?? k}</td>
                    <td className="py-1.5 text-right font-mono text-[#94a3b8]">{v.by_status.pass?.trades ?? 0}</td>
                    <td className={cn("py-1.5 text-right font-mono", (v.lift_r ?? 0) > 0 ? "text-[#93c5fd]" : "text-[#fca5a5]")}>{fmtR(v.lift_r)}</td></tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
