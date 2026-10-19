"use client";
import { CheckCircle2, CircleHelp, MinusCircle, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import type { CheckReport } from "@/types/check";
import { fmtDateTime, fmtPremium } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";

// Lighter tones than the status colours, so the verdict word passes contrast on its tinted panel
const TONE = {
  good:    { ring: "border-[#22c55e55] bg-[#22c55e0f]", text: "text-[#4ade80]", icon: CheckCircle2 },
  warn:    { ring: "border-[#f59e0b55] bg-[#f59e0b0f]", text: "text-[#fcd34d]", icon: MinusCircle },
  bad:     { ring: "border-[#ef444455] bg-[#ef44440f]", text: "text-[#fca5a5]", icon: XCircle },
  neutral: { ring: "border-[#1e2d45] bg-card", text: "text-[#94a3b8]", icon: CircleHelp },
} as const;

export function VerdictCard({ report }: { report: CheckReport }) {
  const v = report.verdict;
  const f = report.facts;
  const T = TONE[v.tone] ?? TONE.neutral;
  const c = f.contract;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden" aria-label="Verdict">
      <div className="px-5 py-4 border-b border-[#1e2d45] flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] tracking-widest text-[#8391a7]">
            {f.index} · {c.right === "CE" ? "CALL" : "PUT"} · {f.horizon === "expiry" ? "HOLD TO EXPIRY" : "INTRADAY"}
          </div>
          <h2 className="font-mono text-xl font-bold text-[#e2e8f0] mt-1 break-all">{c.symbol}</h2>
          <p className="text-[12px] text-[#94a3b8] mt-1">
            bid {fmtPremium(c.bid)} · ask {fmtPremium(c.ask)}
            {c.iv ? ` · IV ${(c.iv * 100).toFixed(1)}%` : ""}
            {c.greeks ? ` · delta ${c.greeks.delta.toFixed(2)}` : ""}
            {f.spot ? ` · NIFTY ${f.spot.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` : ""}
          </p>
        </div>
        <div className={cn("flex items-center gap-3 rounded-xl border px-4 py-3", T.ring)} role="status">
          <T.icon size={26} className={T.text} aria-hidden />
          <div>
            <div className={cn("text-lg font-bold leading-tight", T.text)}>{v.call}</div>
            {v.score != null && <div className="text-[11px] text-[#94a3b8]">direction score {Math.round(v.score)}/100</div>}
          </div>
        </div>
      </div>
      <div className="px-5 py-4">
        <p className="text-sm text-[#e2e8f0]">{v.summary}</p>
        <div className="grid sm:grid-cols-2 gap-4 mt-4">
          <Reasons title="For" items={v.for} icon={ThumbsUp} tone="text-green" empty="Nothing clearly in favour" />
          <Reasons title="Against" items={v.against} icon={ThumbsDown} tone="text-red" empty="Nothing clearly against" />
        </div>
        <p className="text-[11px] text-[#8391a7] mt-4 leading-relaxed">
          From {f.source} · data {f.data_as_of ? fmtDateTime(f.data_as_of) : fmtDateTime(f.as_of)} · checked {fmtDateTime(f.checked_at)}
          {v.basis ? ` · odds from ${v.basis}` : ""}. {f.candidate.note}.
          {f.engine_signals.length > 0 && ` The engine has signal ${f.engine_signals.map(s => `${s.id} (${s.state.toLowerCase()}, grade ${s.grade})`).join(", ")} on this contract.`}
          {" "}Probabilities come from models and history, not promises.
        </p>
      </div>
    </section>
  );
}

function Reasons({ title, items, icon: Icon, tone, empty }: {
  title: string; items: string[]; icon: typeof ThumbsUp; tone: string; empty: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] tracking-widest text-[#8391a7] uppercase">
        <Icon size={12} className={tone} aria-hidden /> {title}
      </div>
      {items.length ? (
        <ul className="mt-1.5 space-y-1.5">
          {items.map(t => <li key={t} className="text-[12px] text-[#cbd5e1] leading-snug break-words">{t}</li>)}
        </ul>
      ) : <p className="mt-1.5 text-[12px] text-[#8391a7]">{empty}</p>}
    </div>
  );
}
