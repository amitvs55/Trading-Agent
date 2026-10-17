"use client";
import { History } from "lucide-react";
import type { RecordStats, Stats } from "@/types/options";
import { useOptionsApi } from "@/lib/optionsApi";
import { useAuth } from "@/components/auth/AuthGate";
import { cn } from "@/lib/utils";
import { fmtDate, fmtPct, fmtR } from "@/lib/optionsFormat";

interface BacktestReport {
  kind: "proxy";
  generated_at: string;
  from: string;
  to: string;
  days: number;
  signals: number;
  overall: Stats;
  evidence: RecordStats;
  by_setup: Record<string, Stats>;
  evidence_by_setup: Record<string, RecordStats>;
  stability: { first_half: RecordStats; second_half: RecordStats };
  benchmark: { index: string; return_pct: number } | null;
  notes: string[];
}

function ci(s: RecordStats | undefined) {
  return s?.ci_r ? `${fmtR(s.ci_r[0])} to ${fmtR(s.ci_r[1])}` : "—";
}

/** The saved proxy backtest (options/backtest/proxy.py): years of real NIFTY paths through the live rules. */
export function BacktestPanel({ labels }: { labels: Record<string, string> }) {
  const { data } = useOptionsApi<{ report: BacktestReport | null }>("/api/options/backtest", 300_000);
  const admin = useAuth()?.user?.role === "admin";
  const r = data?.report;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e2d45] flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-[#e2e8f0] flex items-center gap-2"><History size={13} className="text-[#ff9933]" aria-hidden /> Historical backtest (proxy)</span>
        {r && <span className="text-[11px] text-[#94a3b8]">{fmtDate(r.from)} – {fmtDate(r.to)} · {r.days} days · run {fmtDate(r.generated_at)}</span>}
      </div>
      {!data ? <div className="p-4"><div className="skeleton h-24 rounded-lg" /></div> : !r ? (
        <div className="px-4 py-5 text-[12px] text-[#94a3b8] leading-relaxed">
          No backtest saved yet. It replays years of real NIFTY and India VIX minutes through the same rules the live engine uses.
          {admin && <> Run it from a terminal with DATABASE_URL pointing at this app&apos;s database:
          <pre className="mt-2 overflow-x-auto rounded-lg bg-card border border-[#1e2d45] p-3 text-[11px] text-[#cbd5e1]">{`python -m options.backtest.proxy fetch --from 2024-10-01 --to 2026-10-16 --history sqlite:///data/history.db
python -m options.backtest.proxy run --from 2024-11-01 --to 2026-10-16 --history sqlite:///data/history.db --out sqlite:///data/backtest.db --save`}</pre></>}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
                <th scope="col" className="px-4 py-2 font-medium">SETUP</th><th scope="col" className="px-2 py-2 font-medium text-right">TRADES</th>
                <th scope="col" className="px-2 py-2 font-medium text-right">WIN %</th><th scope="col" className="px-2 py-2 font-medium text-right">AVG R</th>
                <th scope="col" className="px-2 py-2 font-medium text-right">95% INTERVAL</th><th scope="col" className="px-4 py-2 font-medium text-right">VERDICT</th>
              </tr></thead>
              <tbody className="divide-y divide-[#1e2d45]">
                {[["All setups", r.overall, r.evidence] as const,
                  ...Object.entries(r.by_setup).map(([k, st]) => [labels[k] ?? k, st, r.evidence_by_setup[k]] as const)].map(([name, st, ev]) => (
                  <tr key={name}>
                    <td className="px-4 py-2 text-[#e2e8f0] whitespace-nowrap">{name}</td>
                    <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{st.trades}</td>
                    <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{fmtPct(st.win_rate)}</td>
                    <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{fmtR(st.avg_r)}</td>
                    <td className="px-2 py-2 text-right font-mono text-[#94a3b8] whitespace-nowrap">{ci(ev)}</td>
                    <td className={cn("px-4 py-2 text-right whitespace-nowrap", ev?.significant ? "text-green" : (ev?.mean_r ?? 0) <= 0 && ev?.enough ? "text-[#fca5a5]" : "text-yellow")}>
                      {!ev?.enough ? "too few trades" : ev.significant ? "edge (95%)" : (ev.mean_r ?? 0) <= 0 ? "no edge" : "not proven"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-3 border-t border-[#1e2d45] grid gap-3 grid-cols-1 sm:grid-cols-3 text-[12px]">
            <div><div className="text-[10px] tracking-widest text-[#8391a7]">FIRST HALF · AVG R</div><div className="font-mono text-[#e2e8f0] mt-0.5">{fmtR(r.stability.first_half.mean_r)} <span className="text-[#94a3b8]">({ci(r.stability.first_half)})</span></div></div>
            <div><div className="text-[10px] tracking-widest text-[#8391a7]">SECOND HALF · AVG R</div><div className="font-mono text-[#e2e8f0] mt-0.5">{fmtR(r.stability.second_half.mean_r)} <span className="text-[#94a3b8]">({ci(r.stability.second_half)})</span></div></div>
            <div><div className="text-[10px] tracking-widest text-[#8391a7]">NIFTY, SAME PERIOD</div><div className="font-mono text-[#e2e8f0] mt-0.5">{r.benchmark ? `${r.benchmark.return_pct >= 0 ? "+" : ""}${r.benchmark.return_pct.toFixed(1)}%` : "—"}</div></div>
          </div>
          <ul className="px-4 pb-3 text-[11px] text-[#94a3b8] leading-snug list-disc pl-8 space-y-0.5">
            {r.notes.map(n => <li key={n}>{n}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}
