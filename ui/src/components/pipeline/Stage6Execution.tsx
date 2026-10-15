import { cn } from "@/lib/utils";
import type { ExecutionResult } from "@/types/pipeline";
import { format } from "date-fns";

interface Props { execution: ExecutionResult; }

const STATUS_STYLE = {
  executed_simulated: { label: "EXECUTED (Simulated)",  bg: "bg-[#22c55e22] border-[#22c55e44]", text: "text-green"  },
  held:               { label: "HELD",                  bg: "bg-[#f59e0b22] border-[#f59e0b44]", text: "text-yellow" },
  rejected:           { label: "REJECTED",              bg: "bg-[#ef444422] border-[#ef444433]", text: "text-red"    },
};

export function Stage6Execution({ execution }: Props) {
  const style = STATUS_STYLE[execution.status] ?? STATUS_STYLE.held;

  return (
    <div className="p-5">
      <div className="flex items-center gap-4 mb-4">
        <span className={cn("text-xs font-bold px-3 py-1.5 rounded-lg border", style.bg, style.text)}>
          {style.label}
        </span>
        <div>
          <div className="text-xs text-[#64748b]">Order ID</div>
          <div className="font-mono text-sm font-semibold text-[#e2e8f0]">{execution.order_id}</div>
        </div>
        <div>
          <div className="text-xs text-[#64748b]">Logged At (IST)</div>
          <div className="font-mono text-xs text-[#94a3b8]">
            {(() => { try { return format(new Date(execution.logged_at), "dd MMM yyyy HH:mm:ss"); } catch { return execution.logged_at; } })()}
          </div>
        </div>
      </div>

      <div className="bg-bg border border-[#1e2d45] rounded-lg p-4">
        <div className="text-xs font-semibold text-[#64748b] tracking-wide mb-2">EXECUTION DETAILS</div>
        <p className="text-xs text-[#94a3b8] leading-relaxed">{execution.details}</p>
      </div>

      <div className="mt-3 text-xs text-[#475569]">
        * This is a paper trade simulation. No real orders were placed on NSE/BSE.
      </div>
    </div>
  );
}
