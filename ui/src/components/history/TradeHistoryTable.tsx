"use client";
import { useEffect, useState } from "react";
import { Search, Download, RefreshCw } from "lucide-react";
import { cn, formatINR, formatTokens, formatUSD } from "@/lib/utils";
import { format } from "date-fns";
import { useTradeHistory, type ResearchRecord } from "@/hooks/useTradeHistory";

const STATUS_STYLE: Record<string, string> = {
  executed_simulated: "bg-[#22c55e22] text-green",
  held:               "bg-[#f59e0b22] text-yellow",
  rejected:           "bg-[#ef444422] text-red",
  failed:             "bg-[#ef444422] text-red",
  cancelled:          "bg-[#64748b22] text-[#94a3b8]",
  running:            "bg-[#3987e522] text-[#93c5fd]",
};

function statusLabel(s: string) {
  return s === "executed_simulated" ? "EXECUTED" : s.toUpperCase();
}

function fmtDate(d: string | null | undefined) {
  if (!d) return "—";
  try { return format(new Date(d), "dd MMM yyyy, HH:mm"); } catch { return d; }
}

const money = (v: number | null | undefined) => (typeof v === "number" ? formatINR(v) : "—");

// ── CSV export ──────────────────────────────────────────────────────────────

const CSV_COLUMNS: [string, (r: ResearchRecord) => unknown][] = [
  ["run_id", r => r.run_id], ["order_id", r => r.order_id], ["date_ist", r => r.logged_at],
  ["symbol", r => r.ticker], ["exchange", r => r.exchange], ["status", r => r.status], ["decision", r => r.action],
  ["entry_inr", r => r.entry_price], ["stop_loss_inr", r => r.stop_loss], ["target_inr", r => r.take_profit],
  ["size_pct", r => r.size_pct], ["tokens", r => r.usage?.total_tokens], ["cost_usd", r => r.cost_usd],
  ["model", r => r.model], ["requested_by", r => r.requested_by], ["details", r => r.details],
];

/** A cell a spreadsheet won't execute: text starting with = + - @ (or a tab/CR) is a formula
 *  injection risk, so it is prefixed with an apostrophe. */
