"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, Loader2, Minus, Plus } from "lucide-react";
import type { CheckContractRef } from "@/types/check";
import type { ChargeParts, Desk, DeskOrder, OrderType, Product, Side, TicketInfo } from "@/types/desk";
import { ApiError, sendJson, useOptionsApi } from "@/lib/optionsApi";
import { useLiveIndices } from "@/lib/liveIndices";
import { fmtDateTime, fmtPremium, fmtRupees } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";
import { ContractInput } from "@/components/check/ContractInput";
import { pnlTone } from "@/components/check/Money";

export interface TicketPreset {
  text?: string;
  side?: Side;
  lots?: number;
  type?: OrderType;
  product?: Product;
  price?: number;
  trigger?: number;
  source?: string;
}

const TYPES: { v: OrderType; label: string; hint: string }[] = [
  { v: "MARKET", label: "Market", hint: "Fills now at the live ask (buy) or bid (sell)" },
  { v: "LIMIT", label: "Limit", hint: "Fills only at your price or better" },
  { v: "SL", label: "SL", hint: "Waits for the trigger, then a limit order at your price" },
  { v: "SL-M", label: "SL-M", hint: "Waits for the trigger, then fills at market" },
];
const PRODUCTS: { v: Product; label: string; hint: string }[] = [
  { v: "MIS", label: "Intraday", hint: "MIS · squared off at 15:20" },
  { v: "NRML", label: "Carry", hint: "NRML · hold overnight, settles at expiry" },
];
const PART_LABELS: [keyof ChargeParts, string][] = [
  ["brokerage", "Brokerage (₹20 an order)"], ["stt", "STT (on the sell)"], ["exchange", "Exchange charges"],
  ["sebi", "SEBI fee"], ["stamp", "Stamp duty (on the buy)"], ["gst", "GST 18%"],
];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const num = (s: string) => (s.trim() === "" ? null : Number(s));

