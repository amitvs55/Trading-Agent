"use client";
import { ArrowDownRight, ArrowUpRight, ListFilter } from "lucide-react";
import type { Evaluation } from "@/types/options";
import { cn } from "@/lib/utils";
import { fmtTime } from "@/lib/optionsFormat";

const OUTCOME: Record<Evaluation["outcome"], { label: string; cls: string }> = {
  SIGNAL:      { label: "Signal sent",  cls: "text-green border-[#22c55e33] bg-[#22c55e0d]" },
  NO_TRADE:    { label: "No trade",     cls: "text-[#94a3b8] border-[#1e2d45] bg-card" },
  GRADE_C:     { label: "Grade C",      cls: "text-yellow border-[#f59e0b33] bg-[#f59e0b0d]" },
  OVER_BUDGET: { label: "Over budget",  cls: "text-yellow border-[#f59e0b33] bg-[#f59e0b0d]" },
};

/** Every setup that fired and what the engine decided: the honest "why no trade" record. */
export function NoTradeLog({ rows, labels }: { rows: Evaluation[]; labels: Record<string, string> }) {
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center gap-2">
        <ListFilter size={13} className="text-[#ff9933]" />
        <span className="text-xs font-semibold text-[#e2e8f0]">Decision log</span>
        <span className="text-[10px] text-[#64748b]">every trigger that fired today, and why it did or didn't become a signal</span>
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-8 text-center text-xs text-[#475569]">No setup has triggered yet today.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[10px] tracking-widest text-[#64748b] text-left">
                <th className="px-4 py-2 font-medium">TIME</th>
                <th className="px-2 py-2 font-medium">SETUP</th>
                <th className="px-2 py-2 font-medium">SIDE</th>
                <th className="px-2 py-2 font-medium">SCORE</th>
                <th className="px-2 py-2 font-medium">OUTCOME</th>
                <th className="px-4 py-2 font-medium">REASON</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {rows.map(r => (
                <tr key={r.id} className="hover:bg-[#ffffff04]">
                  <td className="px-4 py-2 font-mono text-[#94a3b8] tabular-nums whitespace-nowrap">{fmtTime(r.ts)}</td>
                  <td className="px-2 py-2 text-[#e2e8f0] whitespace-nowrap">{labels[r.setup] ?? r.setup}</td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    {r.side > 0 ? <span className="inline-flex items-center gap-0.5 text-green"><ArrowUpRight size={12} />CE</span>
                                : <span className="inline-flex items-center gap-0.5 text-red"><ArrowDownRight size={12} />PE</span>}
                  </td>
                  <td className="px-2 py-2 font-mono text-[#94a3b8] tabular-nums">{r.score != null ? r.score.toFixed(0) : "—"}</td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded border", OUTCOME[r.outcome].cls)}>{OUTCOME[r.outcome].label}</span>
                  </td>
                  <td className="px-4 py-2 text-[#94a3b8]">{r.reasons}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