function csvCell(v: unknown): string {
  if (v == null) return "";
  let s = String(v);
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(rows: ResearchRecord[]) {
  const lines = [CSV_COLUMNS.map(c => c[0]).join(","), ...rows.map(r => CSV_COLUMNS.map(([, get]) => csvCell(get(r))).join(","))];
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });   // BOM: Excel reads UTF-8
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `research-history-${format(new Date(), "yyyyMMdd-HHmm")}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Research runs and their simulated trade decisions, paged and filtered on the server. */
export function TradeHistoryTable({ limit }: { limit: number }) {
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [statusFil, setStatusFil] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {                                  // search as you type, without a request per keystroke
    const t = setTimeout(() => { setQuery(search.trim()); setPage(0); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const { records, total, isLoading, refresh, fetchAll } = useTradeHistory({
    limit, offset: page * limit, ticker: query, status: statusFil,
  });
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const pageWindow = Array.from({ length: Math.min(5, totalPages) }, (_, i) =>
    Math.min(Math.max(0, page - 2), Math.max(0, totalPages - 5)) + i);

  const exportAll = async () => {
    setExporting(true);
    try { downloadCsv(await fetchAll()); } finally { setExporting(false); }
  };

  return (
    <section id="history-section" className="mt-8">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="font-bold text-base text-[#e2e8f0]">Trade History</h2>
          <p className="text-xs mt-0.5 text-[#8391a7]">Research runs and their simulated NSE/BSE decisions · kept in the database · prices in ₹</p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap w-full sm:w-auto">
          <div className="relative flex-1 sm:flex-none min-w-[180px]">
            <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8391a7]" aria-hidden />
            <input
              type="search"
              aria-label="Search by symbol"
              placeholder="Search symbol…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="bg-surface border border-[#1e2d45] rounded-lg pl-8 pr-3 py-2 text-base lg:text-xs text-[#e2e8f0] w-full sm:w-52 outline-none focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]"
            />
          </div>
          <select
            aria-label="Filter by status"
            value={statusFil}
            onChange={e => { setStatusFil(e.target.value); setPage(0); }}
            className="bg-surface border border-[#1e2d45] rounded-lg px-3 py-2 text-base lg:text-xs text-[#94a3b8] outline-none cursor-pointer focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]"
          >
            <option value="">All statuses</option>
            <option value="executed_simulated">Executed</option>
            <option value="held">Held</option>
            <option value="rejected">Rejected</option>
          </select>
          <button
            onClick={() => refresh()}
            className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]"
          >
            <RefreshCw size={11} className={isLoading ? "animate-spin" : ""} aria-hidden /> Refresh
          </button>
          <button
            onClick={exportAll}
            disabled={exporting || total === 0}
            className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] transition-colors disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]"
          >
            <Download size={11} aria-hidden /> {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

      <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
        {/* Phones: one card per run */}
        <ul className="md:hidden divide-y divide-[#1e2d4560]">
          {isLoading ? Array.from({ length: limit }).map((_, i) => <li key={i} className="px-4 py-3"><div className="skeleton h-[74px] rounded" /></li>) :
            records.length === 0 ? <li className="px-4 py-8 text-center text-xs text-[#8391a7]">No runs found</li> :
            records.map(r => (
              <li key={r.run_id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="bg-bg text-[#ff9933] font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#ff993322]">{r.ticker.replace(/\.(NS|BO)$/i, "")}</span>
                    <span className="bg-card text-[#8391a7] text-[10px] font-semibold px-1.5 py-0.5 rounded">{r.exchange}</span>
                  </span>
                  <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded flex-shrink-0", STATUS_STYLE[r.status] ?? "text-[#94a3b8]")}>{statusLabel(r.status)}</span>
                </div>
                <div className="flex items-center justify-between gap-2 mt-1.5 text-[11px] text-[#8391a7]">
                  <span>{fmtDate(r.logged_at)}</span>
                  <span className="font-mono">
                    <span className="text-[#e2e8f0]">{money(r.entry_price)}</span>
                    {r.cost_usd != null && <> · {formatUSD(r.cost_usd)}</>}
                  </span>
                </div>
                {r.details && <p className="text-[11px] text-[#8391a7] mt-1 line-clamp-2">{r.details}</p>}
              </li>
            ))}
        </ul>
        <div className="hidden md:block overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-[#1e2d45]">
              {["ORDER ID", "SYMBOL", "EXCHANGE", "STATUS", "ENTRY (₹)", "STOP / TARGET (₹)", "TOKENS", "COST ($)", "DATE (IST)", "DETAILS"].map(h => (
                <th key={h} scope="col" className="px-4 py-3 text-left text-[10px] text-[#8391a7] font-semibold tracking-widest whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: limit }).map((_, i) => (
                <tr key={i} className="border-b border-[#1e2d4530]">
                  {Array.from({ length: 10 }).map((_, j) => (
                    <td key={j} className="px-4 py-3"><div className="skeleton h-[18px] rounded w-20" /></td>
                  ))}
                </tr>
              ))
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-xs text-[#8391a7]">No runs found</td>
              </tr>
            ) : (
              records.map(r => (
                <tr key={r.run_id} className="border-b border-[#1e2d4530] hover:bg-[#1a2233] transition-colors">
                  <td className="px-4 py-3 font-mono text-[11px] text-[#8391a7]">{(r.order_id ?? r.run_id).slice(0, 12)}</td>
                  <td className="px-4 py-3">
                    <span className="bg-bg text-[#ff9933] font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-[#ff993322]">{r.ticker.replace(/\.(NS|BO)$/i, "")}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="bg-card text-[#8391a7] text-[10px] font-semibold px-1.5 py-0.5 rounded">{r.exchange}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded", STATUS_STYLE[r.status] ?? "text-[#94a3b8]")}>{statusLabel(r.status)}</span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-[#e2e8f0]">{money(r.entry_price)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#94a3b8] whitespace-nowrap">
                    {r.stop_loss == null && r.take_profit == null ? "—" : <>{money(r.stop_loss)} / {money(r.take_profit)}</>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-[#94a3b8]">{r.usage?.total_tokens != null ? formatTokens(r.usage.total_tokens) : "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#e2e8f0]">{r.cost_usd != null ? formatUSD(r.cost_usd) : "—"}</td>
                  <td className="px-4 py-3 text-[11px] text-[#8391a7] whitespace-nowrap">{fmtDate(r.logged_at)}</td>
                  <td className="px-4 py-3 text-[11px] text-[#8391a7] max-w-[220px] truncate" title={r.details ?? undefined}>{r.details}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>

        <nav aria-label="History pages" className="flex items-center justify-between gap-2 flex-wrap px-4 py-3 border-t border-[#1e2d45]">
          <span className="text-xs text-[#8391a7]">{total ? `${page * limit + 1}–${Math.min(total, (page + 1) * limit)} of ${total} runs` : "0 runs"}</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
              className="text-xs px-2.5 py-1.5 rounded bg-card border border-[#1e2d45] text-[#8391a7] disabled:opacity-40">← Prev</button>
            {pageWindow.map(i => (
              <button key={i} onClick={() => setPage(i)} aria-current={i === page ? "page" : undefined}
                className={cn("text-xs px-2.5 py-1.5 rounded border", i === page
                  ? "bg-[#ff993322] border-[#ff993344] text-[#ff9933]"
                  : "bg-card border-[#1e2d45] text-[#8391a7]")}>
                {i + 1}
              </button>
            ))}
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              className="text-xs px-2.5 py-1.5 rounded bg-card border border-[#1e2d45] text-[#8391a7] disabled:opacity-40">Next →</button>
          </div>
        </nav>
      </div>
    </section>
  );
}
