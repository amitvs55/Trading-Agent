import { cn, formatINR, formatPct } from "@/lib/utils";
import type { TradeProposal } from "@/types/pipeline";

interface Props { proposal: TradeProposal; }

const DIR_STYLE = {
  long:  { bg: "bg-[#22c55e22] border-[#22c55e44] text-green",  label: "LONG"  },
  short: { bg: "bg-[#ef444422] border-[#ef444433] text-red",   label: "SHORT" },
  hold:  { bg: "bg-[#f59e0b22] border-[#f59e0b44] text-yellow", label: "HOLD"  },
};

export function Stage3TradeProposal({ proposal }: Props) {
  const dir = DIR_STYLE[proposal.direction] ?? DIR_STYLE.hold;

  return (
    <div className="p-5">
      {/* Direction badge */}
      <div className="flex items-center gap-4 mb-5">
        <span className={cn("text-2xl font-black px-5 py-2 rounded-xl border tracking-widest", dir.bg)}>{dir.label}</span>
        <div>
          <div className="text-xs text-[#8391a7]">Time Horizon</div>
          <div className="text-sm font-semibold text-[#e2e8f0] font-mono">{proposal.time_horizon}</div>
        </div>
        {proposal.risk_reward_ratio != null && (
          <div>
            <div className="text-xs text-[#8391a7]">Risk : Reward</div>
            <div className="text-sm font-semibold font-mono text-[#e2e8f0]">1 : {proposal.risk_reward_ratio.toFixed(2)}</div>
          </div>
        )}
        <div>
          <div className="text-xs text-[#8391a7]">Position Size</div>
          <div className="text-sm font-semibold font-mono text-[#ff9933]">{proposal.position_size_pct.toFixed(1)}%</div>
        </div>
      </div>

      {/* Price grid */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-bg border border-[#1e2d45] rounded-lg p-3 text-center">
          <div className="text-xs text-[#8391a7] mb-1">Entry Price</div>
          <div className="font-mono font-bold text-[#e2e8f0]">{formatINR(proposal.entry_price)}</div>
        </div>
        <div className="bg-bg border border-[#ef444422] rounded-lg p-3 text-center">
          <div className="text-xs text-[#8391a7] mb-1">Stop Loss</div>
          <div className="font-mono font-bold text-red">{formatINR(proposal.stop_loss)}</div>
          {proposal.entry_price && proposal.stop_loss && (
            <div className="text-[10px] text-[#8391a7] mt-0.5">
              {formatPct((proposal.stop_loss - proposal.entry_price) / proposal.entry_price * 100)}
            </div>
          )}
        </div>
        <div className="bg-bg border border-[#22c55e22] rounded-lg p-3 text-center">
          <div className="text-xs text-[#8391a7] mb-1">Take Profit</div>
          <div className="font-mono font-bold text-green">{formatINR(proposal.take_profit)}</div>
          {proposal.entry_price && proposal.take_profit && (
            <div className="text-[10px] text-[#8391a7] mt-0.5">
              {formatPct((proposal.take_profit - proposal.entry_price) / proposal.entry_price * 100)}
            </div>
          )}
        </div>
      </div>

      {/* Visual SL/TP bar */}
      {proposal.entry_price && proposal.stop_loss && proposal.take_profit && (
        <div className="bg-bg border border-[#1e2d45] rounded-lg p-3 mb-4">
          <div className="text-xs text-[#8391a7] mb-2">Price Levels</div>
          <div className="relative h-2 bg-[#1e2d45] rounded">
            {(() => {
              const lo  = Math.min(proposal.stop_loss, proposal.entry_price, proposal.take_profit) * 0.995;
              const hi  = Math.max(proposal.stop_loss, proposal.entry_price, proposal.take_profit) * 1.005;
              const pct = (v: number) => `${((v - lo) / (hi - lo) * 100).toFixed(1)}%`;
              return (
                <>
                  <div className="absolute h-2 rounded" style={{ left: pct(proposal.stop_loss!), right: `${100 - parseFloat(pct(proposal.take_profit!))}%`, background: "linear-gradient(to right,#ef444433,#22c55e33)" }} />
                  <div className="absolute w-0.5 h-4 -top-1 bg-red rounded" style={{ left: pct(proposal.stop_loss!) }} />
                  <div className="absolute w-0.5 h-4 -top-1 bg-[#ff9933] rounded" style={{ left: pct(proposal.entry_price!) }} />
                  <div className="absolute w-0.5 h-4 -top-1 bg-green rounded" style={{ left: pct(proposal.take_profit!) }} />
                </>
              );
            })()}
          </div>
          <div className="flex justify-between text-[10px] font-mono mt-2">
            <span className="text-red">SL {formatINR(proposal.stop_loss, 0)}</span>
            <span className="text-[#ff9933]">Entry {formatINR(proposal.entry_price, 0)}</span>
            <span className="text-green">TP {formatINR(proposal.take_profit, 0)}</span>
          </div>
        </div>
      )}

      <p className="text-xs text-[#94a3b8] leading-relaxed">{proposal.rationale}</p>
    </div>
  );
}
