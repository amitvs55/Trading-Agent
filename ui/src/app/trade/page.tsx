"use client";
import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeftRight, Info, Loader2, Plus, RotateCcw } from "lucide-react";
import type { Desk, OrderType, Product, Side } from "@/types/desk";
import { sendJson, useOptionsApi } from "@/lib/optionsApi";
import { fmtDateTime, fmtRupees } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";
import { LiveAge } from "@/components/common/LiveAge";
import { PaperCurve } from "@/components/options/PaperChart";
import { pnlTone } from "@/components/check/Money";
import { OrderTicket, type TicketPreset } from "@/components/desk/OrderTicket";
import { DaysPanel, liveOpenPnl, OrdersPanel, PositionsPanel, TradesPanel, useLiveMarks } from "@/components/desk/DeskTables";

type Tab = "positions" | "orders" | "trades" | "days";

export default function TradePage() {
  return (
    <Suspense fallback={null}>
      <TradeDesk />
    </Suspense>
  );
}

function presetFrom(params: URLSearchParams): TicketPreset {
  const n = (k: string) => (params.get(k) ? Number(params.get(k)) : undefined);
  const pick = <T extends string>(k: string, allowed: readonly T[]) => {
    const v = params.get(k);
    return v && (allowed as readonly string[]).includes(v) ? (v as T) : undefined;
  };
  return {
    text: params.get("q") ?? undefined, lots: n("lots"), price: n("price"), trigger: n("trigger"),
    side: pick<Side>("side", ["BUY", "SELL"]), type: pick<OrderType>("type", ["MARKET", "LIMIT", "SL", "SL-M"]),
    product: pick<Product>("product", ["MIS", "NRML"]), source: params.get("signal") ? `signal:${params.get("signal")}` : undefined,
  };
}

function Tile({ label, value, sub, tone, loading }: { label: string; value: string; sub?: React.ReactNode; tone?: string; loading?: boolean }) {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl p-4 min-w-0">
      <div className="text-[10px] text-[#8391a7] tracking-widest mb-2">{label}</div>
      {loading ? <div className="skeleton h-8 rounded w-24" /> :
        <div className={cn("fade-in font-bold text-2xl leading-8 font-mono tabular-nums truncate", tone ?? "text-[#e2e8f0]")}>{value}</div>}
      <div className="text-[11px] text-[#8391a7] mt-1 truncate">{loading ? " " : sub ?? " "}</div>
    </div>
  );
}

