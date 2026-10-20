"use client";
import { Fragment, useEffect, useState, type FormEvent } from "react";
import { ChevronDown, Loader2, X } from "lucide-react";
import type { Desk, DeskOrder, DeskPosition, DeskTrade } from "@/types/desk";
import { sendJson } from "@/lib/optionsApi";
import { useLiveIndices } from "@/lib/liveIndices";
import { fmtDate, fmtDateTime, fmtPremium, fmtRupees, fmtTime } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";
import { pnlTone } from "@/components/check/Money";

const STATUS_TONE: Record<string, string> = {
  FILLED: "text-[#93c5fd] border-[#3987e544] bg-[#3987e514]",
  OPEN: "text-[#fcd34d] border-[#f59e0b44] bg-[#f59e0b14]",
  TRIGGERED: "text-[#fcd34d] border-[#f59e0b44] bg-[#f59e0b14]",
  AMO: "text-[#c4b5fd] border-[#a78bfa44] bg-[#a78bfa14]",
  PENDING: "text-[#cbd5e1] border-[#47556966] bg-[#4755691a]",
  CANCELLED: "text-[#94a3b8] border-[#1e2d45] bg-card",
  REJECTED: "text-[#fca5a5] border-[#ef444444] bg-[#ef444414]",
};

function Pill({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-bold tracking-wide whitespace-nowrap", className)}>{children}</span>;
}

function SidePill({ side }: { side: "BUY" | "SELL" }) {
  return <Pill className={side === "BUY" ? "text-green border-[#22c55e44] bg-[#22c55e14]" : "text-red border-[#ef444444] bg-[#ef444414]"}>{side}</Pill>;
}

/** Positions marked to the live stream when it has the contract, else to the server's last mark. */
function useLiveMarks(positions: DeskPosition[]) {
  const levels = useLiveIndices().levels;
  return positions.map(p => {
    const lvl = levels[p.symbol];
    const ltp = lvl?.kind === "option" && lvl.ltp != null ? lvl.ltp : p.ltp;
    const pnl = p.open && ltp != null && p.avg != null ? (ltp - p.avg) * p.qty : p.pnl;
    return { ...p, ltp, pnl, pnl_pct: pnl != null && p.invested ? (pnl / p.invested) * 100 : p.pnl_pct, live: lvl?.kind === "option" };
  });
}

export function liveOpenPnl(desk: Desk | undefined, marked: ReturnType<typeof useLiveMarks>): number | null {
  if (!desk) return null;
  return marked.filter(p => p.open).reduce((s, p) => s + (p.pnl ?? 0), 0);
}

function ExitButton({ p, onDone }: { p: DeskPosition; onDone: () => void }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);
  async function go() {
    if (!armed) { setArmed(true); return; }
    setBusy(true);
    setError(null);
    try {
      await sendJson("/api/desk/positions/exit", "POST", { token: p.token, product: p.product });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Exit failed");
    } finally {
      setBusy(false);
      setArmed(false);
    }
  }
  return (
    <span className="inline-flex flex-col items-end">
      <button type="button" onClick={go} disabled={busy}
              className={cn("h-7 px-2.5 rounded-md border text-[11px] font-semibold inline-flex items-center gap-1 whitespace-nowrap transition-colors",
                armed ? "bg-[#dc2626] border-[#dc2626] text-white" : "border-[#ef444466] text-[#f87171] hover:bg-[#ef44441a]")}>
        {busy && <Loader2 size={11} className="animate-spin" aria-hidden />}{armed ? "Confirm exit" : "Exit"}
      </button>
      {error && <span role="alert" className="text-[10px] text-[#fca5a5] mt-1 max-w-[180px] text-right">{error}</span>}
    </span>
  );
}

function Contract({ symbol, expiry, product }: { symbol: string; expiry: string | null; product: string }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[12.5px] text-[#e2e8f0] truncate">{symbol}</div>
      <div className="text-[10px] text-[#8391a7]">{product}{expiry ? ` · expires ${fmtDate(expiry)}` : ""}</div>
    </div>
  );
}

