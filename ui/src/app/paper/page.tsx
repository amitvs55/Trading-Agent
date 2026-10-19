"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Info, Loader2, RotateCcw, Wallet } from "lucide-react";
import type { PaperAccount, PaperTrade } from "@/types/options";
import type { CheckRow } from "@/types/check";
import { cn } from "@/lib/utils";
import { sendJson, useOptionsApi } from "@/lib/optionsApi";
import { EXIT_LABELS, fmtDateTime, fmtPremium, fmtR, fmtRupees } from "@/lib/optionsFormat";
import { useAuth } from "@/components/auth/AuthGate";
import { LiveAge } from "@/components/common/LiveAge";
import { PaperCurve } from "@/components/options/PaperChart";
import { DirectionPill, GradeBadge } from "@/components/options/StatusBits";

const pnlTone = (v: number | null | undefined) =>
  v == null || v === 0 ? "text-[#94a3b8]" : v > 0 ? "text-[#93c5fd]" : "text-[#fca5a5]";

function Tile({ label, value, sub, tone, loading }: { label: string; value: string; sub?: React.ReactNode; tone?: string; loading?: boolean }) {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl p-4 min-w-0">
      <div className="text-[10px] text-[#8391a7] tracking-widest mb-2">{label}</div>
      {loading ? <div className="skeleton h-8 rounded w-24" /> :
        <div className={cn("fade-in font-bold text-2xl leading-8 font-mono tabular-nums truncate", tone ?? "text-[#e2e8f0]")}>{value}</div>}
      {sub ? <div className="text-[11px] text-[#8391a7] mt-1 truncate">{sub}</div>
           : loading ? <div className="text-[11px] mt-1" aria-hidden>&nbsp;</div> : null}
    </div>
  );
}

function OpenRow({ t }: { t: PaperTrade }) {
  return (
    <tr className="hover:bg-[#ffffff04]">
      <td className="px-4 py-2"><DirectionPill action={t.action} /></td>
      <td className="px-2 py-2 whitespace-nowrap"><Link href={`/signals/${t.signal_id}`} className="font-mono text-[#e2e8f0] hover:text-[#ff9933]">{t.symbol}</Link>
        <div className="text-[10px] text-[#8391a7]">{t.signal_id} · {t.lots} lot ({t.units} qty)</div></td>
      <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{fmtPremium(t.entry)}<div className="text-[10px] text-[#8391a7]">{fmtDateTime(t.entry_at)}</div></td>
      <td className="px-2 py-2 text-right font-mono text-[#e2e8f0]">{t.bid != null ? fmtPremium(t.bid) : "—"}</td>
      <td className="px-2 py-2 text-right font-mono text-[#fca5a5]">{fmtPremium(t.stop)}</td>
      <td className="px-2 py-2 text-right font-mono text-[#93c5fd]">{fmtPremium(t.t1)} / {fmtPremium(t.t2)}</td>
      <td className={cn("px-4 py-2 text-right font-mono font-semibold", pnlTone(t.unrealised))}>{fmtRupees(t.unrealised, true)}</td>
    </tr>
  );
}

function ClosedRow({ t }: { t: PaperTrade }) {
  return (
    <tr className="hover:bg-[#ffffff04]">
      <td className="px-4 py-2 font-mono text-[#94a3b8] whitespace-nowrap">{fmtDateTime(t.exit_at)}</td>
      <td className="px-2 py-2 whitespace-nowrap"><Link href={`/signals/${t.signal_id}`} className="font-mono text-[#e2e8f0] hover:text-[#ff9933]">{t.symbol}</Link>
        <div className="text-[10px] text-[#8391a7]">{t.signal_id}</div></td>
      <td className="px-2 py-2"><GradeBadge grade={t.grade} score={t.score} /></td>
      <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{t.lots}</td>
      <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{fmtPremium(t.entry)} → {fmtPremium(t.exit)}</td>
      <td className="px-2 py-2 text-[#94a3b8] whitespace-nowrap">{t.exit_reason ? EXIT_LABELS[t.exit_reason] ?? t.exit_reason : "—"}</td>
      <td className="px-2 py-2 text-right font-mono text-[#8391a7]">{fmtRupees(t.charges)}</td>
      <td className={cn("px-2 py-2 text-right font-mono font-semibold", pnlTone(t.pnl))}>{fmtRupees(t.pnl, true)}</td>
      <td className="px-4 py-2 text-right font-mono text-[#94a3b8]">{fmtR(t.r)}</td>
    </tr>
  );
}

