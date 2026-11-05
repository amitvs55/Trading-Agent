"use client";
import { useState } from "react";
import { History, Loader2 } from "lucide-react";
import type { ReplaySignal, ReplayView } from "@/types/auth";
import { cn } from "@/lib/utils";
import { sendJson, useOptionsApi } from "@/lib/optionsApi";
import { EXIT_LABELS, fmtDate, fmtDateTime, fmtPremium, fmtR, fmtRupees } from "@/lib/optionsFormat";
import { Note, Panel } from "@/components/connectors/SideCards";

type NoteT = { tone: "ok" | "err"; text: string } | null;

const OUTCOME_LABELS: Record<string, string> = {
  SIGNAL: "Signals", NO_TRADE: "Blocked by a rule", GRADE_C: "Grade C (score below 60)", OVER_BUDGET: "Over budget",
};

const pnlTone = (v: number | null | undefined) =>
  v == null || Math.round(v) === 0 ? "text-[#94a3b8]" : v > 0 ? "text-[#93c5fd]" : "text-[#fca5a5]";

function daysAgo(n: number): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(Date.now() - n * 86_400_000));
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="bg-card border border-[#1e2d45] rounded-lg px-3 py-2 min-w-0">
      <div className="text-[9px] tracking-widest text-[#8391a7]">{label}</div>
      <div className={cn("font-mono text-[15px] font-semibold truncate", tone ?? "text-[#e2e8f0]")}>{value}</div>
    </div>
  );
}

function SignalRow({ s, label }: { s: ReplaySignal; label: string }) {
  const traded = s.fill != null && s.exit != null;
  return (
    <li className="py-2 flex items-start justify-between gap-3 text-[12px]">
      <div className="min-w-0">
        <div className="text-[10px] text-[#8391a7]">{fmtDateTime(s.created_at)} · {label} · grade {s.grade} ({Math.round(s.score)})
          {s.over_budget && <span className="text-yellow"> · over risk limit</span>}</div>
        <div className="font-mono text-[#e2e8f0] truncate">{s.action === "BUY_CE" ? "BUY CE" : "BUY PE"} {s.symbol}</div>
        <div className="text-[11px] text-[#94a3b8]">
          {traded ? <>₹{fmtPremium(s.fill)} → ₹{fmtPremium(s.exit)} · {EXIT_LABELS[s.exit_reason ?? ""] ?? s.exit_reason}</>
            : (EXIT_LABELS[s.exit_reason ?? s.state] ?? s.state).toString()}
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className={cn("font-mono font-semibold", pnlTone(s.pnl))}>{s.pnl != null ? fmtRupees(s.pnl, true) : "—"}</div>
        <div className="text-[10px] text-[#8391a7] font-mono">{fmtR(s.r)}</div>
      </div>
    </li>
  );
}

