"use client";
import { useState } from "react";
import { usePipelineStream } from "@/hooks/usePipelineStream";
import { useTradeHistory }   from "@/hooks/useTradeHistory";
import { TickerForm }        from "@/components/pipeline/TickerForm";
import { PipelineProgress }  from "@/components/pipeline/PipelineProgress";
import { StageCard }         from "@/components/pipeline/StageCard";
import { Stage1DataCollection } from "@/components/pipeline/Stage1DataCollection";
import { Stage2Research }    from "@/components/pipeline/Stage2Research";
import { Stage3TradeProposal }  from "@/components/pipeline/Stage3TradeProposal";
import { Stage4RiskAssessment } from "@/components/pipeline/Stage4RiskAssessment";
import { Stage5Decision }    from "@/components/pipeline/Stage5Decision";
import { Stage6Execution }   from "@/components/pipeline/Stage6Execution";
import { TechnicalChart }    from "@/components/charts/TechnicalChart";
import { SentimentGauge }    from "@/components/charts/SentimentGauge";
import { DebateScoreBar }    from "@/components/charts/DebateScoreBar";
import { RiskRadar }         from "@/components/charts/RiskRadar";
import { TradeHistoryTable } from "@/components/history/TradeHistoryTable";
import { TokenUsageCard }    from "@/components/usage/TokenUsageCard";
import { toYFTicker }        from "@/lib/utils";

const LIMIT = 10;

