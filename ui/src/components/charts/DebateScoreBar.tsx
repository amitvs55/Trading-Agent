import type { DebateVerdict } from "@/types/pipeline";

interface Props { verdict: DebateVerdict; }

const REC_LABEL: Record<string, string> = {
  strong_buy: "STRONG BUY", buy: "BUY", hold: "HOLD", sell: "SELL", strong_sell: "STRONG SELL",
};
const REC_COLOR: Record<string, string> = {
  strong_buy: "text-green border-[#22c55e55] bg-[#22c55e22]",
  buy:        "text-green border-[#22c55e44] bg-[#22c55e11]",
  hold:       "text-yellow border-[#f59e0b44] bg-[#f59e0b11]",
  sell:       "text-red border-[#ef444444] bg-[#ef44440d]",
  strong_sell:"text-red border-[#ef444455] bg-[#ef444422]",
};

export function DebateScoreBar({ verdict }: Props) {
  return (
    <div>
      {/* Bull */}
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-green text-bg">BULL</span>
            <span className="text-[#64748b]">Winner: {verdict.winner === "bull" ? "✓" : ""}</span>
          </div>
          <span className="font-mono font-bold text-green">{verdict.bull_score.toFixed(1)} / 10</span>
        </div>
        <div className="h-2 bg-[#1e2d45] rounded">
          <div className="h-2 rounded" style={{
            width: `${verdict.bull_score * 10}%`,
            background: "linear-gradient(to right,#22c55e88,#22c55e)",
            boxShadow: "0 0 8px rgba(34,197,94,0.4)",
          }} />
        </div>
      </div>

      {/* Bear */}
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-red text-white">BEAR</span>
            <span className="text-[#64748b]">Winner: {verdict.winner === "bear" ? "✓" : ""}</span>
          </div>
          <span className="font-mono font-bold text-red">{verdict.bear_score.toFixed(1)} / 10</span>
        </div>
        <div className="h-2 bg-[#1e2d45] rounded">
          <div className="h-2 rounded" style={{
            width: `${verdict.bear_score * 10}%`,
            background: "linear-gradient(to right,#ef444488,#ef4444)",
            boxShadow: "0 0 8px rgba(239,68,68,0.4)",
          }} />
        </div>
      </div>

      <div className="pt-2 border-t border-[#1e2d45] flex items-center gap-2">
        <span className="text-xs text-[#64748b]">Recommendation:</span>
        <span className={`text-xs font-bold px-2 py-0.5 rounded border ${REC_COLOR[verdict.final_recommendation]}`}>
          {REC_LABEL[verdict.final_recommendation]}
        </span>
      </div>
    </div>
  );
}