/** Replay recorded days through the live engine with today's rules: what it would have sent, and how it went. */
export function ReplayPanel() {
  const [from, setFrom] = useState(() => daysAgo(30));
  const [to, setTo] = useState(() => daysAgo(0));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<NoteT>(null);
  const { data, refresh } = useOptionsApi<ReplayView>("/api/admin/replay", 5_000);
  const r = data?.report;
  const active = r && (r.status === "queued" || r.status === "running") && !r.stalled;
  const labels = r?.setup_labels ?? {};

  async function start() {
    setBusy(true);
    setNote(null);
    try {
      const v = await sendJson<ReplayView>("/api/admin/replay", "POST", { from, to });
      void refresh(v, { revalidate: false });
      setNote({ tone: "ok", text: v.session_running
        ? "Queued. It runs on the recorder as soon as today's session ends, so it never slows the live engine."
        : "Queued. The recorder starts it within about 15 seconds." });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Couldn't start the replay" });
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1 block w-full bg-card border border-[#1e2d45] rounded-lg px-2.5 h-10 text-sm font-mono text-[#e2e8f0] outline-none focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]";
  const overall = r?.overall;
  return (
    <Panel icon={<History size={14} className="text-[#ff9933]" />} title="Replay recorded days"
           subtitle="Runs the saved market minute by minute through the live engine with today's rules, into a separate database: what it would have sent, and how those trades ended after all charges. Nothing here touches the live record.">
      <div className="grid grid-cols-2 sm:grid-cols-[1fr_1fr_auto] gap-3 items-end">
        <label className="text-[10px] tracking-widest text-[#8391a7] min-w-0">FROM
          <input type="date" value={from} onChange={e => setFrom(e.target.value)} min={data?.recorded.first ?? undefined}
                 max={to} className={field} /></label>
        <label className="text-[10px] tracking-widest text-[#8391a7] min-w-0">TO
          <input type="date" value={to} onChange={e => setTo(e.target.value)} min={from} max={daysAgo(0)} className={field} /></label>
        <button type="button" onClick={start} disabled={busy || !!active || !from || !to}
                className="col-span-2 sm:col-span-1 inline-flex items-center justify-center gap-2 h-10 rounded-lg px-4 text-sm font-semibold bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]">
          {busy && <Loader2 size={14} className="animate-spin" aria-hidden />} Run replay
        </button>
      </div>
      <p className="mt-2 text-[11px] text-[#8391a7]">
        {data?.recorded.days ? `${data.recorded.days} recorded session${data.recorded.days === 1 ? "" : "s"}, ${fmtDate(data.recorded.first)} to ${fmtDate(data.recorded.last)}.` : "No recorded sessions yet."}
      </p>
      <Note note={note} />

      <div className="mt-4" aria-live="polite">
        {!r || r.status === "none" ? <p className="text-[12px] text-[#94a3b8]">No replay run yet.</p>
          : r.status === "queued" ? <p className="text-[12px] text-[#c4b5fd]">Queued ({r.request?.from} to {r.request?.to}, {r.request?.days} session{r.request?.days === 1 ? "" : "s"})
              {data?.session_running ? ": waiting for today's session to end." : ": starting…"}</p>
          : r.status === "running" ? (
            <div>
              <p className={cn("text-[12px]", r.stalled ? "text-yellow" : "text-[#e2e8f0]")}>
                {r.stalled ? "The replay stopped reporting (the recorder may have restarted). Run it again."
                  : <>Replaying {r.current ? fmtDate(r.current) : "…"}: {r.done ?? 0} of {r.total ?? r.request?.days ?? "?"} sessions</>}
              </p>
              <div className="mt-2 h-1.5 rounded bg-card overflow-hidden" role="progressbar" aria-label="Replay progress"
                   aria-valuemin={0} aria-valuemax={r.total ?? 1} aria-valuenow={r.done ?? 0}>
                <div className="h-full bg-[#ff9933] transition-[width] duration-500" style={{ width: `${r.total ? ((r.done ?? 0) / r.total) * 100 : 3}%` }} />
              </div>
            </div>
          )
          : r.status === "error" || r.status === "stopped" ? (
            <p className="text-[12px] text-[#fca5a5]">Replay {r.status === "stopped" ? "stopped" : "failed"}: {r.error}</p>
          ) : (
            <div className="space-y-4">
              <p className="text-[11px] text-[#8391a7]">
                {r.request?.from} to {r.request?.to} · {r.days?.length ?? 0} session{r.days?.length === 1 ? "" : "s"} · run {fmtDateTime(r.finished_at)} by {r.request?.by}
                {r.rules ? ` · risk ${r.rules.risk_per_trade_pct}% of ${fmtRupees(r.rules.capital)}` : ""}
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <Stat label="SIGNALS" value={String(r.signals?.length ?? 0)} />
                <Stat label="WIN RATE" value={overall?.win_rate != null ? `${Math.round(overall.win_rate * 100)}% of ${overall.trades}` : "—"} />
                <Stat label="NET P&L" value={fmtRupees(overall?.total_rupees, true)} tone={pnlTone(overall?.total_rupees)} />
                <Stat label="PER TRADE" value={fmtRupees(overall?.expectancy_rupees, true)} tone={pnlTone(overall?.expectancy_rupees)} />
              </div>
              {r.decisions && (
                <div>
                  <div className="text-[11px] font-semibold text-[#e2e8f0]">Every candidate ({r.decisions.candidates})</div>
                  <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[#94a3b8]">
                    {Object.entries(r.decisions.by_outcome).map(([k, n]) => <li key={k}>{OUTCOME_LABELS[k] ?? k}: <span className="font-mono text-[#e2e8f0]">{n}</span></li>)}
                  </ul>
                  {r.decisions.reasons.length > 0 && (
                    <ul className="mt-2 space-y-1 text-[11px]">
                      {r.decisions.reasons.map(([why, n]) => (
                        <li key={why} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
                          <span className="text-[#94a3b8] truncate">{why}</span><span className="font-mono text-[#e2e8f0]">{n}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {r.by_setup && Object.keys(r.by_setup).length > 0 && (
                <ul className="text-[11px] space-y-1">
                  {Object.entries(r.by_setup).map(([setup, st]) => (
                    <li key={setup} className="flex justify-between gap-3">
                      <span className="text-[#94a3b8] truncate">{labels[setup] ?? setup}</span>
                      <span className="font-mono text-[#e2e8f0] whitespace-nowrap">{st.trades} trades · {st.win_rate != null ? `${Math.round(st.win_rate * 100)}%` : "—"} ·{" "}
                        <span className={pnlTone(st.total_rupees)}>{fmtRupees(st.total_rupees, true)}</span></span>
                    </li>
                  ))}
                </ul>
              )}
              {r.signals && r.signals.length > 0 ? (
                <ul className="divide-y divide-[#1e2d45] max-h-96 overflow-y-auto pr-1">
                  {[...r.signals].reverse().map(s => <SignalRow key={s.id} s={s} label={labels[s.setup] ?? s.setup} />)}
                </ul>
              ) : <p className="text-[12px] text-[#94a3b8]">No signal in this range with today&apos;s rules; the reasons above say why.</p>}
              {r.notes?.map(n => <p key={n} className="text-[10px] text-[#8391a7] leading-snug">{n}</p>)}
            </div>
          )}
      </div>
    </Panel>
  );
}