export default function DashboardPage() {
  const { state, startPipeline, reset } = usePipelineStream();
  const [activeTicker,   setActiveTicker]   = useState("");
  const [activeExchange, setActiveExchange] = useState("NSE");
  const { total } = useTradeHistory({ limit: 1 });            // run count for the form

  function handleAnalyze(ticker: string, exchange: string) {
    setActiveTicker(ticker);
    setActiveExchange(exchange);
    startPipeline(ticker, exchange);
  }

  const { stages, status, currentStage, elapsed, fullResult } = state;
  const yf = activeTicker ? toYFTicker(activeTicker, activeExchange) : "";

  function stageStatus(n: number): "pending" | "running" | "complete" {
    if (currentStage > n) return "complete";
    if (currentStage === n && status === "running") return "running";
    if (status === "done") return "complete";
    return "pending";
  }

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">

      {/* Ticker form */}
      <TickerForm
        status={status}
        onAnalyze={handleAnalyze}
        onReset={reset}
        lastTicker={fullResult?.ticker ?? undefined}
        totalRuns={total}
        lastDuration={fullResult?.total_duration_seconds}
      />

      {/* Pipeline progress — shown once analysis starts */}
      {status !== "idle" && (
        <PipelineProgress
          status={status}
          currentStage={currentStage}
          elapsed={elapsed}
          ticker={yf || undefined}
        />
      )}

      {/* Error banner */}
      {status === "error" && state.error && (
        <div className="mb-4 bg-[#ef444411] border border-[#ef444433] rounded-xl px-5 py-4 text-sm text-red">
          ⚠ {state.error}
        </div>
      )}

      {/* Two-column layout */}
      {status !== "idle" && (
        <div className="grid gap-5 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_390px]">

          {/* ── Left: Stage cards ── */}
          <div className="flex flex-col gap-4 min-w-0">

            {/* Stage 1 */}
            <StageCard
              stageNumber={1} title="Stage 1 — Data Collection"
              subtitle={`Market Data · Sentiment · News · Fundamentals${stages.stage1 ? " · 4 agents" : ""}`}
              status={stageStatus(1)} defaultOpen={true}
              badge={activeTicker ? <span className="bg-bg text-[#ff9933] font-mono text-xs font-bold px-2.5 py-1 rounded border border-[#ff993322]">{yf}</span> : undefined}
            >
              {stages.stage1 && (
                <Stage1DataCollection
                  market={stages.stage1.market}
                  sentiment={stages.stage1.sentiment}
                  news={stages.stage1.news}
                  fundamentals={stages.stage1.fundamentals}
                />
              )}
            </StageCard>

            {/* Stage 2 */}
            <StageCard
              stageNumber={2} title="Stage 2 — Research Debate"
              subtitle="Bull Researcher · Bear Researcher · Moderator"
              status={stageStatus(2)}
              badge={stages.stage2 ? (
                <span className={`text-xs font-bold px-2.5 py-1 rounded border ${
                  stages.stage2.debate_verdict.winner === "bull"
                    ? "bg-[#22c55e22] text-green border-[#22c55e44]"
                    : stages.stage2.debate_verdict.winner === "bear"
                    ? "bg-[#ef444422] text-red border-[#ef444433]"
                    : "bg-[#f59e0b22] text-yellow border-[#f59e0b44]"
                }`}>
                  {stages.stage2.debate_verdict.final_recommendation.replace("_", " ").toUpperCase()}
                </span>
              ) : undefined}
            >
              {stages.stage2 && (
                <Stage2Research
                  bullCase={stages.stage2.bull_case}
                  bearCase={stages.stage2.bear_case}
                  verdict={stages.stage2.debate_verdict}
                />
              )}
            </StageCard>

            {/* Stage 3 */}
            <StageCard
              stageNumber={3} title="Stage 3 — Trade Proposal"
              subtitle="TraderAgent · Entry · SL · TP · Position sizing"
              status={stageStatus(3)}
              badge={stages.stage3 ? (
                <span className={`text-xs font-black px-3 py-1 rounded border tracking-wide ${
                  stages.stage3.trade_proposal.direction === "long"  ? "bg-[#22c55e22] text-green border-[#22c55e44]" :
                  stages.stage3.trade_proposal.direction === "short" ? "bg-[#ef444422] text-red border-[#ef444433]" :
                  "bg-[#f59e0b22] text-yellow border-[#f59e0b44]"
                }`}>
                  {stages.stage3.trade_proposal.direction.toUpperCase()}
                </span>
              ) : undefined}
            >
              {stages.stage3 && <Stage3TradeProposal proposal={stages.stage3.trade_proposal} />}
            </StageCard>

            {/* Stage 4 */}
            <StageCard
              stageNumber={4} title="Stage 4 — Risk Assessment"
              subtitle="Aggressive · Neutral · Conservative (parallel)"
              status={stageStatus(4)}
            >
              {stages.stage4 && <Stage4RiskAssessment assessments={stages.stage4.risk_assessments} />}
            </StageCard>

            {/* Stage 5 */}
            <StageCard
              stageNumber={5} title="Stage 5 — Portfolio Decision"
              subtitle="Portfolio Manager · Final execute/hold/reject"
              status={stageStatus(5)}
              badge={stages.stage5 ? (
                <span className={`text-sm font-black px-3 py-1.5 rounded border ${
                  stages.stage5.final_decision.action === "execute" ? "bg-[#22c55e22] text-green border-[#22c55e55]" :
                  stages.stage5.final_decision.action === "reject"  ? "bg-[#ef444422] text-red border-[#ef444455]" :
                  "bg-[#f59e0b22] text-yellow border-[#f59e0b55]"
                }`}>
                  {stages.stage5.final_decision.action.toUpperCase()}
                </span>
              ) : undefined}
            >
              {stages.stage5 && <Stage5Decision decision={stages.stage5.final_decision} />}
            </StageCard>

            {/* Stage 6 */}
            <StageCard
              stageNumber={6} title="Stage 6 — Execution"
              subtitle="Execution Engine · NSE paper trade simulation"
              status={stageStatus(6)}
              badge={stages.stage6 ? (
                <span className="bg-[#22c55e22] text-green text-[10px] font-semibold px-2 py-0.5 rounded border border-[#22c55e33]">
                  {stages.stage6.execution.status.replace("_", " ").toUpperCase()}
                </span>
              ) : undefined}
            >
              {stages.stage6 && <Stage6Execution execution={stages.stage6.execution} />}
            </StageCard>
          </div>

          {/* ── Right: Charts panel ── */}
          <div className="flex flex-col gap-4 min-w-0">

            {/* OpenAI token usage + cost */}
            <TokenUsageCard usage={state.usage} status={status} />

            {/* Price Chart */}
            <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2d45]">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-[#e2e8f0]">Price Chart</span>
                  {yf && <span className="bg-bg text-[#ff9933] text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border border-[#ff993322]">{yf}</span>}
                  <span className="text-[10px] text-[#8391a7]">3 months · 1D</span>
                </div>
                <div className="flex items-center gap-3">
                  {[["#ff9933","Price"],["#f59e0b","SMA20"],["#f97316","SMA50"]].map(([c,l]) => (
                    <div key={l} className="flex items-center gap-1">
                      <div className="w-2 h-0.5" style={{ background: c }} />
                      <span className="text-[10px] text-[#8391a7]">{l}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="p-3">
                {yf
                  ? <TechnicalChart ticker={yf} proposal={stages.stage3?.trade_proposal} />
                  : <div className="h-48 flex items-center justify-center text-xs text-[#8391a7]">Enter a ticker to load chart</div>
                }
              </div>
            </div>

            {/* Sentiment Gauge */}
            {stages.stage1 && (
              <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e2d45]">
                  <span className="text-xs font-semibold text-[#e2e8f0]">Market Sentiment</span>
                  <span className="text-xs ml-2 text-[#8391a7]">Dalal Street · News analysis</span>
                </div>
                <div className="p-4 flex items-center gap-4">
                  <SentimentGauge score={stages.stage1.sentiment.overall_score} />
                  <div className="flex flex-col gap-2 flex-1">
                    {[
                      { label: "Overall",       val: stages.stage1.sentiment.overall_score },
                      { label: "Twitter / X",   val: stages.stage1.sentiment.twitter_score },
                      { label: "Reddit",         val: stages.stage1.sentiment.reddit_score  },
                    ].map(({ label, val }) => (
                      <div key={label} className="flex justify-between text-xs">
                        <span className="text-[#8391a7]">{label}</span>
                        <span className={`font-mono font-bold ${val != null && val >= 0 ? "text-green" : "text-red"}`}>
                          {val != null ? (val >= 0 ? "+" : "") + val.toFixed(2) : "—"}
                        </span>
                      </div>
                    ))}
                    <div className="text-[10px] text-[#8391a7] mt-1 border-t border-[#1e2d45] pt-2">{stages.stage1.sentiment.data_source}</div>
                  </div>
                </div>
              </div>
            )}

            {/* Debate scores */}
            {stages.stage2 && (
              <div className="bg-surface border border-[#1e2d45] rounded-xl p-4">
                <div className="text-xs font-semibold text-[#e2e8f0] mb-3">Research Debate Scores</div>
                <DebateScoreBar verdict={stages.stage2.debate_verdict} />
              </div>
            )}

            {/* Risk Radar */}
            {stages.stage4 ? (
              <div className="bg-surface border border-[#1e2d45] rounded-xl p-4">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs font-semibold text-[#e2e8f0]">Risk Comparison</div>
                  <div className="flex items-center gap-3">
                    {[["#ef4444","Aggressive"],["#f59e0b","Neutral"],["#22c55e","Conservative"]].map(([c,l]) => (
                      <div key={l} className="flex items-center gap-1">
                        <div className="w-2 h-0.5 rounded" style={{ background: c }} />
                        <span className="text-[9px] text-[#8391a7]">{l}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <RiskRadar assessments={stages.stage4.risk_assessments} />
              </div>
            ) : (
              <div className="bg-surface border border-[#1e2d45] rounded-xl p-4 opacity-40">
                <div className="text-xs font-semibold text-[#e2e8f0] mb-3">Risk Assessment Comparison</div>
                <div className="h-28 flex items-center justify-center">
                  <div className="text-center">
                    <div className="w-5 h-5 rounded-full border-2 border-[#1e2d45] border-t-[#64748b] animate-spin mx-auto mb-2" />
                    <div className="text-xs text-[#8391a7]">Awaiting Stage 4…</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Trade History */}
      <TradeHistoryTable limit={LIMIT} />
    </main>
  );
}
