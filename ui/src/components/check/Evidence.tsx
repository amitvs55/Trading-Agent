"use client";
import { CheckCircle2, ListChecks, ScrollText, XCircle } from "lucide-react";
import type { CheckReport } from "@/types/check";
import { ChecksList } from "@/components/options/ChecksList";
import { fmtDateTime, fmtPremium } from "@/lib/optionsFormat";

const GATE_LABELS: Record<string, string> = {
  data_fresh: "Market data is fresh", session_open: "Inside the entry window", no_event_window: "No high-impact event window",
  no_fresh_news: "No fresh market-moving news", no_market_shock: "No market shock", liquidity: "Contract is liquid",
  premium_not_rich: "Premium isn't too expensive", min_rr: "Reward:risk to T1 at least 1.3",
};

/** Everything behind the verdict: each check with its numbers, the facts, and every assumption made. */
export function EvidencePanel({ report }: { report: CheckReport }) {
  const ev = report.evidence;
  const plan = report.plan;
  return (
    <section className="grid lg:grid-cols-2 gap-5" aria-label="Evidence">
      <div className="bg-surface border border-[#1e2d45] rounded-xl p-5 min-w-0">
        <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2">
          <ListChecks size={14} className="text-[#ff9933]" aria-hidden /> The 12 checks, for this direction
        </h3>
        <p className="text-[11px] text-[#8391a7] mt-0.5">The same checks every signal goes through, scored for a {report.facts.side > 0 ? "rise (call)" : "fall (put)"}</p>
        <div className="mt-2"><ChecksList checks={ev.pillars} /></div>
        {ev.gates.length > 0 && (
          <>
            <h4 className="text-[10px] tracking-widest text-[#8391a7] mt-4">SAFETY GATES</h4>
            <ul className="mt-1.5 space-y-1.5">
              {ev.gates.map(g => (
                <li key={g.name} className="flex items-start gap-2 text-[12px]">
                  {g.ok ? <CheckCircle2 size={14} className="text-green mt-0.5 flex-shrink-0" aria-label="Pass" />
                        : <XCircle size={14} className="text-red mt-0.5 flex-shrink-0" aria-label="Fail" />}
                  <span className="text-[#cbd5e1]">{GATE_LABELS[g.name] ?? g.name}{!g.ok && g.reason ? <span className="text-[#94a3b8]">: {g.reason}</span> : null}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <div className="space-y-5 min-w-0">
        {plan && (
          <div className="bg-surface border border-[#1e2d45] rounded-xl p-5">
            <h3 className="text-sm font-semibold text-[#e2e8f0]">The plan the odds assume</h3>
            <dl className="mt-3 grid grid-cols-4 gap-3 text-center">
              {[["ENTRY", plan.entry_high, "text-[#e2e8f0]"], ["STOP", plan.stop, "text-[#fca5a5]"], ["T1", plan.t1, "text-[#93c5fd]"],
                ["T2", plan.t2, "text-[#93c5fd]"]].map(([k, v, tone]) => (
                <div key={k as string}><dt className="text-[10px] tracking-widest text-[#8391a7]">{k}</dt>
                  <dd className={`font-mono font-semibold mt-0.5 ${tone}`}>{fmtPremium(v as number)}</dd></div>
              ))}
            </dl>
            <p className="text-[11px] text-[#8391a7] mt-3">
              Reward:risk {plan.rr1.toFixed(2)} to T1, {plan.rr2.toFixed(2)} to T2 · the idea is wrong if the NIFTY future closes a
              5-minute bar {report.facts.side > 0 ? "below" : "above"} {report.facts.candidate.invalidation.toLocaleString("en-IN")}
            </p>
          </div>
        )}
        <div className="bg-surface border border-[#1e2d45] rounded-xl p-5">
          <h3 className="text-sm font-semibold text-[#e2e8f0]">The numbers</h3>
          <dl className="mt-2 divide-y divide-[#1e2d45] text-[12px]">
            {ev.numbers.map(n => (
              <div key={n.label} className="flex items-start justify-between gap-4 py-1.5">
                <dt className="text-[#94a3b8]">{n.label}</dt>
                <dd className="text-right font-mono text-[#e2e8f0] break-words min-w-0">
                  {typeof n.value === "number" ? n.value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : n.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="bg-surface border border-[#1e2d45] rounded-xl p-5">
          <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2">
            <ScrollText size={14} className="text-[#ff9933]" aria-hidden /> Assumptions
          </h3>
          <ul className="mt-2 space-y-1.5 list-disc pl-4 text-[12px] text-[#cbd5e1] leading-snug marker:text-[#475569]">
            {ev.assumptions.map(a => <li key={a}>{a}</li>)}
          </ul>
          <p className="text-[11px] text-[#8391a7] mt-3">
            Data from {ev.data_times.source}, as of {fmtDateTime(ev.data_times.market_data ?? ev.data_times.facts)}
            {ev.history_span ? ` · history ${ev.history_span.sessions} sessions (${ev.history_span.from} to ${ev.history_span.to})` : ""}
          </p>
        </div>
      </div>
    </section>
  );
}