function Segmented<T extends string>({ value, options, onChange, label, tone }: {
  value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string; tone?: (v: T) => string;
}) {
  return (
    <div className="flex rounded-lg border border-[#1e2d45] p-0.5 bg-card" role="group" aria-label={label}>
      {options.map(o => (
        <button key={o.v} type="button" aria-pressed={value === o.v} onClick={() => onChange(o.v)}
                className={cn("flex-1 h-8 px-2 rounded-md text-[12px] font-semibold transition-colors whitespace-nowrap",
                  value === o.v ? (tone?.(o.v) ?? "bg-[#ff99331f] text-[#ff9933]") : "text-[#94a3b8] hover:text-[#e2e8f0]")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function PriceInput({ id, label, value, onChange, hint }: { id: string; label: string; value: string; onChange: (v: string) => void; hint?: string }) {
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="text-[10px] tracking-widest text-[#8391a7]">{label}</label>
      <div className="mt-1 relative">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8391a7] text-sm" aria-hidden>₹</span>
        <input id={id} value={value} inputMode="decimal" autoComplete="off" placeholder={hint}
               onChange={e => onChange(e.target.value.replace(/[^0-9.]/g, ""))}
               className="w-full bg-card border border-[#1e2d45] rounded-lg pl-6 pr-2 h-10 text-[14px] font-mono text-[#e2e8f0] placeholder:text-[#475569] focus:outline-none focus:border-[#ff9933] focus:ring-2 focus:ring-[#ff993333]" />
      </div>
    </div>
  );
}

export function OrderTicket({ desk, preset, onPlaced }: { desk: Desk | undefined; preset: TicketPreset; onPlaced: (o: DeskOrder) => void }) {
  const [text, setText] = useState(preset.text ?? "");
  const [contract, setContract] = useState<CheckContractRef | null>(null);
  const [side, setSide] = useState<Side>(preset.side ?? "BUY");
  const [product, setProduct] = useState<Product>(preset.product ?? "MIS");
  const [type, setType] = useState<OrderType>(preset.type ?? "MARKET");
  const [lots, setLots] = useState(preset.lots ?? 1);
  const [price, setPrice] = useState(preset.price ? preset.price.toFixed(2) : "");
  const [trigger, setTrigger] = useState(preset.trigger ? preset.trigger.toFixed(2) : "");
  const [source, setSource] = useState(preset.source);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [showCharges, setShowCharges] = useState(false);
  const resultRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => { if (result) resultRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [result]);

  const needsPrice = type === "LIMIT" || type === "SL";
  const needsTrigger = type === "SL" || type === "SL-M";
  const params = useDebounced(contract ? new URLSearchParams({
    token: String(contract.token), side, lots: String(lots), order_type: type, product,
    ...(needsPrice && num(price) ? { price } : {}), ...(needsTrigger && num(trigger) ? { trigger_price: trigger } : {}),
  }).toString() : null, 250);
  const { data: info, error } = useOptionsApi<TicketInfo>(params ? `/api/desk/ticket?${params}` : null, 3000);
  const fresh = info && contract && info.contract.token === contract.token ? info : null;

  // The live stream's copy of this contract beats the ticket's, which refreshes every 3 s
  const lvl = useLiveIndices().levels[contract?.symbol ?? ""];
  const q = lvl?.kind === "option" && lvl.ltp != null ? { bid: lvl.bid ?? null, ask: lvl.ask ?? null, ltp: lvl.ltp, source: "live" }
    : fresh?.quote ?? null;

  const lotSize = contract?.lot_size ?? fresh?.contract.lot_size ?? 0;
  const held = fresh ? fresh.held[product] : 0;
  const freeToSell = fresh ? Math.max(0, fresh.held[product] - fresh.selling[product]) : 0;
  const position = desk?.positions.find(p => p.token === contract?.token && p.product === product && p.open);
  const est = fresh?.estimate;
  const sellPnl = side === "SELL" && position?.avg != null && est?.price != null && est.charges
    ? (est.price - position.avg) * lots * lotSize - (est.charges.total ?? 0) - position.buy_charges * (lots * lotSize) / position.qty
    : null;
  const market = fresh?.market ?? desk?.market;

  // A limit order starts from the live price on your side of the book: once per contract, side and type
  // (set while rendering, React's pattern for state that follows other state), so clearing the box to
  // type your own price doesn't refill it
  const prefillKey = `${contract?.token}-${side}-${type}`;
  const sidePx = q ? (side === "BUY" ? (q.ask ?? q.ltp) : (q.bid ?? q.ltp)) : null;
  const [prefilledFor, setPrefilledFor] = useState("");
  if (needsPrice && sidePx && prefilledFor !== prefillKey) {
    setPrefilledFor(prefillKey);
    if (!price) setPrice((Math.round(sidePx / 0.05) * 0.05).toFixed(2));
  }

  const stale = !fresh;
  const problem = fresh?.problem ?? (error instanceof ApiError ? error.message : null);
  const canSubmit = !!contract && !!fresh && !problem && !busy;
  const verb = side === "BUY" ? "Buy" : "Sell";
  const amo = market && !market.open;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!contract || !canSubmit) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await sendJson<{ order: DeskOrder }>("/api/desk/orders", "POST", {
        token: contract.token, side, lots, order_type: type, product, source: source ?? "ticket",
        price: needsPrice ? num(price) : null, trigger_price: needsTrigger ? num(trigger) : null,
      });
      const o = r.order;
      setResult({ ok: o.status !== "REJECTED", text: describe(o) });
      setSource(undefined);
      onPlaced(o);
    } catch (err) {
      setResult({ ok: false, text: err instanceof Error ? err.message : "The order didn't go through, try again" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="bg-surface border border-[#1e2d45] rounded-xl p-4 sm:p-5 space-y-4" aria-label="Order ticket">
      <ContractInput id="desk-contract" value={text} onChange={v => { setText(v); setResult(null); }} onPick={setText}
                     onResolved={c => { if (contract && c?.token !== contract.token) setPrice(""); setContract(c); }} />

      <div className="grid grid-cols-3 gap-2 -mt-2" aria-live="polite">
        {([["BID", q?.bid], ["ASK", q?.ask], ["LTP", q?.ltp]] as const).map(([k, v]) => (
          <div key={k} className="bg-card border border-[#1e2d45] rounded-lg px-2.5 py-1.5 min-w-0">
            <div className="text-[9px] tracking-widest text-[#8391a7]">{k}</div>
            <div className={cn("font-mono text-[14px] tabular-nums truncate", k === "BID" ? "text-[#fca5a5]" : k === "ASK" ? "text-[#86efac]" : "text-[#e2e8f0]")}>
              {v != null ? fmtPremium(v) : "—"}
            </div>
          </div>
        ))}
      </div>
      <p className="-mt-2 h-4 text-[11px] text-[#8391a7] truncate">
        {!contract ? "Pick a contract to see its price" : !q ? "No price yet" :
          q.source === "live" ? <><span className="inline-block w-1.5 h-1.5 rounded-full bg-green mr-1.5 align-middle" aria-hidden />Live price</>
          : `From the ${q.source}${market?.open ? "; the live stream starts in a moment" : ""}`}
      </p>

      <Segmented label="Buy or sell" value={side} onChange={v => { setSide(v); setPrice(""); setResult(null); }}
                 options={[{ v: "BUY", label: "Buy" }, { v: "SELL", label: held ? `Sell · ${freeToSell} qty` : "Sell" }]}
                 tone={v => (v === "BUY" ? "bg-[#22c55e1f] text-[#4ade80]" : "bg-[#ef44441f] text-[#f87171]")} />

      <div className="grid grid-cols-2 gap-3">
        <div className="min-w-0">
          <div className="text-[10px] tracking-widest text-[#8391a7] mb-1">PRODUCT</div>
          <Segmented label="Product" value={product} onChange={setProduct} options={PRODUCTS} />
        </div>
        <div className="min-w-0">
          <div className="text-[10px] tracking-widest text-[#8391a7] mb-1" id="desk-lots-label">LOTS{lotSize ? ` · ${lots * lotSize} qty` : ""}</div>
          <div className="flex items-center h-9 rounded-lg border border-[#1e2d45] bg-card" role="group" aria-labelledby="desk-lots-label">
            <button type="button" aria-label="One lot fewer" onClick={() => setLots(l => Math.max(1, l - 1))}
                    className="h-full w-9 grid place-items-center text-[#94a3b8] hover:text-[#e2e8f0] disabled:opacity-40" disabled={lots <= 1}><Minus size={14} /></button>
            <input aria-label="Lots" value={lots} inputMode="numeric" onChange={e => setLots(Math.min(20, Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1)))}
                   className="flex-1 min-w-0 w-full bg-transparent text-center font-mono text-[14px] text-[#e2e8f0] focus:outline-none" />
            <button type="button" aria-label="One lot more" onClick={() => setLots(l => Math.min(20, l + 1))}
                    className="h-full w-9 grid place-items-center text-[#94a3b8] hover:text-[#e2e8f0] disabled:opacity-40" disabled={lots >= 20}><Plus size={14} /></button>
          </div>
        </div>
      </div>
      <p className="-mt-2 text-[11px] text-[#8391a7]">{PRODUCTS.find(p => p.v === product)!.hint}</p>

      <div>
        <div className="text-[10px] tracking-widest text-[#8391a7] mb-1">ORDER TYPE</div>
        <Segmented label="Order type" value={type} onChange={v => { setType(v); setResult(null); }} options={TYPES} />
        <p className="mt-1 text-[11px] text-[#8391a7]">{TYPES.find(t => t.v === type)!.hint}</p>
      </div>

      {(needsPrice || needsTrigger) && (
        <div className="grid grid-cols-2 gap-3">
          {needsTrigger && <PriceInput id="desk-trigger" label="TRIGGER" value={trigger} onChange={setTrigger}
                                       hint={side === "BUY" ? "above LTP" : "below LTP"} />}
          {needsPrice && <PriceInput id="desk-price" label="LIMIT PRICE" value={price} onChange={setPrice} />}
        </div>
      )}

      <dl className="rounded-lg border border-[#1e2d45] bg-card divide-y divide-[#1e2d45] text-[12px]" aria-busy={stale}>
        <Row label={type === "MARKET" ? `Price (live ${side === "BUY" ? "ask" : "bid"})` : "Price"} value={est?.price != null ? `₹${fmtPremium(est.price)}` : "—"} />
        <Row label="Order value" value={fmtRupees(est?.value)} />
        <div className="px-3 py-2 flex flex-wrap items-center justify-between gap-x-2">
          <dt><button type="button" onClick={() => setShowCharges(s => !s)} aria-expanded={showCharges}
                      className="text-[#94a3b8] hover:text-[#e2e8f0] inline-flex items-center gap-1">Charges incl. GST
            <ChevronDown size={12} className={cn("transition-transform", showCharges && "rotate-180")} aria-hidden /></button></dt>
          <dd className="font-mono text-[#e2e8f0]">{est?.charges ? `₹${fmtPremium(est.charges.total)}` : "—"}</dd>
          {showCharges && est?.charges && (
            <dd className="basis-full">
              <ul className="mt-2 space-y-1 text-[11px] text-[#8391a7]">
                {PART_LABELS.map(([k, label]) => (
                  <li key={k} className="flex justify-between gap-2"><span>{label}</span><span className="font-mono">₹{fmtPremium(est.charges![k] as number)}</span></li>
                ))}
              </ul>
            </dd>
          )}
        </div>
        {side === "BUY" ? <>
          <Row label="Funds needed" value={fmtRupees(est?.block)} sub={type === "MARKET" ? "incl. 2% for the price moving" : undefined} />
          <Row label="Available after" value={fresh && est?.block != null ? fmtRupees(fresh.available - est.block) : "—"} />
          <Row label="Breakeven" value={est?.breakeven != null ? `₹${fmtPremium(est.breakeven)}` : "—"} sub="sell above this to profit after both orders' charges" />
        </> : <>
          <Row label="You get" value={est?.value != null && est.charges ? fmtRupees(est.value - (est.charges.total ?? 0)) : "—"} />
          <Row label="Est. P&L on this sell" value={sellPnl != null ? fmtRupees(sellPnl, true) : "—"} tone={pnlTone(sellPnl)}
               sub={position?.avg != null ? `vs your average ₹${fmtPremium(position.avg)}, after charges` : undefined} />
        </>}
      </dl>

      {problem && contract && (
        <p role="alert" className="flex items-start gap-2 text-[12px] text-[#fcd34d] bg-[#f59e0b0d] border border-[#f59e0b33] rounded-lg px-3 py-2">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" aria-hidden /> {problem}
        </p>
      )}
      {market && (market.open && !market.live) && (
        <p className="text-[12px] text-[#fcd34d]">Live prices aren&apos;t streaming right now, so orders are paused until the feed is back.</p>
      )}

      <button type="submit" disabled={!canSubmit || (market?.open && !market.live)}
              className={cn("w-full h-11 rounded-lg font-semibold text-sm inline-flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
                side === "BUY" ? "bg-[#15803d] hover:bg-[#166534] text-white" : "bg-[#dc2626] hover:bg-[#b91c1c] text-white")}>
        {busy ? <><Loader2 size={15} className="animate-spin" aria-hidden /> Placing…</>
          : <>{verb} {lots} lot{lots > 1 ? "s" : ""}{amo ? " at the open" : ""}{est?.value != null ? ` · ${fmtRupees(est.value)}` : ""}</>}
      </button>
      <p className="-mt-2 text-[11px] text-[#8391a7] text-center min-h-4">
        {amo ? `Market closed: the order goes in at the open, ${fmtDateTime(market!.next_open)}` : "Paper money only: no real order is placed"}
      </p>

      {result && (
        <p role="status" ref={resultRef} className={cn("fade-in flex items-start gap-2 text-[12px] rounded-lg px-3 py-2 border",
          result.ok ? "text-[#bfdbfe] bg-[#3987e50d] border-[#3987e533]" : "text-[#fecaca] bg-[#ef44440d] border-[#ef444433]")}>
          {result.ok ? <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0" aria-hidden /> : <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" aria-hidden />}
          {result.text}
        </p>
      )}
    </form>
  );
}

function Row({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="px-3 py-2 flex items-start justify-between gap-3">
      <dt className="text-[#94a3b8] min-w-0">{label}{sub && <span className="block text-[10px] text-[#8391a7] leading-snug">{sub}</span>}</dt>
      <dd className={cn("font-mono text-right flex-shrink-0", tone ?? "text-[#e2e8f0]")}>{value}</dd>
    </div>
  );
}

export function describe(o: DeskOrder): string {
  const what = `${o.side === "BUY" ? "Buy" : "Sell"} ${o.lots} lot${o.lots > 1 ? "s" : ""} ${o.symbol}`;
  switch (o.status) {
    case "FILLED": return `${what}: filled at ₹${fmtPremium(o.fill_price)} (${o.fill_source}). Charges ₹${fmtPremium(o.charges?.total)}.`;
    case "AMO": return `${what}: after-market order placed. It goes in at the next open.`;
    case "OPEN": return `${what}: open at ${o.order_type === "LIMIT" ? `₹${fmtPremium(o.price)}` : `trigger ₹${fmtPremium(o.trigger_price)}`}. It fills when the market gets there.`;
    case "TRIGGERED": return `${what}: triggered, now a limit at ₹${fmtPremium(o.price)}.`;
    case "PENDING": return `${what}: sent. It fills in a moment.`;
    case "REJECTED": return `${what}: rejected. ${o.reason ?? ""}`;
    default: return `${what}: ${o.status_label.toLowerCase()}. ${o.reason ?? ""}`;
  }
}