export function PositionsPanel({ desk, onChange }: { desk: Desk; onChange: () => void }) {
  const rows = useLiveMarks(desk.positions);
  if (!rows.length) return <Empty text="No positions today. Place an order from the ticket to start." />;
  return (
    <>
      <ul className="md:hidden divide-y divide-[#1e2d45]">
        {rows.map(p => (
          <li key={`${p.token}-${p.product}`} className={cn("px-4 py-3", !p.open && "opacity-70")}>
            <div className="flex items-start justify-between gap-3">
              <Contract symbol={p.symbol} expiry={p.expiry} product={p.product_label} />
              <div className="text-right flex-shrink-0">
                <div className={cn("font-mono font-bold text-[15px]", pnlTone(p.open ? p.pnl : p.realised_today))}>
                  {fmtRupees(p.open ? p.pnl : p.realised_today, true)}</div>
                <div className="text-[10px] text-[#8391a7]">{p.open ? (p.pnl_pct != null ? `${p.pnl_pct >= 0 ? "+" : ""}${p.pnl_pct.toFixed(1)}% · open` : "open") : "closed · after charges"}</div>
              </div>
            </div>
            <div className="mt-2 flex items-end justify-between gap-3">
              <dl className="grid grid-cols-3 gap-3 text-[11px]">
                <div><dt className="text-[10px] text-[#8391a7]">Qty</dt><dd className="font-mono text-[#e2e8f0]">{p.qty}</dd></div>
                <div><dt className="text-[10px] text-[#8391a7]">Avg</dt><dd className="font-mono text-[#e2e8f0]">{p.avg != null ? fmtPremium(p.avg) : "—"}</dd></div>
                <div><dt className="text-[10px] text-[#8391a7]">LTP</dt><dd className="font-mono text-[#e2e8f0]">{p.ltp != null ? fmtPremium(p.ltp) : "—"}</dd></div>
              </dl>
              {p.open && <ExitButton p={p} onDone={onChange} />}
            </div>
          </li>
        ))}
      </ul>
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-[12px] tabular-nums">
          <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
            <th className="px-4 py-2 font-medium">CONTRACT</th><th className="px-2 py-2 font-medium text-right">QTY</th>
            <th className="px-2 py-2 font-medium text-right">AVG</th><th className="px-2 py-2 font-medium text-right">LTP</th>
            <th className="px-2 py-2 font-medium text-right">P&amp;L</th><th className="px-2 py-2 font-medium text-right">REALISED TODAY</th>
            <th className="px-4 py-2 font-medium text-right"><span className="sr-only">Exit</span></th>
          </tr></thead>
          <tbody className="divide-y divide-[#1e2d45]">
            {rows.map(p => (
              <tr key={`${p.token}-${p.product}`} className={cn("hover:bg-[#ffffff04]", !p.open && "opacity-70")}>
                <td className="px-4 py-2.5"><Contract symbol={p.symbol} expiry={p.expiry} product={p.product_label} /></td>
                <td className="px-2 py-2.5 text-right font-mono text-[#e2e8f0]">{p.qty}<div className="text-[10px] text-[#8391a7]">{p.lots} lot{p.lots === 1 ? "" : "s"}</div></td>
                <td className="px-2 py-2.5 text-right font-mono text-[#94a3b8]">{p.avg != null ? fmtPremium(p.avg) : "—"}</td>
                <td className="px-2 py-2.5 text-right font-mono text-[#e2e8f0]">{p.ltp != null ? fmtPremium(p.ltp) : "—"}
                  {p.live && p.open && <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-green align-middle" title="live" aria-label="live" />}</td>
                <td className={cn("px-2 py-2.5 text-right font-mono font-semibold", pnlTone(p.pnl))}>
                  {p.open ? fmtRupees(p.pnl, true) : "—"}
                  {p.open && p.pnl_pct != null && <div className="text-[10px] font-normal">{p.pnl_pct >= 0 ? "+" : ""}{p.pnl_pct.toFixed(1)}%</div>}
                </td>
                <td className={cn("px-2 py-2.5 text-right font-mono", pnlTone(p.realised_today))}>{p.realised_today ? fmtRupees(p.realised_today, true) : "—"}</td>
                <td className="px-4 py-2.5 text-right">{p.open && <ExitButton p={p} onDone={onChange} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-4 py-2 text-[10px] text-[#8391a7] border-t border-[#1e2d45]">
        Open P&amp;L is at the last traded price, before the sell&apos;s charges. Exit sells at the live bid.
      </p>
    </>
  );
}

function priceText(o: DeskOrder): string {
  if (o.order_type === "MARKET") return "Market";
  if (o.order_type === "LIMIT") return `₹${fmtPremium(o.price)}`;
  if (o.order_type === "SL") return `₹${fmtPremium(o.price)} · trg ₹${fmtPremium(o.trigger_price)}`;
  return `trg ₹${fmtPremium(o.trigger_price)}`;
}

function ModifyForm({ o, onDone, onCancel }: { o: DeskOrder; onDone: () => void; onCancel: () => void }) {
  const [lots, setLots] = useState(String(o.lots));
  const [price, setPrice] = useState(o.price != null ? o.price.toFixed(2) : "");
  const [trigger, setTrigger] = useState(o.trigger_price != null ? o.trigger_price.toFixed(2) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sendJson(`/api/desk/orders/${o.id}`, "PATCH", {
        lots: Number(lots) || undefined,
        price: o.order_type === "LIMIT" || o.order_type === "SL" ? Number(price) || undefined : undefined,
        trigger_price: (o.order_type === "SL" || o.order_type === "SL-M") && o.status !== "TRIGGERED" ? Number(trigger) || undefined : undefined,
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Didn't work");
    } finally {
      setBusy(false);
    }
  }
  const field = "mt-1 block w-24 bg-card border border-[#1e2d45] focus:border-[#ff9933] rounded-md px-2 h-8 text-[12px] font-mono text-[#e2e8f0] outline-none";
  return (
    <form onSubmit={submit} className="menu-pop flex flex-wrap items-end gap-2 bg-surface border border-[#1e2d45] rounded-lg p-2.5">
      <label className="text-[10px] tracking-widest text-[#8391a7]">LOTS<input value={lots} inputMode="numeric" onChange={e => setLots(e.target.value.replace(/\D/g, ""))} className={field} /></label>
      {(o.order_type === "LIMIT" || o.order_type === "SL") &&
        <label className="text-[10px] tracking-widest text-[#8391a7]">PRICE<input value={price} inputMode="decimal" onChange={e => setPrice(e.target.value.replace(/[^0-9.]/g, ""))} className={field} /></label>}
      {(o.order_type === "SL" || o.order_type === "SL-M") && o.status !== "TRIGGERED" &&
        <label className="text-[10px] tracking-widest text-[#8391a7]">TRIGGER<input value={trigger} inputMode="decimal" onChange={e => setTrigger(e.target.value.replace(/[^0-9.]/g, ""))} className={field} /></label>}
      <button type="submit" disabled={busy} className="h-8 px-3 rounded-md bg-[#ff9933] text-[#0b0f1a] text-[12px] font-semibold disabled:opacity-50 inline-flex items-center gap-1">
        {busy && <Loader2 size={12} className="animate-spin" aria-hidden />} Save</button>
      <button type="button" onClick={onCancel} className="h-8 px-2 text-[12px] text-[#8391a7] hover:text-[#e2e8f0]">Back</button>
      {error && <p role="alert" className="basis-full text-[11px] text-[#fca5a5]">{error}</p>}
    </form>
  );
}

function OrderActions({ o, onChange }: { o: DeskOrder; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!o.active) return null;
  if (editing) return <ModifyForm o={o} onDone={() => { setEditing(false); onChange(); }} onCancel={() => setEditing(false)} />;
  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await sendJson(`/api/desk/orders/${o.id}/cancel`, "POST", {});
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="inline-flex items-center gap-1.5 flex-wrap justify-end">
      {o.status !== "PENDING" && o.order_type !== "MARKET" &&
        <button type="button" onClick={() => setEditing(true)} className="h-7 px-2.5 rounded-md border border-[#1e2d45] text-[11px] text-[#cbd5e1] hover:border-[#ff993366] hover:text-[#ff9933]">Modify</button>}
      <button type="button" onClick={cancel} disabled={busy}
              className="h-7 px-2.5 rounded-md border border-[#1e2d45] text-[11px] text-[#cbd5e1] hover:border-[#ef444466] hover:text-[#f87171] inline-flex items-center gap-1">
        {busy ? <Loader2 size={11} className="animate-spin" aria-hidden /> : <X size={11} aria-hidden />} Cancel</button>
      {error && <span role="alert" className="basis-full text-right text-[10px] text-[#fca5a5]">{error}</span>}
    </span>
  );
}

export function OrdersPanel({ desk, onChange }: { desk: Desk; onChange: () => void }) {
  const [all, setAll] = useState(false);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(desk.as_of));
  const shown = desk.orders.filter(o => all || o.active || o.created_at.slice(0, 10) === today || (o.filled_at ?? "").slice(0, 10) === today);
  const older = desk.orders.length - shown.length;
  return (
    <>
      {!shown.length ? <Empty text={older ? "No orders today." : "No orders yet."} /> : (
        <ul className="divide-y divide-[#1e2d45]">
          {shown.map(o => (
            <li key={o.id} className="px-4 py-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <SidePill side={o.side} />
                  <Pill className={STATUS_TONE[o.status]}>{o.status_label.toUpperCase()}</Pill>
                  <span className="text-[10px] text-[#8391a7]">{o.order_type} · {o.product_label} · {fmtDateTime(o.created_at)}</span>
                </div>
                <div className="mt-1 font-mono text-[12.5px] text-[#e2e8f0] truncate">{o.symbol}</div>
                <div className="text-[11px] text-[#94a3b8] mt-0.5">
                  {o.qty} qty ({o.lots} lot{o.lots === 1 ? "" : "s"}) · {priceText(o)}
                  {o.status === "FILLED" && <> · filled <span className="font-mono text-[#e2e8f0]">₹{fmtPremium(o.fill_price)}</span> at {fmtTime(o.filled_at)} ({o.fill_source}) · charges ₹{fmtPremium(o.charges?.total)}</>}
                  {o.active && o.block ? <> · holds {fmtRupees(o.block)}</> : null}
                </div>
                {o.reason && <div className={cn("text-[11px] mt-0.5", o.status === "REJECTED" ? "text-[#fca5a5]" : "text-[#8391a7]")}>{o.reason}</div>}
              </div>
              <OrderActions o={o} onChange={onChange} />
            </li>
          ))}
        </ul>
      )}
      {(older > 0 || all) && (
        <div className="px-4 py-2 border-t border-[#1e2d45]">
          <button type="button" onClick={() => setAll(a => !a)} className="text-[11px] text-[#ff9933] hover:underline">
            {all ? "Show today's only" : `Show ${older} older order${older === 1 ? "" : "s"}`}</button>
        </div>
      )}
    </>
  );
}

const PARTS: [keyof DeskTrade["charges_detail"], string][] = [
  ["brokerage", "Brokerage"], ["stt", "STT"], ["exchange", "Exchange"], ["sebi", "SEBI"], ["stamp", "Stamp"], ["gst", "GST"],
];

function ChargesLine({ c }: { c: DeskTrade["charges_detail"] }) {
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-[#8391a7]">
      {PARTS.map(([k, label]) => <span key={k}>{label} <span className="font-mono text-[#94a3b8]">₹{fmtPremium(c[k] as number)}</span></span>)}
    </span>
  );
}

export function TradesPanel({ desk }: { desk: Desk }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!desk.trades.length) return <Empty text="No closed trades yet. Every sell, square-off and expiry settlement shows here with its charges." />;
  return (
    <>
      <ul className="lg:hidden divide-y divide-[#1e2d45]">
        {desk.trades.map(t => (
          <li key={t.id} className="px-4 py-3">
            <button type="button" onClick={() => setOpen(o => (o === t.id ? null : t.id))} aria-expanded={open === t.id}
                    className="w-full flex items-start justify-between gap-3 text-left">
              <div className="min-w-0">
                <div className="text-[10px] text-[#8391a7]">{fmtDateTime(t.exit_at)} · {t.reason}</div>
                <div className="font-mono text-[12.5px] text-[#e2e8f0] truncate mt-0.5">{t.symbol}</div>
                <div className="text-[11px] text-[#94a3b8] mt-0.5 font-mono">{t.qty} qty · {fmtPremium(t.entry)} → {fmtPremium(t.exit)}</div>
              </div>
              <div className="text-right flex-shrink-0">
                <div className={cn("font-mono font-semibold text-sm", pnlTone(t.net))}>{fmtRupees(t.net, true)}</div>
                <div className="text-[10px] text-[#8391a7] inline-flex items-center gap-0.5">charges ₹{fmtPremium(t.charges)}
                  <ChevronDown size={11} className={cn("transition-transform", open === t.id && "rotate-180")} aria-hidden /></div>
              </div>
            </button>
            {open === t.id && <div className="mt-2"><ChargesLine c={t.charges_detail} /></div>}
          </li>
        ))}
      </ul>
      <div className="hidden lg:block overflow-x-auto">
        <table className="w-full text-[12px] tabular-nums">
          <thead><tr className="text-[10px] tracking-widest text-[#8391a7] text-left">
            <th className="px-4 py-2 font-medium">CLOSED</th><th className="px-2 py-2 font-medium">CONTRACT</th>
            <th className="px-2 py-2 font-medium text-right">QTY</th><th className="px-2 py-2 font-medium text-right">BUY AVG → SELL</th>
            <th className="px-2 py-2 font-medium">HOW</th><th className="px-2 py-2 font-medium text-right">GROSS</th>
            <th className="px-2 py-2 font-medium text-right">CHARGES</th><th className="px-4 py-2 font-medium text-right">NET</th>
          </tr></thead>
          <tbody className="divide-y divide-[#1e2d45]">
            {desk.trades.map(t => (
              <Fragment key={t.id}>
                <tr className="hover:bg-[#ffffff04] cursor-pointer" onClick={() => setOpen(o => (o === t.id ? null : t.id))}>
                  <td className="px-4 py-2 font-mono text-[#94a3b8] whitespace-nowrap">{fmtDateTime(t.exit_at)}</td>
                  <td className="px-2 py-2"><Contract symbol={t.symbol} expiry={null} product={t.product === "MIS" ? "Intraday" : "Carry"} /></td>
                  <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{t.qty}</td>
                  <td className="px-2 py-2 text-right font-mono text-[#94a3b8] whitespace-nowrap">{fmtPremium(t.entry)} → {fmtPremium(t.exit)}</td>
                  <td className="px-2 py-2 text-[#94a3b8] whitespace-nowrap">{t.reason}</td>
                  <td className={cn("px-2 py-2 text-right font-mono", pnlTone(t.gross))}>{fmtRupees(t.gross, true)}</td>
                  <td className="px-2 py-2 text-right font-mono text-[#8391a7]">
                    <button type="button" aria-expanded={open === t.id} aria-label={`Charges ₹${fmtPremium(t.charges)}: show the breakdown`}
                            className="inline-flex items-center gap-0.5 hover:text-[#e2e8f0]"
                            onClick={e => { e.stopPropagation(); setOpen(o => (o === t.id ? null : t.id)); }}>
                      ₹{fmtPremium(t.charges)} <ChevronDown size={11} className={cn("transition-transform", open === t.id && "rotate-180")} aria-hidden />
                    </button>
                  </td>
                  <td className={cn("px-4 py-2 text-right font-mono font-semibold", pnlTone(t.net))}>{fmtRupees(t.net, true)}
                    {t.net_pct != null && <div className="text-[10px] font-normal">{t.net_pct >= 0 ? "+" : ""}{t.net_pct.toFixed(1)}%</div>}</td>
                </tr>
                {open === t.id && <tr><td colSpan={8} className="px-4 pb-2.5 pt-0"><ChargesLine c={t.charges_detail} /></td></tr>}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function DaysPanel({ desk }: { desk: Desk }) {
  if (!desk.days.length) return <Empty text="Your P&L by day appears after the first closed trade." />;
  const max = Math.max(...desk.days.map(d => Math.abs(d.net)), 1);
  return (
    <ul className="divide-y divide-[#1e2d45]">
      {desk.days.map(d => (
        <li key={d.day} className="px-4 py-2.5 grid grid-cols-[88px_minmax(0,1fr)_auto] items-center gap-3 text-[12px]">
          <span className="text-[#94a3b8]">{fmtDate(d.day)}</span>
          <span className="h-2 rounded bg-card overflow-hidden" aria-hidden>
            <span className="block h-full rounded" style={{ width: `${(Math.abs(d.net) / max) * 100}%`, background: d.net >= 0 ? "#3987e5" : "#e66767" }} />
          </span>
          <span className="text-right">
            <span className={cn("font-mono font-semibold", pnlTone(d.net))}>{fmtRupees(d.net, true)}</span>
            <span className="block text-[10px] text-[#8391a7]">{d.trades} trade{d.trades === 1 ? "" : "s"} · charges ₹{fmtPremium(d.charges)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="px-4 py-10 text-center text-xs text-[#8391a7]">{text}</div>;
}

export { useLiveMarks };