// Phones: one card per position or trade instead of a wide table
function OpenCard({ t }: { t: PaperTrade }) {
  return (
    <li>
      <Link href={`/signals/${t.signal_id}`} className="block px-4 py-3 active:bg-[#ffffff06]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2"><DirectionPill action={t.action} /><span className="text-[11px] text-[#8391a7]">{t.lots} lot · {t.units} qty</span></div>
            <div className="font-mono text-[13px] text-[#e2e8f0] truncate mt-1">{t.symbol}</div>
          </div>
          <div className="text-right flex-shrink-0">
            <div className={cn("font-mono font-bold text-base", pnlTone(t.unrealised))}>{fmtRupees(t.unrealised, true)}</div>
            <div className="text-[10px] text-[#8391a7]">open P&amp;L</div>
          </div>
        </div>
        <dl className="grid grid-cols-4 gap-2 mt-2.5 text-[11px]">
          {([["Entry", fmtPremium(t.entry), "text-[#e2e8f0]"], ["Bid", t.bid != null ? fmtPremium(t.bid) : "—", "text-[#e2e8f0]"],
             ["Stop", fmtPremium(t.stop), "text-[#fca5a5]"], ["T1", fmtPremium(t.t1), "text-[#93c5fd]"]] as const).map(([k, v, tone]) => (
            <div key={k}><dt className="text-[10px] text-[#8391a7]">{k}</dt><dd className={cn("font-mono", tone)}>{v}</dd></div>
          ))}
        </dl>
      </Link>
    </li>
  );
}

function ClosedCard({ t }: { t: PaperTrade }) {
  return (
    <li>
      <Link href={`/signals/${t.signal_id}`} className="flex items-start justify-between gap-3 px-4 py-3 active:bg-[#ffffff06]">
        <div className="min-w-0">
          <div className="text-[11px] text-[#8391a7]">{fmtDateTime(t.exit_at)} · <span className="font-mono">{t.signal_id}</span></div>
          <div className="font-mono text-[13px] text-[#e2e8f0] truncate mt-0.5">{t.symbol}</div>
          <div className="text-[11px] text-[#94a3b8] mt-1">
            <span className="font-mono">{fmtPremium(t.entry)} → {fmtPremium(t.exit)}</span> · {t.exit_reason ? EXIT_LABELS[t.exit_reason] ?? t.exit_reason : "—"}
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className={cn("font-mono font-semibold text-sm", pnlTone(t.pnl))}>{fmtRupees(t.pnl, true)}</div>
          <div className="font-mono text-[11px] text-[#94a3b8]">{fmtR(t.r)}</div>
          <div className="mt-1"><GradeBadge grade={t.grade} score={t.score} /></div>
        </div>
      </Link>
    </li>
  );
}

