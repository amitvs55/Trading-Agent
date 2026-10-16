"use client";
import Link from "next/link";
import { BarChart3, Info } from "lucide-react";
import type { Performance, SignalsResponse, Stats } from "@/types/options";
import { useOptionsApi } from "@/lib/optionsApi";
import { cn } from "@/lib/utils";
import { EXIT_LABELS, fmtDateTime, fmtPct, fmtR, fmtRupees } from "@/lib/optionsFormat";
import { EquityChart, RDistribution } from "@/components/options/PerformanceCharts";
import { GradeBadge, ModeTag } from "@/components/options/StatusBits";

function Tile({ label, value, sub, loading }: { label: string; value: string; sub?: string; loading?: boolean }) {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl p-4">
      <div className="text-[10px] text-[#64748b] tracking-widest mb-2">{label}</div>
      {loading ? <div className="skeleton h-7 rounded w-20" /> : <div className="font-bold text-2xl text-[#e2e8f0]">{value}</div>}
      {sub && <div className="text-[11px] text-[#64748b] mt-1">{sub}</div>}
    </div>
  );
}

function StatsTable({ title, rows, labels }: { title: string; rows: Record<string, Stats>; labels?: Record<string, string> }) {
  const entries = Object.entries(rows);
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e2d45] text-xs font-semibold text-[#e2e8f0]">{title}</div>
      {entries.length === 0 ? <div className="px-4 py-6 text-xs text-[#475569] text-center">No signals yet</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] tabular-nums">
            <thead><tr className="text-[10px] tracking-widest text-[#64748b] text-left">
              <th className="px-4 py-2 font-medium"> </th><th className="px-2 py-2 font-medium text-right">TRADES</th>
              <th className="px-2 py-2 font-medium text-right">WIN %</th><th className="px-2 py-2 font-medium text-right">AVG R</th>
              <th className="px-4 py-2 font-medium text-right">NET</th>
            </tr></thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {entries.map(([k, st]) => (
                <tr key={k}>
                  <td className="px-4 py-2 text-[#e2e8f0] whitespace-nowrap">{labels?.[k] ?? k}</td>
                  <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{st.trades}</td>
                  <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{fmtPct(st.win_rate)}</td>
                  <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{fmtR(st.avg_r)}</td>
                  <td className={cn("px-4 py-2 text-right font-mono font-semibold", st.total_rupees > 0 ? "text-[#93c5fd]" : st.total_rupees < 0 ? "text-[#fca5a5]" : "text-[#94a3b8]")}>{fmtRupees(st.total_rupees, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function PerformancePage() {
  const perf = useOptionsApi<Performance>("/api/options/performance", 60_000);
  const log = useOptionsApi<SignalsResponse>("/api/options/signals?days=3650", 60_000);
  const p = perf.data;
  const o = p?.overall;
  const loading = perf.isLoading && !p;
  const labels = p?.setup_labels ?? {};

  return (
    <>
      <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
        <div className="mb-5">
          <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><BarChart3 size={20} className="text-[#ff9933]" /> Track record</h1>
          <p className="text-sm text-[#64748b] mt-1">Every signal ever sent, measured on live bid/ask after all charges. Losses count exactly like wins.</p>
        </div>

        <div className="mb-5 flex items-start gap-2.5 bg-[#3987e50d] border border-[#3987e533] rounded-xl px-4 py-3 text-[12px] text-[#94a3b8] leading-relaxed">
          <Info size={14} className="text-[#60a5fa] mt-0.5 flex-shrink-0" />
          <span>
            Signals are stored before their outcome is known and can't be edited. Signals that never filled (entry not reached,
            cancelled) are listed below but excluded from P&amp;L. SHADOW signals are what the system would have done: they
            prove a setup before it goes LIVE. Past results don&apos;t guarantee future ones.
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 mb-5">
          <Tile loading={loading} label="TRADES" value={String(o?.trades ?? 0)} sub={`${p?.counts.signals ?? 0} signals · ${p?.counts.expired ?? 0} unfilled`} />
          <Tile loading={loading} label="WIN RATE" value={fmtPct(o?.win_rate)} sub={`${o?.wins ?? 0} wins`} />
          <Tile loading={loading} label="AVG RESULT" value={fmtR(o?.avg_r)} sub="per trade, in risk units" />
          <Tile loading={loading} label="EXPECTANCY" value={fmtRupees(o?.expectancy_rupees, true)} sub="net ₹ per trade" />
          <Tile loading={loading} label="NET P&L" value={fmtRupees(o?.total_rupees, true)}
                sub={p && o ? `${((o.total_rupees / p.capital) * 100).toFixed(1)}% of capital` : undefined} />
          <Tile loading={loading} label="MAX DRAWDOWN" value={fmtRupees(o?.max_drawdown_rupees)} sub="peak to trough" />
          <Tile loading={loading} label="PROFIT FACTOR" value={o?.profit_factor != null ? o.profit_factor.toFixed(2) : "—"} sub="gross win ÷ gross loss" />
        </div>

        <div className="grid gap-5 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] mb-5">
          <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden min-w-0">
            <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
              <span className="text-xs font-semibold text-[#e2e8f0]">Cumulative net P&amp;L</span>
              <span className="text-[10px] text-[#64748b]">₹ after charges · 1 lot per signal</span>
            </div>
            <div className="p-3">{p && p.equity.length ? <EquityChart data={p.equity} /> :
              <div className="h-72 grid place-items-center text-xs text-[#475569]">The curve starts with the first completed trade.</div>}</div>
          </section>
          <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden min-w-0">
            <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
              <span className="text-xs font-semibold text-[#e2e8f0]">Result distribution</span>
              <span className="text-[10px] text-[#64748b]"><span className="text-[#93c5fd]">■</span> gain <span className="text-[#fca5a5] ml-1.5">■</span> loss · in R</span>
            </div>
            <div className="p-3">{p && p.r_values.length ? <RDistribution values={p.r_values} /> :
              <div className="h-60 grid place-items-center text-xs text-[#475569]">No completed trades yet.</div>}</div>
          </section>
        </div>

        <div className="grid gap-5 grid-cols-1 lg:grid-cols-2 mb-5">
          <StatsTable title="By setup" rows={p?.by_setup ?? {}} labels={labels} />
          <StatsTable title="By grade" rows={p?.by_grade ?? {}} labels={{ A: "Grade A", B: "Grade B" }} />
          <StatsTable title="Shadow vs live" rows={p?.by_mode ?? {}} labels={{ SHADOW: "Shadow test", LIVE: "Live" }} />
          <StatsTable title="Intraday vs positional" rows={p?.by_horizon ?? {}} labels={{ intraday: "Intraday", positional: "Positional" }} />
        </div>

        <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[#1e2d45] text-xs font-semibold text-[#e2e8f0]">Every signal</div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead><tr className="text-[10px] tracking-widest text-[#64748b] text-left">
                <th className="px-4 py-2 font-medium">SENT</th><th className="px-2 py-2 font-medium">ID</th>
                <th className="px-2 py-2 font-medium">SETUP</th><th className="px-2 py-2 font-medium">CONTRACT</th>
                <th className="px-2 py-2 font-medium">GRADE</th><th className="px-2 py-2 font-medium">MODE</th>
                <th className="px-2 py-2 font-medium">OUTCOME</th><th className="px-2 py-2 font-medium text-right">NET</th>
                <th className="px-4 py-2 font-medium text-right">R</th>
              </tr></thead>
              <tbody className="divide-y divide-[#1e2d45]">
                {(log.data?.signals ?? []).map(s => (
                  <tr key={s.signal_id} className="hover:bg-[#ffffff04]">
                    <td className="px-4 py-2 font-mono text-[#94a3b8] whitespace-nowrap">{fmtDateTime(s.created_at)}</td>
                    <td className="px-2 py-2 whitespace-nowrap"><Link href={`/signals/${s.signal_id}`} className="font-mono text-[#ff9933] hover:underline">{s.signal_id}</Link></td>
                    <td className="px-2 py-2 text-[#e2e8f0] whitespace-nowrap">{labels[s.setup] ?? s.setup}</td>
                    <td className="px-2 py-2 font-mono text-[#e2e8f0] whitespace-nowrap">{s.contract.tradingsymbol}</td>
                    <td className="px-2 py-2"><GradeBadge grade={s.grade} score={s.score} /></td>
                    <td className="px-2 py-2"><ModeTag mode={s.mode} /></td>
                    <td className="px-2 py-2 text-[#94a3b8] whitespace-nowrap">{s.exit_reason ? EXIT_LABELS[s.exit_reason] ?? s.exit_reason : s.state.replace("_", " ").toLowerCase()}</td>
                    <td className={cn("px-2 py-2 text-right font-mono font-semibold", (s.pnl_rupees ?? 0) > 0 ? "text-[#93c5fd]" : (s.pnl_rupees ?? 0) < 0 ? "text-[#fca5a5]" : "text-[#64748b]")}>{fmtRupees(s.pnl_rupees, true)}</td>
                    <td className="px-4 py-2 text-right font-mono text-[#94a3b8]">{fmtR(s.r_multiple)}</td>
                  </tr>
                ))}
                {!(log.data?.signals ?? []).length && <tr><td colSpan={9} className="px-4 py-8 text-center text-xs text-[#475569]">No signals yet. They appear here the moment they are sent.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  );
}
