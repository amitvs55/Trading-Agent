"use client";
import { RefreshCw } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format, parseISO } from "date-fns";
import { useUsageReport } from "@/hooks/useUsageReport";
import { formatINR, formatTokens, formatUSD, USD_INR } from "@/lib/utils";

export default function UsagePage() {
  const { report, error, isLoading, refresh } = useUsageReport();

  const tiles = [
    { label: "TODAY",        usd: report?.today.cost_usd,              sub: `${report?.today.runs ?? 0} runs` },
    { label: "LAST 7 DAYS",  usd: report?.last_7_days.cost_usd,        sub: `${report?.last_7_days.runs ?? 0} runs` },
    { label: "ALL TIME",     usd: report?.all_time.cost_usd,           sub: `${report?.all_time.runs ?? 0} runs` },
    { label: "AVG / RUN",    usd: report?.all_time.avg_cost_per_run,   sub: report?.model ?? "" },
  ];

  const daily  = (report?.daily ?? []).map(d => ({ ...d, label: format(parseISO(d.date), "dd MMM") }));
  const agents = report?.by_agent ?? [];
  const maxAgentCost = Math.max(...agents.map(a => a.cost_usd), 0);

  return (
    <main className="max-w-screen-2xl mx-auto px-6 py-6">
      <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[#e2e8f0]">OpenAI Usage</h1>
          <p className="text-sm text-[#64748b] mt-1">
            Token consumption and estimated cost in US dollars across pipeline runs · ₹ at {USD_INR}/$
          </p>
        </div>
        <button
          onClick={() => refresh()}
          className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] transition-colors"
        >
          <RefreshCw size={11} className={isLoading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 bg-[#ef444411] border border-[#ef444433] rounded-xl px-5 py-4 text-sm text-red">
          ⚠ Could not load usage: {String(error.message ?? error)}
        </div>
      )}

      {/* KPI tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-5">
        {tiles.map(t => (
          <div key={t.label} className="bg-surface border border-[#1e2d45] rounded-xl p-4">
            <div className="text-[10px] text-[#64748b] tracking-widest mb-2">{t.label}</div>
            {isLoading && !report
              ? <div className="skeleton h-7 rounded w-24" />
              : <div className="font-mono font-bold text-2xl text-[#e2e8f0]">{formatUSD(t.usd ?? 0)}</div>}
            <div className="font-mono text-[11px] text-[#64748b] mt-1">≈ {formatINR((t.usd ?? 0) * USD_INR)} · {t.sub}</div>
          </div>
        ))}
        <div className="bg-surface border border-[#1e2d45] rounded-xl p-4">
          <div className="text-[10px] text-[#64748b] tracking-widest mb-2">TOTAL TOKENS</div>
          {isLoading && !report
            ? <div className="skeleton h-7 rounded w-24" />
            : <div className="font-mono font-bold text-2xl text-[#ff9933]">{formatTokens(report?.all_time.total_tokens ?? 0)}</div>}
          <div className="font-mono text-[11px] text-[#64748b] mt-1">
            {formatTokens(report?.all_time.prompt_tokens ?? 0)} in · {formatTokens(report?.all_time.completion_tokens ?? 0)} out
          </div>
        </div>
      </div>

      <div className="grid gap-5 grid-cols-1 lg:grid-cols-[1fr_390px]">
        {/* Daily cost chart */}
        <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
            <span className="text-xs font-semibold text-[#e2e8f0]">Daily cost · last 30 days</span>
            <span className="text-[10px] text-[#64748b]">USD · UTC days</span>
          </div>
          <div className="p-3 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#1e2d45" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={{ stroke: "#1e2d45" }} interval={4} />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} tickLine={false} axisLine={false} width={56}
                       tickFormatter={(v: number) => formatUSD(v)} />
                <Tooltip
                  cursor={{ fill: "#ff99330d" }}
                  contentStyle={{ background: "#1a2233", border: "1px solid #1e2d45", borderRadius: 8, fontSize: 11 }}
                  labelStyle={{ color: "#e2e8f0" }}
                  formatter={(v: number, _n, item) => [
                    `${formatUSD(v)} · ${formatTokens(item.payload.total_tokens)} tokens · ${item.payload.runs} runs`,
                    "Cost",
                  ]}
                />
                <Bar dataKey="cost_usd" fill="#ff9933" radius={[3, 3, 0, 0]} maxBarSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Cost by agent */}
        <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
            <span className="text-xs font-semibold text-[#e2e8f0]">Cost by agent · all time</span>
            {report?.most_expensive_agent && (
              <span className="text-[10px] text-[#64748b]">Top: <span className="text-[#ff9933]">{report.most_expensive_agent.agent.replace(/_/g, " ")}</span></span>
            )}
          </div>
          <div className="p-4 flex flex-col gap-2.5">
            {agents.length === 0 ? (
              <div className="text-xs text-[#475569] text-center py-8">No tracked runs yet. Run an analysis from the Dashboard.</div>
            ) : agents.map(a => (
              <div key={a.agent}>
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="text-[#94a3b8]">{a.agent.replace(/_/g, " ")}</span>
                  <span className="font-mono">
                    <span className="text-[#64748b]">{formatTokens(a.total_tokens)} · </span>
                    <span className="text-[#e2e8f0]">{formatUSD(a.cost_usd)}</span>
                  </span>
                </div>
                <div className="h-1.5 bg-card rounded overflow-hidden">
                  <div className="h-full bg-[#ff9933] rounded" style={{ width: `${maxAgentCost > 0 ? (a.cost_usd / maxAgentCost) * 100 : 0}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {report && report.untracked_runs > 0 && (
        <p className="text-[11px] text-[#475569] mt-4">
          {report.untracked_runs} older run{report.untracked_runs === 1 ? "" : "s"} in the trade log predate usage tracking and are not counted.
        </p>
      )}
    </main>
  );
}