function ResetForm({ acct, onDone }: { acct: PaperAccount; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [balance, setBalance] = useState(String(acct.settings.starting_balance));
  const [follow, setFollow] = useState(acct.settings.follow);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sendJson("/api/admin/paper", "PUT", { reset: true, starting_balance: Number(balance), follow });
      setOpen(false);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
              className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] hover:border-[#2d3e58] transition-colors">
        <RotateCcw size={12} /> Reset account
      </button>
    );
  }
  return (
    <form onSubmit={submit} className="menu-pop w-full sm:w-auto flex flex-wrap items-end gap-2 bg-surface border border-[#1e2d45] rounded-xl p-3">
      <label className="text-[10px] tracking-widest text-[#8391a7]">STARTING BALANCE (₹)
        <input value={balance} onChange={e => setBalance(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric"
               className="mt-1 block w-32 bg-card border border-[#1e2d45] focus:border-[#ff9933] rounded-lg px-2.5 py-1.5 text-sm font-mono text-[#e2e8f0] outline-none" />
      </label>
      <label className="text-[10px] tracking-widest text-[#8391a7]">FOLLOW
        <select value={follow} onChange={e => setFollow(e.target.value as "all" | "A")}
                className="mt-1 block bg-card border border-[#1e2d45] focus:border-[#ff9933] rounded-lg px-2.5 py-1.5 text-sm text-[#e2e8f0] outline-none">
          <option value="all">Every signal</option><option value="A">Grade A only</option>
        </select>
      </label>
      <button type="submit" disabled={busy || Number(balance) < 10_000}
              className="flex items-center gap-1.5 bg-[#ff9933] hover:bg-[#ffa94d] disabled:opacity-50 text-[#0b0f1a] rounded-lg px-3 py-2 text-xs font-semibold">
        {busy && <Loader2 size={12} className="animate-spin" />} Start fresh from now
      </button>
      <button type="button" onClick={() => setOpen(false)} className="px-2 py-2 text-xs text-[#8391a7] hover:text-[#e2e8f0]">Cancel</button>
      {error && <p className="basis-full text-[11px] text-[#fca5a5]">{error}</p>}
      <p className="basis-full text-[10px] text-[#8391a7]">Past signals stay in the track record; the paper account just counts from now.</p>
    </form>
  );
}

/** Trades followed from Option Check: kept apart from the signal account above (not in its balance). */
function CheckTrades() {
  const { data } = useOptionsApi<{ trades: CheckRow[] }>("/api/options/checks/paper", 30_000);
  const trades = data?.trades ?? [];
  if (data && !trades.length) return null;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden mt-5" aria-label="Followed from Option Check">
      <div className="px-4 py-3 border-b border-[#1e2d45]">
        <span className="text-xs font-semibold text-[#e2e8f0]">Followed from Option Check</span>
        <span className="text-[10px] text-[#8391a7] ml-2">separate from the signal account above</span>
      </div>
      <ul className="divide-y divide-[#1e2d45]">
        {!data ? <li className="px-4 py-3"><div className="skeleton h-10 rounded" /></li> : trades.map(t => {
          const p = t.paper!;
          return (
            <li key={t.id} className="px-4 py-2.5 flex flex-wrap items-center justify-between gap-2 text-[12px]">
              <div className="min-w-0">
                <Link href={`/check?id=${t.id}`} className="font-mono text-[#e2e8f0] hover:text-[#ff9933]">{t.symbol}</Link>
                <div className="text-[10px] text-[#8391a7]">{p.units} qty from ₹{fmtPremium(p.entry)} · checked {fmtDateTime(t.created_at)}
                  {t.summary?.verdict ? ` · said ${t.summary.verdict.toLowerCase()}` : ""}</div>
              </div>
              <div className="text-right">
                {p.closed_at ? <><span className={cn("font-mono font-semibold", pnlTone(p.pnl))}>{fmtRupees(p.pnl, true)}</span>
                                 <div className="text-[10px] text-[#8391a7]">closed at ₹{fmtPremium(p.exit)}</div></>
                  : <span className="text-[11px] text-[#60a5fa]">open · live on its check page</span>}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function PaperPage() {
  const auth = useAuth();
  const { data: a, refresh } = useOptionsApi<PaperAccount>("/api/paper", 5_000);
  const loading = !a;
  const start = a?.settings.starting_balance ?? 100_000;

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><Wallet size={20} className="text-[#ff9933]" /> Paper trading</h1>
          <p className="text-sm text-[#8391a7] mt-1">
            A virtual {a ? fmtRupees(start) : "₹1,00,000"} account that takes {a ? a.settings.follow_label.toLowerCase() : "every signal"} automatically,
            sized by your risk rules, on live prices.
          </p>
        </div>
        {a ? auth?.user?.role === "admin" && <ResetForm acct={a} onDone={() => refresh()} />
          : <div className="h-[34px] w-[132px] rounded-lg skeleton hidden [.role-admin_&]:block" aria-hidden />}
      </div>

      <div className="mb-5 flex items-start gap-2.5 bg-[#3987e50d] border border-[#3987e533] rounded-xl px-4 py-3 text-[12px] text-[#94a3b8] leading-relaxed">
        <Info size={14} className="text-[#60a5fa] mt-0.5 flex-shrink-0" />
        <span>
          Each position opens when its signal&apos;s entry fills (at the live ask) and closes on the signal&apos;s own exits (at the live bid), with
          all charges. Size comes from this account&apos;s balance at your {a ? `${a.rules.risk_per_trade_pct}%` : "3%"} risk per trade
          (at most {a?.rules.max_lots ?? 1} lot, like the signals); after a {a ? `${a.rules.daily_loss_stop_pct}%` : "10%"} loss in a day it
          takes no new trades until the next day.
        </span>
      </div>
      {/* Changing values sit on their own fixed-height line, so the banner above never re-wraps as they load */}
      <p className="-mt-3 mb-5 h-4 text-[11px] text-[#8391a7] truncate">
        Running since {a ? fmtDateTime(a.settings.started_at) : "…"} · updated <LiveAge iso={a?.as_of} never="…" />
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 mb-5">
        <Tile loading={loading} label="EQUITY" value={fmtRupees(a?.equity)} tone={pnlTone((a?.equity ?? start) - start)}
              sub={a ? `${a.return_pct >= 0 ? "+" : ""}${a.return_pct.toFixed(2)}% since start` : undefined} />
        <Tile loading={loading} label="TODAY" value={fmtRupees(a?.today.pnl, true)} tone={pnlTone(a?.today.pnl)}
              sub={a ? (a.today.daily_stop_hit ? "daily stop hit: no new trades today" : `stop at −${fmtRupees(a.today.daily_stop)}`) : undefined} />
        <Tile loading={loading} label="OPEN P&L" value={fmtRupees(a?.unrealised, true)} tone={pnlTone(a?.unrealised)}
              sub={a ? `${a.open.length} open position${a.open.length === 1 ? "" : "s"}` : undefined} />
        <Tile loading={loading} label="REALISED" value={fmtRupees(a?.realised, true)} tone={pnlTone(a?.realised)} sub="after all charges" />
        <Tile loading={loading} label="CASH FREE" value={fmtRupees(a?.cash)} sub={a ? `${fmtRupees(a.invested)} in positions` : undefined} />
        <Tile loading={loading} label="WIN RATE" value={a?.stats.win_rate != null ? `${(a.stats.win_rate * 100).toFixed(0)}%` : "—"}
              sub={a ? `${a.stats.wins} of ${a.stats.trades} trades` : undefined} />
        <Tile loading={loading} label="MAX DRAWDOWN" value={fmtRupees(a?.stats.max_drawdown)}
              sub={a ? `${a.stats.max_drawdown_pct.toFixed(1)}% from peak` : undefined} />
      </div>

      <div className="grid gap-5 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] mb-5">
        <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden min-w-0">
          <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
            <span className="text-xs font-semibold text-[#e2e8f0]">Balance</span>
            <span className="text-[10px] text-[#8391a7]">₹ after each closed trade · dashed line = starting balance</span>
          </div>
          <div className="p-3">
            {!a ? <div className="skeleton h-64 rounded-lg" /> : a.curve.length > 1 ? <PaperCurve curve={a.curve} start={start} /> :
              <div className="h-64 grid place-items-center text-xs text-[#8391a7] text-center px-6">The curve starts with the first closed paper trade.<br />Signals run from 09:30 on trading days.</div>}
          </div>
        </section>
        <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden min-w-0">
          <div className="px-4 py-3 border-b border-[#1e2d45] text-xs font-semibold text-[#e2e8f0]">Skipped entries</div>
          {!a ? <div className="p-4"><div className="skeleton h-16 rounded" /></div> : a.skipped.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-[#8391a7]">None. Every followed signal that filled was taken.</div>
          ) : (
            <ul className="divide-y divide-[#1e2d45] max-h-64 overflow-y-auto">
              {a.skipped.map(s => (
                <li key={s.signal_id} className="px-4 py-2 text-[12px]">
                  <Link href={`/signals/${s.signal_id}`} className="font-mono text-[#ff9933] hover:underline">{s.signal_id}</Link>
                  <span className="text-[#8391a7]"> · {fmtDateTime(s.at)}</span>
                  <div className="text-[#94a3b8]">{s.reason}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden mb-5">
        <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
          <span className="text-xs font-semibold text-[#e2e8f0]">Open positions</span>
          <span className="text-[10px] text-[#8391a7]">marked to the live bid · updates every 5s</span>
        </div>
        <ul className="md:hidden divide-y divide-[#1e2d45]">
          {!a ? <li className="px-4 py-3"><div className="skeleton h-14 rounded" /></li> :
            a.open.length ? a.open.map(t => <OpenCard key={t.signal_id} t={t} />) :
            <li className="px-4 py-8 text-center text-xs text-[#8391a7]">No open position.</li>}
        </ul>
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-[12px] tabular-nums">
            <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
              <th className="px-4 py-2 font-medium">SIDE</th><th className="px-2 py-2 font-medium">CONTRACT</th>
              <th className="px-2 py-2 font-medium text-right">ENTRY</th><th className="px-2 py-2 font-medium text-right">BID NOW</th>
              <th className="px-2 py-2 font-medium text-right">STOP</th><th className="px-2 py-2 font-medium text-right">T1 / T2</th>
              <th className="px-4 py-2 font-medium text-right">OPEN P&amp;L</th>
            </tr></thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {!a ? <tr><td colSpan={7} className="px-4 py-3"><div className="skeleton h-4 rounded" /></td></tr> :
                a.open.length ? a.open.map(t => <OpenRow key={t.signal_id} t={t} />) :
                <tr><td colSpan={7} className="px-4 py-8 text-center text-xs text-[#8391a7]">No open position.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between">
          <span className="text-xs font-semibold text-[#e2e8f0]">Closed trades <span className="text-[#8391a7] font-normal">({a?.trades.length ?? 0})</span></span>
          {a && a.stats.best != null && <span className="text-[10px] text-[#8391a7]">best {fmtRupees(a.stats.best, true)} · worst {fmtRupees(a.stats.worst, true)}</span>}
        </div>
        <ul className="lg:hidden divide-y divide-[#1e2d45]">
          {!a ? <li className="px-4 py-3"><div className="skeleton h-14 rounded" /></li> :
            a.trades.length ? a.trades.map(t => <ClosedCard key={t.signal_id} t={t} />) :
            <li className="px-4 py-8 text-center text-xs text-[#8391a7]">No closed paper trade yet.</li>}
        </ul>
        <div className="hidden lg:block overflow-x-auto">
          <table className="w-full text-[12px] tabular-nums">
            <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
              <th className="px-4 py-2 font-medium">CLOSED</th><th className="px-2 py-2 font-medium">CONTRACT</th>
              <th className="px-2 py-2 font-medium">GRADE</th><th className="px-2 py-2 font-medium text-right">LOTS</th>
              <th className="px-2 py-2 font-medium text-right">ENTRY → EXIT</th><th className="px-2 py-2 font-medium">REASON</th>
              <th className="px-2 py-2 font-medium text-right">CHARGES</th><th className="px-2 py-2 font-medium text-right">NET</th>
              <th className="px-4 py-2 font-medium text-right">R</th>
            </tr></thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {!a ? <tr><td colSpan={9} className="px-4 py-3"><div className="skeleton h-4 rounded" /></td></tr> :
                a.trades.length ? a.trades.map(t => <ClosedRow key={t.signal_id} t={t} />) :
                <tr><td colSpan={9} className="px-4 py-8 text-center text-xs text-[#8391a7]">No closed paper trade yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <CheckTrades />
      <p className="text-[10px] text-[#8391a7] mt-3">Paper results are simulated on live quotes and don&apos;t guarantee live results.</p>
    </main>
  );
}
