import { cn, formatINR } from "@/lib/utils";
import type { FinalDecision } from "@/types/pipeline";

interface Props { decision: FinalDecision; }

const ACTION_STYLE = {
  execute: { label: "EXECUTE", bg: "bg-[#22c55e22] border-[#22c55e66]", text: "text-green",  glow: "0 0 24px rgba(34,197,94,0.3)"  },
  hold:    { label: "HOLD",    bg: "bg-[#f59e0b22] border-[#f59e0b66]", text: "text-yellow", glow: "0 0 24px rgba(245,158,11,0.3)" },
  reject:  { label: "REJECT",  bg: "bg-[#ef444422] border-[#ef444466]", text: "text-red",    glow: "0 0 24px rgba(239,68,68,0.3)"  },
};

export function Stage5Decision({ decision }: Props) {
  const style = ACTION_STYLE[decision.action] ?? ACTION_STYLE.hold;

  return (
    <div className="p-5">
      {/* Big action badge */}
      <div className="flex items-center gap-6 mb-5">
        <div
          className={cn("text-4xl font-black px-8 py-4 rounded-2xl border-2 tracking-widest", style.bg, style.text)}
          style={{ boxShadow: style.glow }}
        >
          {style.label}
        </div>
        <div className="flex flex-col gap-2">
          <div className="text-xs text-[#8391a7]">Portfolio Manager decision based on consensus from all 3 risk managers</div>
          <div className="text-xs text-[#94a3b8] leading-relaxed max-w-md">{decision.risk_consensus}</div>
        </div>
      </div>

      {/* Final parameters */}
      {decision.action === "execute" && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          {[
            { label: "Entry",         val: formatINR(decision.final_entry) },
            { label: "Stop Loss",     val: formatINR(decision.final_stop_loss), color: "text-red" },
            { label: "Take Profit",   val: formatINR(decision.final_take_profit), color: "text-green" },
            { label: "Position Size", val: decision.final_position_size_pct != null ? decision.final_position_size_pct.toFixed(1) + "%" : "—", color: "text-[#ff9933]" },
          ].map(({ label, val, color }) => (
            <div key={label} className="bg-bg border border-[#1e2d45] rounded-lg p-3 text-center">
              <div className="text-xs text-[#8391a7] mb-1">{label}</div>
              <div className={cn("font-mono font-bold text-sm", color ?? "text-[#e2e8f0]")}>{val}</div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-bg border border-[#1e2d45] rounded-lg p-4">
        <div className="text-xs font-semibold text-[#8391a7] tracking-wide mb-2">REASONING</div>
        <p className="text-xs text-[#94a3b8] leading-relaxed">{decision.reasoning}</p>
      </div>
    </div>
  );
}