function TradeDesk() {
  const params = useSearchParams();
  const [preset] = useState(() => presetFrom(params));
  const { data: desk, refresh } = useOptionsApi<Desk>("/api/desk", 3000);
  const [tab, setTab] = useState<Tab>("positions");
  const marked = useLiveMarks(desk?.positions ?? []);
  const openPnl = liveOpenPnl(desk, marked);
  const loading = !desk;
  const openCount = desk?.positions.filter(p => p.open).length ?? 0;
  const activeOrders = desk?.orders.filter(o => o.active).length ?? 0;
  const equity = desk ? desk.funds.cash + marked.filter(p => p.open).reduce((s, p) => s + (p.ltp ?? p.avg ?? 0) * p.qty, 0) : null;
  const total = desk && equity != null ? equity - desk.funds.start : null;
  const today = desk && openPnl != null ? desk.today.realised + openPnl : null;

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "positions", label: "Positions", count: openCount }, { id: "orders", label: "Orders", count: activeOrders },
    { id: "trades", label: "Trades", count: desk?.stats.trades }, { id: "days", label: "By day" },
  ];

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5 flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><ArrowLeftRight size={20} className="text-[#ff9933]" /> Trade</h1>
          <p className="text-sm text-[#8391a7] mt-1">
            Buy and sell NIFTY options with paper money on live prices. Every order pays ₹20 brokerage plus STT, exchange, SEBI and stamp charges and 18% GST.
          </p>
        </div>
        {desk && <AccountControls desk={desk} onDone={() => void refresh()} />}
      </div>

      <div className="grid gap-5 grid-cols-1 xl:grid-cols-[400px_minmax(0,1fr)] items-start">
        <div className="min-w-0">
          <OrderTicket desk={desk} preset={preset} onPlaced={() => { void refresh(); setTab(t => (t === "trades" || t === "days" ? "orders" : t)); }} />
        </div>

        <div className="space-y-5 min-w-0">
          <div className="grid grid-cols-2 md:grid-cols-3 2xl:grid-cols-5 gap-3">
            <Tile loading={loading} label="AVAILABLE" value={fmtRupees(desk?.funds.available)}
                  sub={desk ? (desk.funds.blocked ? `${fmtRupees(desk.funds.blocked)} held for open orders` : `of ${fmtRupees(desk.funds.start)} starting funds`) : undefined} />
            <Tile loading={loading} label="TODAY" value={fmtRupees(today, true)} tone={pnlTone(today)}
                  sub={desk ? `realised ${fmtRupees(desk.today.realised, true)} · open ${fmtRupees(openPnl, true)}` : undefined} />
            <Tile loading={loading} label="OPEN P&L" value={fmtRupees(openPnl, true)} tone={pnlTone(openPnl)}
                  sub={`${openCount} open position${openCount === 1 ? "" : "s"}`} />
            <Tile loading={loading} label="TOTAL P&L" value={fmtRupees(total, true)} tone={pnlTone(total)}
                  sub={desk && total != null ? `${total >= 0 ? "+" : ""}${((total / desk.funds.start) * 100).toFixed(2)}% · equity ${fmtRupees(equity)}` : undefined} />
            <Tile loading={loading} label="CHARGES PAID" value={fmtRupees(desk?.stats.charges_paid)}
                  sub={desk ? `brokerage ${fmtRupees(desk.stats.charges_detail.brokerage)} · GST ${fmtRupees(desk.stats.charges_detail.gst)}` : undefined} />
          </div>

          <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden min-w-0">
            <div className="px-2 sm:px-3 border-b border-[#1e2d45] flex items-center justify-between gap-2">
              <div role="tablist" aria-label="Desk" className="flex overflow-x-auto">
                {tabs.map(t => (
                  <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                          className={cn("relative h-11 px-3 text-[12.5px] font-medium whitespace-nowrap transition-colors",
                            tab === t.id ? "text-[#ff9933]" : "text-[#94a3b8] hover:text-[#e2e8f0]")}>
                    {t.label}{t.count ? <span className="ml-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded bg-card text-[#cbd5e1]">{t.count}</span> : null}
                    {tab === t.id && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded bg-[#ff9933]" aria-hidden />}
                  </button>
                ))}
              </div>
              <span className="hidden sm:block text-[10px] text-[#8391a7] pr-1 whitespace-nowrap">updated <LiveAge iso={desk?.as_of} never="…" /></span>
            </div>
            <div role="tabpanel" aria-label={tabs.find(t => t.id === tab)!.label}>
              {!desk ? <div className="p-4 space-y-2">{[0, 1, 2].map(i => <div key={i} className="skeleton h-12 rounded" />)}</div>
                : tab === "positions" ? <PositionsPanel desk={desk} onChange={() => void refresh()} />
                : tab === "orders" ? <OrdersPanel desk={desk} onChange={() => void refresh()} />
                : tab === "trades" ? <TradesPanel desk={desk} />
                : <DaysPanel desk={desk} />}
            </div>
          </section>

          <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden min-w-0">
            <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between gap-3 flex-wrap">
              <span className="text-xs font-semibold text-[#e2e8f0]">Balance after each closed trade</span>
              {desk && <span className="text-[10px] text-[#8391a7]">
                {desk.stats.trades ? `${desk.stats.wins} of ${desk.stats.trades} won · best ${fmtRupees(desk.stats.best, true)} · worst ${fmtRupees(desk.stats.worst, true)}` : "dashed line = starting funds"}
              </span>}
            </div>
            <div className="p-3">
              {!desk ? <div className="skeleton h-64 rounded-lg" /> : desk.curve.length > 1 ? <PaperCurve curve={desk.curve} start={desk.funds.start} /> :
                <div className="h-64 grid place-items-center text-xs text-[#8391a7] text-center px-6">The curve starts with your first closed trade.</div>}
            </div>
          </section>

          <div className="flex items-start gap-2.5 bg-[#3987e50d] border border-[#3987e533] rounded-xl px-4 py-3 text-[12px] text-[#94a3b8] leading-relaxed">
            <Info size={14} className="text-[#60a5fa] mt-0.5 flex-shrink-0" />
            <span>
              Orders fill like a real broker&apos;s: a buy at the live ask, a sell at the live bid, a limit only at your price or better, a stop
              when the last price crosses its trigger. Intraday positions are squared off at {desk?.market.square_off ?? "15:20"}; carried ones are
              settled at expiry at their intrinsic value. Outside market hours an order waits for the next open. This desk is buy-only: you sell
              what you hold. Running since {desk ? fmtDateTime(desk.account.started_at) : "…"}.
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}

function AccountControls({ desk, onDone }: { desk: Desk; onDone: () => void }) {
  const [mode, setMode] = useState<"add" | "reset" | null>(null);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sendJson("/api/desk/account", "POST", { action: mode, amount: Number(amount) });
      setMode(null);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Didn't work");
    } finally {
      setBusy(false);
    }
  }

  if (!mode) {
    const btn = "flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] hover:border-[#2d3e58] transition-colors";
    return (
      <div className="flex gap-2">
        <button type="button" className={btn} onClick={() => { setMode("add"); setAmount("50000"); }}><Plus size={12} /> Add funds</button>
        <button type="button" className={btn} onClick={() => { setMode("reset"); setAmount(String(desk.account.funds)); }}><RotateCcw size={12} /> Reset</button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="menu-pop w-full sm:w-auto flex flex-wrap items-end gap-2 bg-surface border border-[#1e2d45] rounded-xl p-3">
      <label className="text-[10px] tracking-widest text-[#8391a7]">{mode === "add" ? "ADD (₹)" : "START AGAIN WITH (₹)"}
        <input value={amount} onChange={e => setAmount(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" autoFocus
               className="mt-1 block w-36 bg-card border border-[#1e2d45] focus:border-[#ff9933] rounded-lg px-2.5 py-1.5 text-sm font-mono text-[#e2e8f0] outline-none" />
      </label>
      <button type="submit" disabled={busy || !Number(amount)}
              className="flex items-center gap-1.5 bg-[#ff9933] hover:bg-[#ffa94d] disabled:opacity-50 text-[#0b0f1a] rounded-lg px-3 py-2 text-xs font-semibold">
        {busy && <Loader2 size={12} className="animate-spin" />} {mode === "add" ? "Add funds" : "Reset account"}
      </button>
      <button type="button" onClick={() => setMode(null)} className="px-2 py-2 text-xs text-[#8391a7] hover:text-[#e2e8f0]">Cancel</button>
      {error && <p className="basis-full text-[11px] text-[#fca5a5]">{error}</p>}
      {mode === "reset" && <p className="basis-full text-[10px] text-[#8391a7]">Open orders are cancelled and positions, trades and P&amp;L start from zero.</p>}
    </form>
  );
}
