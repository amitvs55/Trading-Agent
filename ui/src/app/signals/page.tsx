"use client";
import { Radio, RefreshCw, Satellite } from "lucide-react";
import type { BoardResponse, EvaluationsResponse, OptionsStatus, SignalsResponse } from "@/types/options";
import { useOptionsApi } from "@/lib/optionsApi";
import { istDateKey, todayIST } from "@/lib/optionsFormat";
import { SessionBar } from "@/components/options/SessionBar";
import { IndexBoard } from "@/components/options/IndexBoard";
import { SignalCard } from "@/components/options/SignalCard";
import { NoTradeLog } from "@/components/options/NoTradeLog";

const OPEN = new Set(["TRIGGERED", "ACTIVE", "T1_HIT"]);

export default function SignalsPage() {
  const status = useOptionsApi<OptionsStatus>("/api/options/status", 30_000);
  const boards = useOptionsApi<BoardResponse>("/api/options/board", 15_000);
  const signals = useOptionsApi<SignalsResponse>("/api/options/signals?days=7", 5_000);
  const evals = useOptionsApi<EvaluationsResponse>("/api/options/evaluations?hours=12", 30_000);
  const needsLogin = status.needsLogin || boards.needsLogin || signals.needsLogin;

  const all = signals.data?.signals ?? [];
  const labels = signals.data?.setup_labels ?? {};
  const open = all.filter(s => OPEN.has(s.state));
  const today = todayIST();
  const closedToday = all.filter(s => !OPEN.has(s.state) && istDateKey(s.created_at) === today);
  const boardList = Object.values(boards.data?.boards ?? {});
  const error = status.error || boards.error || signals.error;
  const boardsLoading = !boards.data && !boards.error;
  const signalsLoading = !signals.data && !signals.error;

  return (
    <>
      <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
        <div className="mb-5 flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5">
              <Radio size={20} className="text-[#ff9933]" /> Live Signals
            </h1>
            <p className="text-sm text-[#64748b] mt-1">
              NIFTY options · buy-only · every signal checked against 12 analysis pillars and tracked to its result
            </p>
          </div>
          <button onClick={() => { status.refresh(); boards.refresh(); signals.refresh(); evals.refresh(); }}
                  className="flex items-center gap-1.5 bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-xs text-[#94a3b8] hover:text-[#e2e8f0] transition-colors">
            <RefreshCw size={11} className={signals.isLoading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>

        {error && !needsLogin && (
          <div className="mb-4 bg-[#ef444411] border border-[#ef444433] rounded-xl px-5 py-3 text-sm text-red">
            ⚠ Could not reach the signal API: {error.message}. Showing the last data received.
          </div>
        )}

        <div className="mb-5"><SessionBar status={status.data} /></div>

        <div className="grid gap-5 grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_480px]">
          <div className="flex flex-col gap-5 min-w-0">
            {boardsLoading ? <div className="skeleton h-[520px] rounded-xl" /> :
             boardList.length ? boardList.map(b => <IndexBoard key={b.index} board={b} />) : (
              <section className="bg-surface border border-[#1e2d45] rounded-xl px-6 py-14 text-center">
                <Satellite size={28} className="mx-auto text-[#334155] mb-3" />
                <div className="text-sm font-semibold text-[#e2e8f0]">No analysis yet</div>
                <p className="text-xs text-[#64748b] mt-1.5 max-w-md mx-auto leading-relaxed">
                  The board fills in after the first 5-minute close of a session (09:20 IST), once market data is connected and
                  the recorder is running.
                </p>
              </section>
            )}
          </div>

          <aside className="flex flex-col gap-4 min-w-0 order-first 2xl:order-none" aria-label="Open signals">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#e2e8f0]">Open signals <span className="text-[#64748b] font-normal">({open.length})</span></h2>
              <span className="text-[10px] text-[#64748b]">updates every 5s</span>
            </div>
            {signalsLoading ? <div className="skeleton h-72 rounded-xl" /> : open.length ? open.map(s => (
              <SignalCard key={s.signal_id} s={s} quote={signals.data?.quotes[s.signal_id]} setupLabel={labels[s.setup] ?? s.setup} />
            )) : (
              <div className="bg-surface border border-dashed border-[#1e2d45] rounded-xl px-5 py-10 text-center">
                <div className="text-sm text-[#e2e8f0] font-medium">No open signal</div>
                <p className="text-xs text-[#64748b] mt-1.5 leading-relaxed">
                  The engine checks every setup on each 5-minute close. When nothing meets every rule, the answer is
                  NO TRADE, and the decision log below says why.
                </p>
              </div>
            )}

            {closedToday.length > 0 && (
              <>
                <h2 className="text-sm font-semibold text-[#e2e8f0] mt-2">Closed today <span className="text-[#64748b] font-normal">({closedToday.length})</span></h2>
                {closedToday.map(s => <SignalCard key={s.signal_id} s={s} setupLabel={labels[s.setup] ?? s.setup} compact />)}
              </>
            )}
          </aside>
        </div>

        <div className="mt-5">
          <NoTradeLog rows={(evals.data?.evaluations ?? []).filter(r => istDateKey(r.ts) === today)} labels={evals.data?.setup_labels ?? labels} />
        </div>
      </main>
    </>
  );
}
