"use client";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PipelineStatus } from "@/types/pipeline";

const STAGES = [
  { n: 1, label: "Data Collection" },
  { n: 2, label: "Research Debate" },
  { n: 3, label: "Trade Proposal" },
  { n: 4, label: "Risk Assessment" },
  { n: 5, label: "Portfolio Mgr"  },
  { n: 6, label: "Execution"      },
];

interface Props {
  status:       PipelineStatus;
  currentStage: number;
  elapsed:      number;
  ticker?:      string;
}

export function PipelineProgress({ status, currentStage, elapsed, ticker }: Props) {
  function stageStatus(n: number): "done" | "running" | "pending" {
    if (currentStage > n) return "done";
    if (currentStage === n && status === "running") return "running";
    return "pending";
  }

  return (
    <section className="mb-6">
      <div className="bg-surface border border-[#1e2d45] rounded-xl px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs font-semibold text-[#64748b] tracking-widest">
            PIPELINE PROGRESS{ticker ? ` — ${ticker}` : ""}
          </span>
          {status === "running" && (
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full border-2 border-[#1e2d45] border-t-[#ff9933] animate-spin" />
              <span className="text-xs font-mono text-[#ff9933]">
                Stage {currentStage} · {elapsed.toFixed(1)}s elapsed
              </span>
            </div>
          )}
          {status === "done" && (
            <span className="text-xs text-green font-mono">✓ Complete in {elapsed.toFixed(1)}s</span>
          )}
        </div>

        <div className="flex items-center">
          {STAGES.map((s, i) => {
            const st = stageStatus(s.n);
            return (
              <div key={s.n} className="flex items-center flex-1">
                <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
                  {/* Circle */}
                  <div className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all",
                    st === "done"    && "border-green  bg-[#22c55e22]",
                    st === "running" && "border-[#ff9933] bg-[#ff993311] animate-stage-pulse",
                    st === "pending" && "border-[#1e2d45] bg-card",
                  )}>
                    {st === "done"    && <Check size={12} className="text-green" strokeWidth={3} />}
                    {st === "running" && <div className="w-3 h-3 rounded-full border-2 border-[#ff993333] border-t-[#ff9933] animate-spin" />}
                    {st === "pending" && <span className="text-xs font-bold text-[#64748b]">{s.n}</span>}
                  </div>
                  {/* Label */}
                  <span className={cn(
                    "text-xs whitespace-nowrap",
                    st === "done"    && "text-green font-medium",
                    st === "running" && "text-[#ff9933] font-medium",
                    st === "pending" && "text-[#64748b]",
                  )}>
                    {s.label}
                  </span>
                  <span className={cn("text-xs font-mono",
                    st === "done"    && "text-[#64748b]",
                    st === "running" && "text-[#ff9933]",
                    st === "pending" && "text-[#475569]",
                  )}>
                    {st === "running" ? "Running…" : st === "done" ? "✓" : "Pending"}
                  </span>
                </div>

                {/* Connector line */}
                {i < STAGES.length - 1 && (
                  <div className={cn(
                    "flex-1 h-0.5 mx-2 mb-8 transition-colors",
                    st === "done" ? "bg-green" : "bg-[#1e2d45]",
                  )} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
