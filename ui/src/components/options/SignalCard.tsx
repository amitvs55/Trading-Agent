"use client";
import Link from "next/link";
import { ChevronRight, Clock, Hourglass, ShieldAlert } from "lucide-react";
import type { Quote, Signal, Status } from "@/types/options";
import { cn } from "@/lib/utils";
import { EXIT_LABELS, fmtDate, fmtPremium, fmtR, fmtRupees, fmtTime } from "@/lib/optionsFormat";
import { DirectionPill, GradeBadge, ModeTag, StateBadge, STATUS_STYLE } from "./StatusBits";

const OPEN = new Set(["TRIGGERED", "ACTIVE", "T1_HIT"]);

/** Where the premium sits between the stop and target 2: risk zone left of entry, reward zone right. */
function PriceTrack({ s, current }: { s: Signal; current: number | null }) {
  const entry = s.fill_price ?? s.entry_high;
  const lo = Math.min(s.initial_stop ?? s.stop_loss, s.stop_loss);
  const hi = s.t2;
  const span = hi - lo || 1;
  const pos = (v: number) => Math.min(100, Math.max(0, ((v - lo) / span) * 100));
  const marks = [
    { v: s.initial_stop ?? s.stop_loss, label: "SL" },
    { v: entry, label: s.fill_price ? "Fill" : "Entry" },
    { v: s.t1, label: "T1" },
    { v: s.t2, label: "T2" },
  ];
  const trailing = s.state === "T1_HIT" && s.stop_loss > entry;
  return (
    <div className="pt-6 pb-5 px-1" role="img"
         aria-label={`Premium ${current ?? "unknown"}; stop ${s.stop_loss}, entry ${entry}, T1 ${s.t1}, T2 ${s.t2}`}>
      <div className="relative h-1.5 rounded-full bg-[#0b0f1a]">
        <div className="absolute inset-y-0 left-0 rounded-l-full bg-[#e6676740]" style={{ width: `${pos(entry)}%` }} />
        <div className="absolute inset-y-0 rounded-r-full bg-[#3987e540]" style={{ left: `${pos(entry)}%`, right: 0 }} />
        {trailing && <div className="absolute -top-1 bottom-[-4px] w-0.5 bg-green" style={{ left: `${pos(s.stop_loss)}%` }} title={`Trailing stop ${s.stop_loss}`} />}
        {marks.map(m => (
          <div key={m.label} className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2" style={{ left: `${pos(m.v)}%` }}>
            <div className="w-0.5 h-3 bg-[#64748b]" />
            <div className="absolute top-4 left-1/2 -translate-x-1/2 text-[9px] text-[#64748b] whitespace-nowrap">{m.label}</div>
          </div>
        ))}
        {current != null && (
          <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 transition-all duration-700" style={{ left: `${pos(current)}%` }}>
            <div className="w-3.5 h-3.5 rounded-full bg-[#e2e8f0] ring-2 ring-[#111827] shadow" />
            <div className="absolute -top-6 left-1/2 -translate-x-1/2 font-mono text-[10px] font-bold text-[#e2e8f0] bg-[#1a2233] border border-[#1e2d45] rounded px-1 whitespace-nowrap">
              {fmtPremium(current)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Price({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "risk" | "reward" }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] tracking-widest text-[#64748b]">{label}</div>
      <div className={cn("font-mono text-base font-bold mt-0.5 tabular-nums",
        tone === "risk" ? "text-[#fca5a5]" : tone === "reward" ? "text-[#93c5fd]" : "text-[#e2e8f0]")}>{value}</div>
      {sub && <div className="text-[10px] text-[#64748b] mt-0.5 leading-snug">{sub}</div>}
    </div>
  );
}

function CheckCounts({ s }: { s: Signal }) {
  const counts: Record<Status, number> = { pass: 0, warn: 0, fail: 0, na: 0 };
  s.checks.forEach(c => { counts[c.status] += 1; });
  return (
    <span className="inline-flex items-center gap-2">
      {(["pass", "warn", "fail", "na"] as Status[]).filter(k => counts[k]).map(k => {
        const S = STATUS_STYLE[k];
        return <span key={k} className={cn("inline-flex items-center gap-0.5 text-[11px] font-mono", S.text)} title={`${counts[k]} ${S.label}`}><S.icon size={11} />{counts[k]}</span>;
      })}
    </span>
  );
}

export function SignalCard({ s, quote, setupLabel, compact = false, wide = false }: {
  s: Signal; quote?: Quote; setupLabel: string; compact?: boolean; wide?: boolean;
}) {
  const open = OPEN.has(s.state);
  const current = open ? (quote?.bid ?? quote?.ltp ?? null) : s.exit_price;
  const risk = s.entry_high - s.stop_loss;
  const rr1 = risk > 0 ? (s.t1 - s.entry_high) / risk : 0;
  const rr2 = risk > 0 ? (s.t2 - s.entry_high) / risk : 0;
  const up = s.action === "BUY_CE";
  const result = s.pnl_rupees;

  return (
    <article className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className={cn("h-0.5", up ? "bg-green" : "bg-red")} />
      <div className="px-4 pt-3.5 pb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <DirectionPill action={s.action} />
            <GradeBadge grade={s.grade} score={s.score} />
            <ModeTag mode={s.mode} />
            {s.horizon === "positional" && <span className="text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded bg-[#a78bfa14] text-[#c4b5fd] border border-[#a78bfa33]">POSITIONAL</span>}
          </div>
          <div className="mt-2 font-mono font-bold text-[#e2e8f0] text-[15px] truncate">{s.contract.tradingsymbol}</div>
          <div className="text-[11px] text-[#64748b] mt-0.5">
            {setupLabel} · expiry {fmtDate(s.contract.expiry)} · lot {s.contract.lot_size} · {s.signal_id} · {fmtTime(s.created_at)}
          </div>
        </div>
        <StateBadge state={s.state} />
      </div>

      {!open && result != null && (
        <div className={cn("mx-4 mb-3 px-3 py-2 rounded-lg border flex items-center justify-between",
          result > 0 ? "border-[#3987e544] bg-[#3987e50f]" : "border-[#e6676744] bg-[#e667670f]")}>
          <span className="text-xs text-[#94a3b8]">{EXIT_LABELS[s.exit_reason ?? ""] ?? s.exit_reason} @ <span className="font-mono text-[#e2e8f0]">{fmtPremium(s.exit_price)}</span></span>
          <span className="font-mono font-bold text-sm">
            <span className={result > 0 ? "text-[#93c5fd]" : "text-[#fca5a5]"}>{fmtRupees(result, true)}</span>
            <span className="text-[#94a3b8] ml-2">{fmtR(s.r_multiple)}</span>
          </span>
        </div>
      )}
      {!open && result == null && (
        <div className="mx-4 mb-3 px-3 py-2 rounded-lg border border-[#1e2d45] bg-card text-xs text-[#94a3b8]">
          {EXIT_LABELS[s.exit_reason ?? s.state] ?? s.state}: no trade, not counted in the track record.
        </div>
      )}

      <div className={cn("px-4 grid grid-cols-2 gap-x-3 gap-y-3", wide && "md:grid-cols-4")}>
        <Price label="ENTRY" value={`${fmtPremium(s.entry_low)}–${fmtPremium(s.entry_high)}`}
               sub={s.fill_price ? `filled ${fmtPremium(s.fill_price)} at ${fmtTime(s.filled_at)}` : `limit · valid till ${fmtTime(s.valid_until)}`} />
        <Price label={s.state === "T1_HIT" ? "STOP (TRAILING)" : "STOP-LOSS"} value={fmtPremium(s.stop_loss)} tone="risk" sub={`or ${s.invalidation_rule}`} />
        <Price label="TARGET 1" value={fmtPremium(s.t1)} tone="reward" sub={`R:R 1 : ${rr1.toFixed(1)} · ${s.lots >= 2 ? "book half" : "lock half the gain"}`} />
        <Price label="TARGET 2" value={fmtPremium(s.t2)} tone="reward" sub={`R:R 1 : ${rr2.toFixed(1)}`} />
      </div>

      {!compact && <div className="px-4"><PriceTrack s={s} current={current} /></div>}

      <div className="px-4 py-3 mt-1 border-t border-[#1e2d45] flex flex-wrap items-center justify-between gap-3 text-[11px]">
        <div className="flex items-center gap-4 flex-wrap text-[#94a3b8]">
          <span className="inline-flex items-center gap-1.5">
            <ShieldAlert size={12} className={s.over_budget ? "text-yellow" : "text-[#64748b]"} />
            {s.lots} lot · risk <span className="font-mono text-[#e2e8f0]">{fmtRupees(s.risk_rupees)}</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            {s.horizon === "intraday" ? <Clock size={12} className="text-[#64748b]" /> : <Hourglass size={12} className="text-[#64748b]" />}
            {s.horizon === "intraday" ? `time stop ${s.time_stop?.slice(0, 5) ?? "—"}` : `hold until ${fmtDate(s.exit_by)} 15:15`}
          </span>
          <CheckCounts s={s} />
          {open && quote && <span className="text-[#64748b]">quote {fmtTime(quote.ts)} · bid {fmtPremium(quote.bid)} / ask {fmtPremium(quote.ask)}</span>}
        </div>
        <Link href={`/signals/${s.signal_id}`} className="inline-flex items-center gap-0.5 text-[#ff9933] hover:underline font-medium">
          Full analysis <ChevronRight size={13} />
        </Link>
      </div>
    </article>
  );
}
