"use client";
import { History, Target } from "lucide-react";
import type { ChecksResponse, CheckRow } from "@/types/check";
import { fmtDateTime, fmtRupees } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";
import { pnlTone } from "./Money";

// Small text: the lighter tones, which pass contrast on the dark panel
const CALL_TONE: Record<string, string> = {
  "Worth taking": "text-[#4ade80] border-[#22c55e44]", Marginal: "text-[#fcd34d] border-[#f59e0b44]",
  Avoid: "text-[#fca5a5] border-[#ef444444]", "Can't price": "text-[#94a3b8] border-[#1e2d45]",
};

function Result({ row }: { row: CheckRow }) {
  const o = row.outcome ?? {};
  const parts: { label: string; pnl: number | null | undefined }[] = [];
  if (o.after_30m) parts.push({ label: "30 min", pnl: o.after_30m.pnl });
  if (o.at_exit) parts.push({ label: row.summary?.settles ? "expiry" : "exit", pnl: o.at_exit.pnl });
  if (!parts.length) return <span className="text-[11px] text-[#8391a7]">result pending</span>;
  return (
    <span className="text-[11px] text-[#94a3b8]">
      {parts.map((p, i) => (
        <span key={p.label}>{i > 0 && " · "}{p.label} <span className={cn("font-mono", pnlTone(p.pnl))}>{fmtRupees(p.pnl, true)}</span></span>
      ))}
    </span>
  );
}

export function RecentChecks({ data, onOpen, activeId }: { data: ChecksResponse | undefined; onOpen: (id: string) => void; activeId?: string }) {
  const rows = data?.checks ?? [];
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden" aria-label="Your recent checks">
      <div className="px-4 py-3 border-b border-[#1e2d45]">
        <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2"><History size={14} className="text-[#ff9933]" aria-hidden /> Your recent checks</h3>
        <p className="text-[11px] text-[#8391a7] mt-0.5">What the checker said, and what actually happened after</p>
      </div>
      {!data ? <ul>{[0, 1, 2].map(i => <li key={i} className="px-4 py-3"><div className="skeleton h-9 rounded" /></li>)}</ul>
        : !rows.length ? <p className="px-4 py-6 text-center text-[12px] text-[#8391a7]">No checks yet. Your checks and their results appear here.</p>
        : (
          <ul className="divide-y divide-[#1e2d45] max-h-[420px] overflow-y-auto">
            {rows.map(r => (
              <li key={r.id}>
                <button type="button" onClick={() => onOpen(r.id)} aria-current={r.id === activeId ? "true" : undefined}
                        className={cn("w-full text-left px-4 py-2.5 hover:bg-[#ffffff05] focus-visible:outline-none focus-visible:bg-[#ffffff08]",
                                      r.id === activeId && "bg-[#ff99330a]")}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[12px] text-[#e2e8f0] truncate">{r.symbol ?? r.query}</span>
                    {r.summary?.verdict && (
                      <span className={cn("flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded border", CALL_TONE[r.summary.verdict])}>{r.summary.verdict}</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-0.5">
                    <span className="text-[11px] text-[#8391a7]">{fmtDateTime(r.created_at)}{r.paper ? " · paper" : ""}</span>
                    <Result row={r} />
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
    </section>
  );
}

export function CheckerRecord({ data }: { data: ChecksResponse | undefined }) {
  const rec = data?.record;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl p-4" aria-label="How the checker has done">
      <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2"><Target size={14} className="text-[#ff9933]" aria-hidden /> How the checker has done</h3>
      {!rec ? <div className="skeleton h-16 rounded mt-3" /> : rec.scored === 0 ? (
        <p className="text-[12px] text-[#8391a7] mt-2">No finished checks yet. Each check is scored once its horizon has passed.</p>
      ) : (
        <>
          <p className="text-[11px] text-[#8391a7] mt-1">{rec.scored} of {rec.checks} checks scored{!rec.enough && " · too few to judge yet (30+ needed)"}</p>
          <ul className="mt-2 space-y-1 text-[12px]">
            {rec.verdicts.map(v => (
              <li key={v.verdict} className="flex justify-between gap-2">
                <span className="text-[#cbd5e1]">{v.verdict}</span>
                <span className="font-mono text-[#94a3b8]">{Math.round(v.made_money_rate * 100)}% made money · n={v.checks}</span>
              </li>
            ))}
          </ul>
          {rec.calibration.length > 0 && (
            <>
              <h4 className="text-[10px] tracking-widest text-[#8391a7] mt-3">SAID vs HAPPENED (chance of profit)</h4>
              <ul className="mt-1 space-y-0.5 text-[11px] font-mono text-[#94a3b8]">
                {rec.calibration.map(c => (
                  <li key={c.from}>said {Math.round(c.said * 100)}% → {Math.round(c.happened * 100)}% (n={c.checks})</li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
