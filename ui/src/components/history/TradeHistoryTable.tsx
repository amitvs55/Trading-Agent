"use client";
import { useState } from "react";
import { Search, Download, RefreshCw } from "lucide-react";
import { cn, formatINR, formatTokens, formatUSD } from "@/lib/utils";
import { format } from "date-fns";

interface Props {
  records:   Record<string, unknown>[];
  total:     number;
  isLoading: boolean;
  onRefresh: () => void;
  page:      number;
  setPage:   (p: number) => void;
  limit:     number;
}

const STATUS_STYLE: Record<string, string> = {
  executed_simulated: "bg-[#22c55e22] text-green",
  held:               "bg-[#f59e0b22] text-yellow",
  rejected:           "bg-[#ef444422] text-red",
};
const DIR_STYLE: Record<string, string> = {
  long:  "bg-[#22c55e22] text-green",
  short: "bg-[#ef444422] text-red",
  hold:  "bg-[#64748b22] text-[#94a3b8]",
};

function statusLabel(s: string) {
  return s === "executed_simulated" ? "EXECUTED" : s.toUpperCase();
}

function fmtDate(d: unknown) {
  try { return format(new Date(d as string), "dd MMM yyyy, HH:mm"); }
  catch { return String(d ?? "—"); }
}

export function TradeHistoryTable({ records, total, isLoading, onRefresh, page, setPage, limit }: Props) {
  const [search,    setSearch]    = useState("");
  const [statusFil, setStatusFil] = useState("");

  const filtered = records.filter(r => {
    const s = search.toLowerCase();
    const matchText = !s || String(r.ticker ?? "").toLowerCase().includes(s) || String(r.order_id ?? "").toLowerCase().includes(s);
    const matchStatus = !statusFil || String(r.status ?? "") === statusFil;
    return matchText && matchStatus;
  });

  const totalPages = Math.ceil(total / limit);

  return (
    <section id="history-section" className="mt-8">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="font-bold text-base text-[#e2e8f0]">Trade History</h2>
          <p className="text-xs mt-0.5 text-[#64748b]">Simulated NSE/BSE paper trades · <code className="font-mono">logs/trades.jsonl</code> · Prices in ₹</p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap w-full sm:w-auto">
          {/* Search */}
          <div className="relative flex-1 sm:flex-none min-w-[180px]">
            <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#64748b]" />
            <input
              type="text"
              placeholder="Search symbol or order ID…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-surface border border-[#1e2d45] rounded-lg pl-8 pr-3 py-2 text-xs text-[#e2e8f0] w-full sm:w-52 outline-none focus:border-[#ff993344]"
            />
          </div>
          {/* Status filter */}
          <select
            value={statusFil}
            onChange={e => setStatusFil(e.target.value)}
            className="bg-surface border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] outline-none cursor-pointer"
          >
            <option value="">All statuses</option>
            <option value="executed_simulated">Executed</option>
            <option value="held">Held</option>
            <option value="rejected">Rejected</option>
          </select>
          {/* Refresh */}
          <button
            onClick={onRefresh}
            className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] transition-colors"
          >
            <RefreshCw size={11} className={isLoading ? "animate-spin" : ""} /> Refresh
          </button>
          {/* Export placeholder */}
          <button className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">
            <Download size={11} /> Export
          </button>
        </div>
      </div>

      <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
        {/* Phones: one card per trade */}
        <ul className="md:hidden divide-y divide-[#1e2d4560]">
          {isLoading ? Array.from({ length: 4 }).map((_, i) => <li key={i} className="px-4 py-3"><div className="skeleton h-10 rounded" /></li>) :
            filtered.length === 0 ? <li className="px-4 py-8 text-center text-xs text-[#64748b]">No trades found</li> :
            filtered.map((r, i) => {
              const ticker = String(r.ticker ?? "").replace(/\.(NS|BO)$/i, "");
              const status = String(r.status ?? "");
              const detail = String(r.details ?? "").toLowerCase();
              const direction = detail.includes("short") ? "short" : detail.includes("hold") ? "hold" : "long";
              const usage = r.usage as { total_tokens?: number; cost_usd?: number } | null | undefined;
              return (
                <li key={i} className="px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="bg-bg text-[#ff9933] font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#ff993322]">{ticker}</span>
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded", DIR_STYLE[direction] ?? "text-[#94a3b8]")}>{direction.toUpperCase()}</span>
                    </span>
                    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded flex-shrink-0", STATUS_STYLE[status] ?? "text-[#94a3b8]")}>{statusLabel(status)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-1.5 text-[11px] text-[#64748b]">
                    <span>{fmtDate(r.logged_at)}</span>
                    <span className="font-mono">
                      <span className="text-[#e2e8f0]">{typeof r.entry_price === "number" ? formatINR(r.entry_price) : "—"}</span>
                      {usage?.cost_usd != null && <> · {formatUSD(usage.cost_usd)}</>}
                    </span>
                  </div>
                  {r.details != null && <p className="text-[11px] text-[#64748b] mt-1 line-clamp-2">{String(r.details)}</p>}
                </li>
              );
            })}
        </ul>
        <div className="hidden md:block overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-[#1e2d45]">
              {["ORDER ID", "SYMBOL", "EXCHANGE", "STATUS", "DIRECTION", "ENTRY (₹)", "TOKENS", "COST ($)", "DATE (IST)", "DETAILS"].map(h => (
                <th key={h} className="px-4 py-3 text-left text-[10px] text-[#64748b] font-semibold tracking-widest">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-[#1e2d4530]">
                  {Array.from({ length: 10 }).map((_, j) => (
                    <td key={j} className="px-4 py-3"><div className="skeleton h-3 rounded w-20" /></td>
                  ))}
                </tr>
              ))
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-xs text-[#64748b]">No trades found</td>
              </tr>
            ) : (
              filtered.map((r, i) => {
                const ticker    = String(r.ticker    ?? "").replace(/\.(NS|BO)$/i, "");
                const status    = String(r.status    ?? "");
                const direction = String(r.details   ?? "").toLowerCase().includes("short") ? "short"
                               : String(r.details   ?? "").toLowerCase().includes("hold")  ? "hold" : "long";
                const entryPrice = typeof r.entry_price === "number" ? formatINR(r.entry_price) : "—";
                const exchange  = ticker.endsWith(".BO") ? "BSE" : "NSE";
                const usage     = r.usage as { total_tokens?: number; cost_usd?: number } | null | undefined;

                return (
                  <tr key={i} className="border-b border-[#1e2d4530] hover:bg-[#1a2233] transition-colors cursor-pointer">
                    <td className="px-4 py-3 font-mono text-[11px] text-[#64748b]">{String(r.order_id ?? "").slice(0, 12)}</td>
                    <td className="px-4 py-3">
                      <span className="bg-bg text-[#ff9933] font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#ff993322]">{ticker}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="bg-card text-[#64748b] text-[10px] font-semibold px-1.5 py-0.5 rounded">{exchange}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded", STATUS_STYLE[status] ?? "text-[#94a3b8]")}>
                        {statusLabel(status)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded", DIR_STYLE[direction] ?? "text-[#94a3b8]")}>
                        {direction.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#e2e8f0]">{entryPrice}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[#94a3b8]">{usage?.total_tokens != null ? formatTokens(usage.total_tokens) : "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[#e2e8f0]">{usage?.cost_usd != null ? formatUSD(usage.cost_usd) : "—"}</td>
                    <td className="px-4 py-3 text-[11px] text-[#64748b]">{fmtDate(r.logged_at)}</td>
                    <td className="px-4 py-3 text-[11px] text-[#64748b] max-w-[180px] truncate">{String(r.details ?? "")}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between gap-2 flex-wrap px-4 py-3 border-t border-[#1e2d45]">
          <span className="text-xs text-[#64748b]">Showing {filtered.length} of {total} trades</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
              className="text-xs px-2.5 py-1.5 rounded bg-card border border-[#1e2d45] text-[#64748b] disabled:opacity-40">← Prev</button>
            {Array.from({ length: Math.min(5, totalPages) }).map((_, i) => (
              <button key={i} onClick={() => setPage(i)}
                className={cn("text-xs px-2.5 py-1.5 rounded border", i === page
                  ? "bg-[#ff993322] border-[#ff993344] text-[#ff9933]"
                  : "bg-card border-[#1e2d45] text-[#64748b]")}>
                {i + 1}
              </button>
            ))}
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              className="text-xs px-2.5 py-1.5 rounded bg-card border border-[#1e2d45] text-[#64748b] disabled:opacity-40">Next →</button>
          </div>
        </div>
      </div>
    </section>
  );
}
