import { cn } from "@/lib/utils";
import type { ResearchOutput, DebateVerdict } from "@/types/pipeline";

interface Props {
  bullCase:     ResearchOutput;
  bearCase:     ResearchOutput;
  verdict:      DebateVerdict;
}

const REC_LABEL: Record<string, string> = {
  strong_buy:  "STRONG BUY",
  buy:         "BUY",
  hold:        "HOLD",
  sell:        "SELL",
  strong_sell: "STRONG SELL",
};

const REC_COLOR: Record<string, string> = {
  strong_buy:  "bg-[#22c55e33] text-green border-[#22c55e55]",
  buy:         "bg-[#22c55e22] text-green border-[#22c55e44]",
  hold:        "bg-[#f59e0b22] text-yellow border-[#f59e0b44]",
  sell:        "bg-[#ef444422] text-red border-[#ef444433]",
  strong_sell: "bg-[#ef444433] text-red border-[#ef444455]",
};

export function Stage2Research({ bullCase, bearCase, verdict }: Props) {
  return (
    <div className="p-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        {/* Bull */}
        <div className="bg-[#22c55e0d] border border-[#22c55e33] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-green text-bg">BULL</span>
            <span className="text-xs font-mono text-green">Confidence: {Math.round(bullCase.confidence * 100)}%</span>
          </div>
          <p className="text-xs text-[#94a3b8] leading-relaxed mb-3">{bullCase.thesis}</p>
          <div className="flex flex-col gap-1.5">
            {bullCase.key_arguments.map((a, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-[#94a3b8]">
                <span className="text-green mt-0.5 flex-shrink-0">▲</span>{a}
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-[#22c55e22] flex justify-between text-xs">
            <span className="text-[#8391a7]">Score</span>
            <span className="font-bold font-mono text-green">{verdict.bull_score.toFixed(1)} / 10</span>
          </div>
        </div>

        {/* Bear */}
        <div className="bg-[#ef44440d] border border-[#ef444433] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red text-white">BEAR</span>
            <span className="text-xs font-mono text-red">Confidence: {Math.round(bearCase.confidence * 100)}%</span>
          </div>
          <p className="text-xs text-[#94a3b8] leading-relaxed mb-3">{bearCase.thesis}</p>
          <div className="flex flex-col gap-1.5">
            {bearCase.key_arguments.map((a, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-[#94a3b8]">
                <span className="text-red mt-0.5 flex-shrink-0">▼</span>{a}
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-[#ef444422] flex justify-between text-xs">
            <span className="text-[#8391a7]">Score</span>
            <span className="font-bold font-mono text-red">{verdict.bear_score.toFixed(1)} / 10</span>
          </div>
        </div>
      </div>

      {/* Moderator Verdict */}
      <div className="bg-bg border border-[#1e2d45] rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-[#8391a7] tracking-widest">MODERATOR VERDICT</span>
          <div className="flex items-center gap-2">
            <span className={cn("text-xs font-bold px-3 py-1 rounded border", REC_COLOR[verdict.final_recommendation])}>
              {REC_LABEL[verdict.final_recommendation]}
            </span>
            <span className="text-xs text-[#8391a7]">Winner: {verdict.winner.toUpperCase()}</span>
          </div>
        </div>
        <p className="text-xs text-[#94a3b8] leading-relaxed mb-3">{verdict.rationale}</p>
        {verdict.key_consensus_points.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-[#8391a7] mb-1.5 tracking-wide">CONSENSUS</div>
            {verdict.key_consensus_points.map((p, i) => (
              <div key={i} className="text-xs text-green flex gap-2">
                <span>✓</span>{p}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
