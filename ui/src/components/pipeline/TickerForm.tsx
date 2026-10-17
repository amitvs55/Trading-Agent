"use client";
import { useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PipelineStatus } from "@/types/pipeline";

const QUICK_PICKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "WIPRO", "ICICIBANK"];

interface Props {
  status:        PipelineStatus;
  onAnalyze:     (ticker: string, exchange: string) => void;
  onReset:       () => void;
  lastTicker?:   string;
  totalRuns:     number;
  lastDuration?: number;
}

export function TickerForm({ status, onAnalyze, onReset, lastTicker, totalRuns, lastDuration }: Props) {
  const [ticker,   setTicker]   = useState("RELIANCE");
  const [exchange, setExchange] = useState("NSE");
  const running = status === "running";

  function submit() {
    const t = ticker.trim().toUpperCase();
    if (!t || running) return;
    onAnalyze(t, exchange);
  }

  return (
    <section className="mb-6">
      <div className="bg-surface border border-[#1e2d45] rounded-xl px-4 sm:px-6 py-5 flex items-center gap-4 sm:gap-5 flex-wrap">

        {/* Title */}
        <div className="min-w-0 sm:flex-shrink-0">
          <h1 className="text-lg font-bold text-[#e2e8f0]">Indian Market Analysis</h1>
          <p className="text-xs mt-0.5 text-[#8391a7]">NSE/BSE · Enter symbol (RELIANCE, TCS, INFY…) · SEBI regulated</p>
        </div>

        <div className="hidden sm:block w-px h-9 bg-[#1e2d45]" />

        {/* Controls: on phones the symbol field takes the free width and nothing overflows */}
        <div className="flex items-center gap-2 sm:gap-3 w-full sm:w-auto">
          {/* Exchange */}
          <select
            aria-label="Exchange"
            value={exchange}
            onChange={e => setExchange(e.target.value)}
            disabled={running}
            className="bg-bg border border-[#1e2d45] rounded-lg px-3 py-2.5 text-xs font-semibold text-[#94a3b8] outline-none cursor-pointer disabled:opacity-50 focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]"
          >
            <option>NSE</option>
            <option>BSE</option>
          </select>

          {/* Input */}
          <div className="relative flex-1 min-w-0 sm:flex-none">
            <input
              type="text"
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === "Enter" && submit()}
              disabled={running}
              maxLength={20}
              placeholder="RELIANCE"
              className={cn(
                "bg-bg border rounded-lg px-3 py-2.5 font-mono text-base font-bold tracking-widest outline-none w-full sm:w-44 transition-colors disabled:opacity-50",
                running
                  ? "border-[#ff9933] text-[#ff9933]"
                  : "border-[#1e2d45] text-[#ff9933] focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]"
              )}
            />
          </div>

          {/* Analyse button */}
          <button
            onClick={submit}
            disabled={running}
            className={cn(
              "flex items-center gap-2 px-4 sm:px-6 py-2.5 rounded-lg font-bold text-sm text-white transition-opacity flex-shrink-0",
              running ? "opacity-60 cursor-not-allowed" : "hover:opacity-85 cursor-pointer"
            )}
            style={{ background: "linear-gradient(135deg,#ff9933,#cc6600)" }}
          >
            {running
              ? <><RefreshCw size={13} className="animate-spin" />Analysing…</>
              : <><Play size={13} />Analyse</>}
          </button>

          {/* Reset */}
          {status !== "idle" && !running && (
            <button
              onClick={onReset}
              className="text-xs text-[#8391a7] hover:text-[#e2e8f0] px-3 py-2.5 rounded-lg border border-[#1e2d45] bg-card transition-colors"
            >
              Reset
            </button>
          )}
        </div>

        {/* Quick picks */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-[#8391a7]">Quick:</span>
          {QUICK_PICKS.map(t => (
            <button
              key={t}
              onClick={() => { setTicker(t); }}
              disabled={running}
              className="text-xs font-mono px-2 py-1 rounded bg-card border border-[#ff993322] text-[#ff9933] hover:border-[#ff993366] transition-colors disabled:opacity-40"
            >
              {t}
            </button>
          ))}
        </div>

        {/* Stats */}
        <div className="sm:ml-auto flex items-center gap-6">
          {lastTicker && (
            <div className="text-center">
              <div className="text-xs text-[#8391a7]">Last Run</div>
              <div className="text-sm font-semibold text-[#e2e8f0]">{lastTicker}</div>
            </div>
          )}
          {lastDuration != null && (
            <div className="text-center">
              <div className="text-xs text-[#8391a7]">Duration</div>
              <div className="text-sm font-semibold font-mono text-[#e2e8f0]">{lastDuration.toFixed(1)}s</div>
            </div>
          )}
          <div className="text-center">
            <div className="text-xs text-[#8391a7]">Total Runs</div>
            <div className="text-sm font-semibold text-[#e2e8f0]">{totalRuns}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
