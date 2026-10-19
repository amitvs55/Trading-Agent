"use client";
import type { CheckReport } from "@/types/check";
import { fmtNum, fmtPremium, fmtRupees, fmtTime } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";
import { pnlTone } from "./Money";

/** ₹ P&L (after charges) if NIFTY is at each level at a few moments; text carries the sign, colour only helps. */
export function ScenarioTable({ report }: { report: CheckReport }) {
  const s = report.scenarios!;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden" aria-label="Scenarios">
      <div className="px-5 py-3 border-b border-[#1e2d45]">
        <h3 className="text-sm font-semibold text-[#e2e8f0]">If NIFTY is at…</h3>
        <p className="text-[11px] text-[#8391a7] mt-0.5">Key levels, the open-interest walls and the market&apos;s 1σ / 2σ moves (σ ≈ {fmtNum(s.sd)} points over your horizon)</p>
      </div>
      {/* Focusable, so the table can be scrolled sideways from the keyboard on narrow screens */}
      <div className="overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#ff9933]"
           tabIndex={0} role="region" aria-label="Scenario table">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
              <th scope="col" className="px-4 sm:px-5 py-2 font-medium">NIFTY AT</th>
              {s.moments.map(m => (
                <th key={m.label} scope="col" className="px-3 sm:px-5 py-2 font-medium text-right">
                  {m.label.toUpperCase()} <span className="block sm:inline normal-case tracking-normal">({fmtTime(m.at)})</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e2d45]">
            {s.rows.map(r => (
              <tr key={r.spot} className={cn(r.label === "now" && "bg-[#ffffff05]")}>
                <th scope="row" className="px-4 sm:px-5 py-2 text-left font-normal">
                  <span className="font-mono text-[#e2e8f0] whitespace-nowrap">{fmtNum(r.spot)} <span className="text-[#8391a7]">({r.move_pct >= 0 ? "+" : ""}{r.move_pct.toFixed(2)}%)</span></span>
                  <span className="block text-[11px] text-[#94a3b8]">{r.label}</span>
                </th>
                {r.cells.map((c, i) => (
                  <td key={i} className="px-3 sm:px-5 py-2 text-right whitespace-nowrap">
                    <span className={cn("font-mono font-semibold", pnlTone(c.pnl))}>{fmtRupees(c.pnl, true)}</span>
                    <span className="block text-[10px] text-[#8391a7] font-mono">option ₹{fmtPremium(c.value)}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
