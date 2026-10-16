"use client";
import { memo } from "react";
import { CalendarClock, Gauge, Layers, TrendingDown, TrendingUp, Minus } from "lucide-react";
import type { Board, BoardPillar } from "@/types/options";
import { cn } from "@/lib/utils";
import { ageSeconds, fmtAge, fmtDate, fmtNum, PILLAR_LABELS } from "@/lib/optionsFormat";
import { BiasMark } from "./StatusBits";

const SPOT_NAMES: Record<string, string> = { NIFTY: "NIFTY 50", BANKNIFTY: "NIFTY BANK", FINNIFTY: "NIFTY FIN SERVICE" };

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] tracking-widest text-[#64748b]">{label}</div>
      <div className="font-mono text-sm font-semibold text-[#e2e8f0] mt-0.5 truncate">{value}</div>
      {sub && <div className="text-[10px] text-[#64748b] mt-0.5 truncate">{sub}</div>}
    </div>
  );
}

function PillarTile({ p }: { p: BoardPillar }) {
  const tone = p.status ? { pass: "border-l-green", warn: "border-l-yellow", fail: "border-l-red", na: "border-l-[#334155]" }[p.status]
                        : p.bias > 0 ? "border-l-green" : p.bias < 0 ? "border-l-red" : "border-l-[#334155]";
  return (
    <div className={cn("bg-card border border-[#1e2d45] border-l-2 rounded-lg px-3 py-2.5 min-w-0", tone)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-[#e2e8f0] truncate">{PILLAR_LABELS[p.pillar] ?? p.pillar}</span>
        <BiasMark bias={p.bias} status={p.status} size={11} />
      </div>
      {!p.status && p.bias !== 0 && (
        <div className="h-1 bg-[#0b0f1a] rounded mt-2 overflow-hidden" aria-hidden>
          <div className={cn("h-full rounded", p.bias > 0 ? "bg-green" : "bg-red")} style={{ width: `${Math.round(p.strength * 100)}%` }} />
        </div>
      )}
      <p className="text-[11px] text-[#94a3b8] leading-snug mt-1.5 line-clamp-2" title={p.detail}>{p.detail}</p>
    </div>
  );
}

// Module level (not inside LevelsLadder): a component defined inside another is a new type on
// every render, so React would rebuild every row on each poll.
function LevelRow({ name, value, price }: { name: string; value: number; price: number }) {
  const dist = value - price;
  return (
    <div className="flex items-center justify-between text-[11px] py-1 px-2 rounded hover:bg-[#ffffff06]">
      <span className="text-[#94a3b8] truncate">{name}</span>
      <span className="flex items-center gap-3 font-mono tabular-nums">
        <span className="text-[#e2e8f0]">{fmtNum(value)}</span>
        <span className={cn("w-12 text-right", dist > 0 ? "text-[#86efac]" : "text-[#fca5a5]")}>{dist > 0 ? "+" : "−"}{fmtNum(Math.abs(dist))}</span>
      </span>
    </div>
  );
}

function LevelsLadder({ board }: { board: Board }) {
  const price = board.fut ?? 0;
  const rows = Object.entries(board.levels).map(([name, value]) => ({ name, value }));
  const above = rows.filter(r => r.value > price).sort((a, b) => b.value - a.value).slice(-6);
  const below = rows.filter(r => r.value <= price).sort((a, b) => b.value - a.value).slice(0, 6);
  return (
    <div>
      <div className="text-[10px] tracking-widest text-[#64748b] mb-1.5 px-2">RESISTANCE ABOVE</div>
      {above.length ? above.map(r => <LevelRow key={r.name} {...r} price={price} />) : <div className="text-[11px] text-[#475569] px-2 py-1">Open space</div>}
      <div className="my-1.5 flex items-center gap-2 px-2 py-1.5 rounded-md bg-[#ff993314] border border-[#ff993333]">
        <span className="text-[10px] font-bold tracking-widest text-[#ff9933]">FUT</span>
        <span className="font-mono text-sm font-bold text-[#ff9933] tabular-nums ml-auto">{fmtNum(price, 1)}</span>
      </div>
      <div className="text-[10px] tracking-widest text-[#64748b] mb-1.5 mt-2 px-2">SUPPORT BELOW</div>
      {below.length ? below.map(r => <LevelRow key={r.name} {...r} price={price} />) : <div className="text-[11px] text-[#475569] px-2 py-1">Open space</div>}
    </div>
  );
}

// Memoised: SWR keeps the same object when a poll returns identical data, so an unchanged board skips rendering.
export const IndexBoard = memo(function IndexBoard({ board }: { board: Board }) {
  const age = ageSeconds(board.as_of);
  const TrendIcon = board.htf_trend === "up" ? TrendingUp : board.htf_trend === "down" ? TrendingDown : Minus;
  const oi = board.oi ?? {};
  return (
    <section className="fade-in bg-surface border border-[#1e2d45] rounded-xl overflow-hidden" aria-label={`${board.index} analysis board`}>
      <div className="px-5 py-4 border-b border-[#1e2d45] flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[10px] tracking-widest text-[#64748b]">{SPOT_NAMES[board.index] ?? board.index}</div>
          <div className="flex items-baseline gap-3 mt-1">
            <span className="text-3xl font-bold text-[#e2e8f0] leading-none">{fmtNum(board.spot, 2)}</span>
            <span className="text-xs text-[#64748b]">fut <span className="font-mono text-[#94a3b8]">{fmtNum(board.fut, 1)}</span> · basis <span className="font-mono text-[#94a3b8]">{board.basis >= 0 ? "+" : ""}{fmtNum(board.basis, 1)}</span></span>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md bg-card border border-[#1e2d45] text-[#e2e8f0]">
            <TrendIcon size={12} className={board.htf_trend === "up" ? "text-green" : board.htf_trend === "down" ? "text-red" : "text-[#94a3b8]"} />
            Trend {board.htf_trend}
          </span>
          <span className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md bg-card border border-[#1e2d45] text-[#e2e8f0]">
            <Layers size={12} className="text-[#ff9933]" /> {board.regime} regime
          </span>
          {board.nearest_expiry && (
            <span className={cn("inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md border",
              board.expiry_day ? "bg-[#f59e0b14] border-[#f59e0b44] text-yellow" : "bg-card border-[#1e2d45] text-[#e2e8f0]")}>
              <CalendarClock size={12} /> {board.expiry_day ? (board.monthly_expiry ? "Monthly expiry today" : "Weekly expiry today") : `Expiry ${fmtDate(board.nearest_expiry)}`}
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md bg-card border border-[#1e2d45] text-[#64748b]">
            updated {fmtAge(age)}
          </span>
        </div>
      </div>

      <div className="px-5 py-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 border-b border-[#1e2d45]">
        <Stat label="INDIA VIX" value={fmtNum(board.vix, 2)} sub={board.vix_pct != null ? `1-yr percentile ${board.vix_pct.toFixed(0)}` : undefined} />
        <Stat label="ATM IV" value={board.atm_iv != null ? `${(board.atm_iv * 100).toFixed(1)}%` : "—"} sub="Black-76, synthetic forward" />
        <Stat label="EXPECTED MOVE" value={board.expected_move_1d != null ? `±${fmtNum(board.expected_move_1d)}` : "—"} sub="1 day, 1 std dev" />
        <Stat label="PCR (OI)" value={oi.pcr != null ? oi.pcr.toFixed(2) : "—"} sub="ATM ± expected move" />
        <Stat label="OI WALLS" value={oi.put_wall && oi.call_wall ? `${fmtNum(oi.put_wall)} / ${fmtNum(oi.call_wall)}` : "—"} sub="put support / call resistance" />
        <Stat label="CONTRACT" value={`lot ${board.lot_size}`} sub={`strike step ${board.strike_step}`} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px]">
        <div className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <Gauge size={13} className="text-[#ff9933]" />
            <span className="text-xs font-semibold text-[#e2e8f0]">Analysis pillars</span>
            <span className="text-[10px] text-[#64748b]">direction-neutral view · each signal is graded for its own direction</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-2">
            {board.pillars.map(p => <PillarTile key={p.pillar} p={p} />)}
          </div>
        </div>
        <div className="p-4 border-t xl:border-t-0 xl:border-l border-[#1e2d45]">
          <div className="text-xs font-semibold text-[#e2e8f0] mb-2 px-2">Key levels <span className="text-[10px] font-normal text-[#64748b]">futures points</span></div>
          <LevelsLadder board={board} />
        </div>
      </div>
    </section>
  );
});
