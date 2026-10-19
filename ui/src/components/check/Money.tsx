"use client";
import type { CheckReport, Odds, PlanOdds, PlanOutcome } from "@/types/check";
import { fmtNum, fmtPremium, fmtRupees } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";

export const pnlTone = (v: number | null | undefined) =>
  v == null || Math.round(v) === 0 ? "text-[#94a3b8]" : v > 0 ? "text-[#93c5fd]" : "text-[#fca5a5]";

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl p-4 min-w-0">
      <div className="text-[10px] text-[#8391a7] tracking-widest mb-1.5">{label}</div>
      <div className={cn("font-bold text-xl leading-7 font-mono tabular-nums truncate", tone ?? "text-[#e2e8f0]")}>{value}</div>
      {sub && <div className="text-[11px] text-[#8391a7] mt-1 leading-snug">{sub}</div>}
    </div>
  );
}

export function PositionTiles({ report }: { report: CheckReport }) {
  const p = report.position!;
  const c = report.facts.contract;
  const lotsText = p.lots ? `${p.lots} lot${p.lots > 1 ? "s" : ""} · ${fmtNum(p.units)} qty at ₹${fmtPremium(p.entry)}`
    : `Shown for 1 lot · you need ${fmtRupees(p.min_amount)} for one`;
  return (
    <div>
    {p.entry_note && <p className="mb-3 text-[12px] text-[#94a3b8] bg-[#3987e50d] border border-[#3987e533] rounded-lg px-3 py-2">{p.entry_note}.</p>}
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Tile label="CAPITAL USED" value={fmtRupees(p.capital_used)} sub={lotsText + (p.leftover ? ` · ${fmtRupees(p.leftover)} left over` : "")} />
      <Tile label="MOST YOU CAN LOSE" value={fmtRupees(-p.max_loss, true)} tone="text-[#fca5a5]"
            sub={`if it expires worthless (premium + ${fmtRupees(p.buy_charges)} charges)`} />
      <Tile label="BREAKEVEN AT EXPIRY" value={fmtNum(p.breakeven, 0)}
            sub={`NIFTY ${c.right === "CE" ? "above" : "below"} this at expiry, after round-trip charges`} />
      <Tile label="RISK TO THE STOP" value={p.stop_risk != null ? fmtRupees(-p.stop_risk, true) : "—"}
            tone={p.over_budget ? "text-yellow" : "text-[#e2e8f0]"}
            sub={p.stop_risk != null
              ? `${p.over_budget ? "over" : "within"} your ${report.params.risk_pct}% rule (${fmtRupees(p.budget)})`
              : "no plan for this contract"} />
    </div>
    </div>
  );
}

// Validated categorical slots for the dark surface (dataviz check: lightness, chroma, CVD and
// normal-vision separation all pass in this order); every part is also labelled with its share
type Shown = "t2" | "t1" | "time" | "stop";
const SHOWN: { key: Shown; label: string; color: string }[] = [
  { key: "t2", label: "Target 2", color: "#3987e5" },
  { key: "t1", label: "T1, then out", color: "#199e70" },
  { key: "time", label: "Time exit", color: "#9085e9" },
  { key: "stop", label: "Stop-loss", color: "#e66767" },
];

function merge(o: Record<PlanOutcome, number>): Record<Shown, number> {
  return { t2: o.t2, t1: o.t1_then_time + o.t1_then_stop, time: o.time, stop: o.stop };
}

function OddsBlock({ title, sub, hold, plan, empty }: { title: string; sub: string; hold?: Odds; plan?: PlanOdds | null; empty?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] tracking-widest text-[#8391a7]">{title}</div>
      <div className="text-[11px] text-[#8391a7] mt-0.5 leading-snug min-h-[30px]">{sub}</div>
      {!hold ? <p className="text-[12px] text-[#94a3b8] mt-3">{empty}</p> : (
        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-[12px]">
          <dt className="text-[#94a3b8]">Chance of profit (hold)</dt>
          <dd className="text-right font-mono text-[#e2e8f0]">{Math.round(hold.p_profit * 100)}%</dd>
          <dt className="text-[#94a3b8]">Expected P&amp;L (hold)</dt>
          <dd className={cn("text-right font-mono font-semibold", pnlTone(hold.expected))}>{fmtRupees(hold.expected, true)}</dd>
          <dt className="text-[#94a3b8]">Likely range (10%–90%)</dt>
          <dd className="text-right font-mono text-[#cbd5e1]">{fmtRupees(hold.p10, true)} … {fmtRupees(hold.p90, true)}</dd>
          {plan && <>
            <dt className="text-[#94a3b8]">Reaches T1 (with the plan)</dt>
            <dd className="text-right font-mono text-[#e2e8f0]">{Math.round(plan.p_t1 * 100)}%</dd>
            <dt className="text-[#94a3b8]">Expected P&amp;L (with the plan)</dt>
            <dd className={cn("text-right font-mono font-semibold", pnlTone(plan.expected))}>{fmtRupees(plan.expected, true)}</dd>
          </>}
        </dl>
      )}
      {plan && <OutcomeBar outcomes={plan.outcomes} />}
    </div>
  );
}

function OutcomeBar({ outcomes }: { outcomes: Record<PlanOutcome, number> }) {
  const shares = merge(outcomes);
  const parts = SHOWN.filter(p => shares[p.key] > 0.005);
  return (
    <div className="mt-3">
      <div className="flex h-2.5 rounded overflow-hidden gap-[2px] bg-card" role="img"
           aria-label={"How the plan ended: " + parts.map(p => `${p.label} ${Math.round(shares[p.key] * 100)}%`).join(", ")}>
        {parts.map(p => <div key={p.key} style={{ width: `${shares[p.key] * 100}%`, background: p.color }} />)}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-[#94a3b8]">
        {parts.map(p => (
          <li key={p.key} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ background: p.color }} aria-hidden />
            {p.label} {Math.round(shares[p.key] * 100)}%
          </li>
        ))}
      </ul>
    </div>
  );
}

export function OddsPanel({ report }: { report: CheckReport }) {
  const h = report.history;
  const m = report.market!;
  const similar = h?.similar?.hold ? h.similar : null;
  const hv = similar ?? (h?.hold ? h : null);
  const histTitle = similar ? "HISTORY: SIMILAR SESSIONS" : "HISTORY: PAST SESSIONS";
  const histSub = hv
    ? `${similar ? `${similar.sessions} sessions like today (${similar.rule})` : `${h!.sessions} sessions`}${h?.from ? `, ${h.from} to ${h.to}` : ""}: how NIFTY really moved over the same stretch`
    : "";
  const hz = report.horizon!;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl p-5" aria-label="Chances and expected profit or loss">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
        <h3 className="text-sm font-semibold text-[#e2e8f0]">What your money can do</h3>
        <span className="text-[11px] text-[#8391a7]">
          {hz.starts_at_open ? "from the next open" : "from now"} to {hz.label} · after all charges
        </span>
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <OddsBlock title={histTitle} sub={histSub} hold={hv?.hold} plan={hv?.plan}
                   empty={h?.note ?? "History view needs saved sessions; it fills in as the recorder runs and the backfill completes."} />
        <OddsBlock title="MARKET VIEW" sub={`What the options market prices: NIFTY moves at ${(m.sigma * 100).toFixed(1)}% a year, no drift (${m.paths.toLocaleString("en-IN")} paths)`}
                   hold={m.hold} plan={m.plan} />
      </div>
      <p className="text-[11px] text-[#8391a7] mt-4 leading-relaxed">{report.evidence.why_market_view_loses}</p>
    </section>
  );
}
