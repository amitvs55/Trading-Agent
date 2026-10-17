import { cn } from "@/lib/utils";
import type { RiskAssessment } from "@/types/pipeline";

interface Props { assessments: RiskAssessment[]; }

const PROFILE_STYLE = {
  aggressive:   { label: "Aggressive",   color: "text-red",    border: "border-[#ef444433]", bg: "bg-[#ef44440d]" },
  neutral:      { label: "Neutral",      color: "text-yellow", border: "border-[#f59e0b33]", bg: "bg-[#f59e0b0d]" },
  conservative: { label: "Conservative", color: "text-green",  border: "border-[#22c55e33]", bg: "bg-[#22c55e0d]" },
};

function riskColor(score: number) {
  if (score >= 7) return "text-red";
  if (score >= 4) return "text-yellow";
  return "text-green";
}

export function Stage4RiskAssessment({ assessments }: Props) {
  return (
    <div className="p-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {assessments.map(a => {
          const style = PROFILE_STYLE[a.profile] ?? PROFILE_STYLE.neutral;
          return (
            <div key={a.profile} className={cn("border rounded-xl p-4", style.border, style.bg)}>
              <div className="flex items-center justify-between mb-3">
                <span className={cn("text-xs font-bold uppercase tracking-wide", style.color)}>{style.label}</span>
                <span className={cn(
                  "text-[10px] font-bold px-2 py-0.5 rounded",
                  a.approve ? "bg-[#22c55e22] text-green" : "bg-[#ef444422] text-red"
                )}>
                  {a.approve ? "APPROVED" : "REJECTED"}
                </span>
              </div>

              {/* Risk score */}
              <div className="mb-3">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-[#8391a7]">Risk Score</span>
                  <span className={cn("font-bold font-mono", riskColor(a.risk_score))}>{a.risk_score.toFixed(1)} / 10</span>
                </div>
                <div className="h-1.5 bg-[#1e2d45] rounded">
                  <div className="h-1.5 rounded" style={{
                    width: `${a.risk_score * 10}%`,
                    background: a.risk_score >= 7 ? "#ef4444" : a.risk_score >= 4 ? "#f59e0b" : "#22c55e"
                  }} />
                </div>
              </div>

              <div className="flex justify-between text-xs mb-3">
                <span className="text-[#8391a7]">Max Position</span>
                <span className="font-mono font-semibold text-[#e2e8f0]">{a.max_position_size_pct.toFixed(1)}%</span>
              </div>

              {a.concerns.length > 0 && (
                <div className="flex flex-col gap-1.5 mb-3">
                  {a.concerns.slice(0, 3).map((c, i) => (
                    <div key={i} className="text-[10px] text-[#94a3b8] flex gap-1.5">
                      <span className="text-red flex-shrink-0">•</span>{c}
                    </div>
                  ))}
                </div>
              )}

              <p className="text-[10px] text-[#8391a7] leading-relaxed border-t border-[#1e2d4566] pt-2">{a.recommendation}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
