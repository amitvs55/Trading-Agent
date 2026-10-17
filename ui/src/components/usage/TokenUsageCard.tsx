"use client";
import { Coins, AlertTriangle } from "lucide-react";
import type { UsageSummary, PipelineStatus } from "@/types/pipeline";
import { formatINR, formatTokens, formatUSD, USD_INR } from "@/lib/utils";

const STAGE_NAMES: Record<string, string> = {
  "1": "Data Collection",
  "2": "Research Debate",
  "3": "Trade Proposal",
  "4": "Risk Assessment",
  "5": "Portfolio Decision",
  "6": "Execution",
};

interface Props {
  usage:  UsageSummary | null;
  status: PipelineStatus;
}

export function TokenUsageCard({ usage, status }: Props) {
  const cost    = usage?.cost_usd ?? 0;
  const agents  = Object.entries(usage?.by_agent ?? {}).sort((a, b) => b[1].cost_usd - a[1].cost_usd);
  const stages  = Object.entries(usage?.by_stage ?? {}).sort((a, b) => a[0].localeCompare(b[0]));
  const maxStageCost = Math.max(...stages.map(([, s]) => s.cost_usd), 0);

  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2d45]">
        <div className="flex items-center gap-2">
          <Coins size={13} className="text-[#ff9933]" />
          <span className="text-xs font-semibold text-[#e2e8f0]">OpenAI Usage</span>
          {status === "running" && (
            <span className="flex items-center gap-1 text-[10px] text-[#8391a7]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#ff9933] animate-pulse" /> live
            </span>
          )}
        </div>
        <span className="bg-bg text-[#94a3b8] text-[10px] font-mono px-1.5 py-0.5 rounded border border-[#1e2d45]">
          {usage?.model ?? "—"}
        </span>
      </div>

      <div className="p-4">
        {/* Run cost */}
        <div className="flex items-end justify-between mb-4">
          <div>
            <div className="text-[10px] text-[#8391a7] tracking-widest mb-1">THIS RUN</div>
            <div className="font-mono font-bold text-3xl text-[#e2e8f0] leading-none">{formatUSD(cost)}</div>
            <div className="font-mono text-[11px] text-[#8391a7] mt-1.5">≈ {formatINR(cost * USD_INR)}</div>
          </div>
          <div className="text-right">
            <div className="font-mono text-sm font-bold text-[#e2e8f0]">{usage?.calls ?? 0}</div>
            <div className="text-[10px] text-[#8391a7]">LLM calls{usage?.retries ? ` · ${usage.retries} retry` : ""}</div>
          </div>
        </div>

        {usage && !usage.pricing_known && (
          <div className="flex items-start gap-2 mb-4 bg-[#f59e0b11] border border-[#f59e0b33] rounded-lg px-3 py-2 text-[11px] text-yellow">
            <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
            <span>No price for <span className="font-mono">{usage.model}</span>; cost shows $0. Set OPENAI_PRICE_INPUT_PER_1M / OUTPUT_PER_1M.</span>
          </div>
        )}

        {/* Token counts */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          {[
            { label: "Input",  val: usage?.prompt_tokens },
            { label: "Output", val: usage?.completion_tokens },
            { label: "Cached", val: usage?.cached_tokens },
            { label: "Total",  val: usage?.total_tokens },
          ].map(({ label, val }) => (
            <div key={label} className="bg-card rounded-lg px-2 py-2 text-center">
              <div className="font-mono text-xs font-bold text-[#e2e8f0]">{formatTokens(val ?? 0)}</div>
              <div className="text-[9px] text-[#8391a7] mt-0.5">{label}</div>
            </div>
          ))}
        </div>

        {/* Per stage */}
        {stages.length > 0 && (
          <div className="mb-4">
            <div className="text-[10px] text-[#8391a7] tracking-widest mb-2">BY STAGE</div>
            <div className="flex flex-col gap-1.5">
              {stages.map(([stage, s]) => (
                <div key={stage} className="flex items-center gap-2 text-[11px]">
                  <span className="w-28 truncate text-[#94a3b8]">{STAGE_NAMES[stage] ?? `Stage ${stage}`}</span>
                  <div className="flex-1 h-1.5 bg-card rounded overflow-hidden">
                    <div className="h-full bg-[#ff9933] rounded"
                         style={{ width: `${maxStageCost > 0 ? (s.cost_usd / maxStageCost) * 100 : 0}%` }} />
                  </div>
                  <span className="w-14 text-right font-mono text-[#e2e8f0]">{formatUSD(s.cost_usd)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Per agent */}
        {agents.length > 0 ? (
          <div>
            <div className="text-[10px] text-[#8391a7] tracking-widest mb-2">BY AGENT</div>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[#8391a7] text-[9px] tracking-widest">
                  <th className="text-left font-semibold pb-1">AGENT</th>
                  <th className="text-right font-semibold pb-1">TOKENS</th>
                  <th className="text-right font-semibold pb-1">COST</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(([name, a]) => (
                  <tr key={name} className="border-t border-[#1e2d4530]">
                    <td className="py-1 text-[#94a3b8]">{name.replace(/_/g, " ")}{a.calls > 1 ? <span className="text-[#8391a7]"> ×{a.calls}</span> : null}</td>
                    <td className="py-1 text-right font-mono text-[#94a3b8]">{formatTokens(a.total_tokens)}</td>
                    <td className="py-1 text-right font-mono text-[#e2e8f0]">{formatUSD(a.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-[11px] text-[#8391a7] text-center py-2">
            {status === "running" ? "Waiting for the first stage to finish…" : "No LLM calls recorded"}
          </div>
        )}
      </div>
    </div>
  );
}
