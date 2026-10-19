"use client";
import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, Crosshair, Info, Loader2 } from "lucide-react";
import type { CheckResponse, ChecksResponse, PaperFollow } from "@/types/check";
import { ApiError, apiJson, sendJson, useOptionsApi } from "@/lib/optionsApi";
import { cn } from "@/lib/utils";
import { ContractInput } from "@/components/check/ContractInput";
import { VerdictCard } from "@/components/check/Verdict";
import { OddsPanel, PositionTiles } from "@/components/check/Money";
import { PayoffChart } from "@/components/check/PayoffChart";
import { ScenarioTable } from "@/components/check/Scenarios";
import { WhatIfPanel, type WhatIfValues } from "@/components/check/WhatIf";
import { EvidencePanel } from "@/components/check/Evidence";
import { CheckerRecord, RecentChecks } from "@/components/check/RecentChecks";
import { PaperFollowCard } from "@/components/check/PaperFollow";

const AMOUNTS = [10_000, 25_000, 50_000, 100_000];

export default function CheckPage() {
  return (
    <Suspense fallback={null}>
      <OptionCheck />
    </Suspense>
  );
}

function OptionCheck() {
  const params = useSearchParams();
  const [text, setText] = useState(() => params.get("q") ?? "");
  const [amount, setAmount] = useState(25_000);
  const [horizon, setHorizon] = useState<"intraday" | "expiry">("intraday");
  const [result, setResult] = useState<CheckResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [whatIf, setWhatIf] = useState<WhatIfValues | null>(null);
  const [whatIfBusy, setWhatIfBusy] = useState(false);
  const { data: checks, refresh: refreshChecks } = useOptionsApi<ChecksResponse>("/api/options/checks", 60_000);
  const resultsRef = useRef<HTMLDivElement>(null);
  const whatIfSeq = useRef(0);
  const shownId = useRef<string | null>(null);

  const show = useCallback((r: CheckResponse, scroll: boolean) => {
    shownId.current = r.id;
    setResult(r);
    const p = r.report.params;
    setWhatIf({ amount: p.amount, entry: p.entry, horizon: p.horizon, iv_shift: 0, slippage_pct: 0 });
    try { window.history.replaceState(null, "", `/check?id=${r.id}`); } catch { /* ignore */ }
    if (scroll) requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, []);

  const open = useCallback(async (id: string, scroll = true) => {
    setError(null);
    try {
      show(await apiJson<CheckResponse>(`/api/options/check/${id}`), scroll);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't open that check");
    }
  }, [show]);

  // A shared or reloaded link (?id=…) opens that check (not again for the one just shown)
  const idParam = params.get("id");
  useEffect(() => {
    if (idParam && idParam !== shownId.current) void open(idParam, false);
  }, [idParam, open]);

  async function run(e?: FormEvent) {
    e?.preventDefault();
    if (running || text.trim().length < 3) return;
    setRunning(true);
    setError(null);
    try {
      const r = await sendJson<CheckResponse>("/api/options/check", "POST", { query: text.trim(), amount, horizon });
      show(r, true);
      void refreshChecks();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "The check didn't run, try again");
    } finally {
      setRunning(false);
    }
  }

  // What-ifs: recomputed on the server from the saved facts, debounced; the old numbers stay until the new ones land
  useEffect(() => {
    if (!result || !whatIf) return;
    const p = result.report.params;
    const same = whatIf.amount === p.amount && whatIf.entry === p.entry && whatIf.horizon === p.horizon
      && whatIf.iv_shift === (p.iv_shift ?? 0) && whatIf.slippage_pct === (p.slippage_pct ?? 0);
    if (same) return;
    const mine = ++whatIfSeq.current;
    const t = setTimeout(async () => {
      setWhatIfBusy(true);
      try {
        const r = await sendJson<{ report: CheckResponse["report"] }>(`/api/options/check/${result.id}/whatif`, "POST", whatIf);
        if (mine === whatIfSeq.current) setResult(cur => (cur ? { ...cur, report: r.report } : cur));
      } catch { /* keep the last numbers */ } finally {
        if (mine === whatIfSeq.current) setWhatIfBusy(false);
      }
    }, 220);
    return () => clearTimeout(t);
  }, [whatIf, result]);

  const report = result?.report;
  const setPaper = (p: PaperFollow) => { setResult(cur => (cur ? { ...cur, paper: p } : cur)); void refreshChecks(); };

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><Crosshair size={20} className="text-[#ff9933]" /> Option Check</h1>
        <p className="text-sm text-[#8391a7] mt-1">
          Type a contract and an amount: every check the signals use, what the money can turn into, and the evidence for each number.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5 min-w-0">
          <form onSubmit={run} className="bg-surface border border-[#1e2d45] rounded-xl p-5" aria-label="Check a contract">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <ContractInput value={text} onChange={setText} onPick={setText} disabled={running} />
              <div>
                <label htmlFor="check-amount" className="text-[10px] tracking-widest text-[#8391a7]">AMOUNT</label>
                <div className="mt-1.5 flex items-center gap-2">
                  <span className="text-[#8391a7]">₹</span>
                  <input id="check-amount" type="number" inputMode="numeric" min={1000} step={1000} value={amount}
                         onChange={e => setAmount(Math.max(1, Number(e.target.value) || 0))} disabled={running}
                         className="w-full bg-card border border-[#1e2d45] rounded-lg px-3 h-11 text-[15px] font-mono text-[#e2e8f0] focus:outline-none focus:border-[#ff9933] focus:ring-2 focus:ring-[#ff993333]" />
                </div>
                <div className="hidden lg:block h-5 mt-1.5" aria-hidden />
                <div className="h-7 mt-1 flex items-center gap-1.5 overflow-x-auto">
                  {AMOUNTS.map(a => (
                    <button key={a} type="button" onClick={() => setAmount(a)} aria-pressed={amount === a}
                            className={cn("flex-shrink-0 h-6 px-2 rounded-md border text-[11px] font-mono",
                                          amount === a ? "border-[#ff993366] text-[#ff9933] bg-[#ff99330f]" : "border-[#1e2d45] text-[#94a3b8] bg-card hover:text-[#e2e8f0]")}>
                      ₹{a >= 100_000 ? `${a / 100_000}L` : `${a / 1000}k`}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex rounded-lg border border-[#1e2d45] p-0.5 bg-card" role="group" aria-label="Holding">
                {(["intraday", "expiry"] as const).map(h => (
                  <button key={h} type="button" aria-pressed={horizon === h} onClick={() => setHorizon(h)}
                          className={cn("h-8 px-3 rounded-md text-[12px] font-medium transition-colors",
                                        horizon === h ? "bg-[#ff99331f] text-[#ff9933]" : "text-[#94a3b8] hover:text-[#e2e8f0]")}>
                    {h === "intraday" ? "Intraday" : "Hold to expiry"}
                  </button>
                ))}
              </div>
              <button type="submit" disabled={running || text.trim().length < 3}
                      className="inline-flex items-center justify-center gap-2 h-10 min-w-[140px] px-5 rounded-lg bg-[#ff9933] text-[#0b0f1a] font-semibold text-sm hover:bg-[#ffa94d] disabled:opacity-50 disabled:cursor-not-allowed">
                {running ? <><Loader2 size={15} className="animate-spin" aria-hidden /> Checking…</> : "Check"}
              </button>
            </div>
            {error && (
              <p role="alert" className="mt-3 flex items-start gap-2 text-[12px] text-[#fcd34d] bg-[#f59e0b0d] border border-[#f59e0b33] rounded-lg px-3 py-2">
                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" aria-hidden /> {error}
              </p>
            )}
          </form>

          <div ref={resultsRef} className="scroll-mt-28 space-y-5" aria-busy={running}>
            {running && !report ? <ResultSkeleton /> : !report ? <EmptyState onTry={t => setText(t)} /> : (
              <>
                <VerdictCard report={report} />
                {report.priced ? (
                  <>
                    <PositionTiles report={report} />
                    <PaperFollowCard checkId={result!.id} symbol={report.facts.contract.symbol} paper={result!.paper}
                                     onChange={setPaper} priced={report.priced} />
                    <div className="grid gap-5 2xl:grid-cols-2">
                      <OddsPanel report={report} />
                      {whatIf && <WhatIfPanel values={whatIf} busy={whatIfBusy} defaultEntry={report.position?.entry_note ? report.position.entry : report.facts.contract.ask}
                                              entryHint={report.position?.entry_note ? "estimated next-open price" : "live ask"}
                                              onChange={v => setWhatIf(cur => (cur ? { ...cur, ...v } : cur))}
                                              onReset={() => { const p = report.params; setWhatIf({ amount: p.amount, entry: null, horizon: p.horizon, iv_shift: 0, slippage_pct: 0 }); }} />}
                    </div>
                    <PayoffChart report={report} />
                    <ScenarioTable report={report} />
                  </>
                ) : null}
                <EvidencePanel report={report} />
              </>
            )}
          </div>
        </div>

        <aside className="space-y-5 min-w-0">
          <RecentChecks data={checks} onOpen={id => void open(id)} activeId={result?.id} />
          <CheckerRecord data={checks} />
        </aside>
      </div>
    </main>
  );
}

function EmptyState({ onTry }: { onTry: (t: string) => void }) {
  return (
    <section className="bg-surface border border-dashed border-[#1e2d45] rounded-xl p-6">
      <div className="flex items-start gap-3">
        <Info size={16} className="text-[#60a5fa] mt-0.5 flex-shrink-0" aria-hidden />
        <div className="text-[13px] text-[#94a3b8] leading-relaxed">
          <p className="text-[#e2e8f0] font-medium">What you get</p>
          <ul className="mt-2 space-y-1 list-disc pl-4 marker:text-[#475569]">
            <li>A verdict (worth taking, marginal or avoid) with the reasons for and against.</li>
            <li>What your amount buys, the most you can lose, breakeven, and the chance of profit two ways: the
                options market&apos;s own pricing and how NIFTY really moved on past days.</li>
            <li>Every check, number and assumption behind it, and what-if sliders to change them.</li>
          </ul>
          <p className="mt-3">Try: {["Nifty 27th Oct 25000 ce", "25000 pe next week"].map((t, i) => (
            <button key={t} type="button" onClick={() => onTry(t)} className="font-mono text-[#ff9933] hover:underline">
              {i > 0 && <span className="text-[#475569] mx-1.5">·</span>}{t}
            </button>
          ))}</p>
        </div>
      </div>
    </section>
  );
}

function ResultSkeleton() {
  return (
    <div className="space-y-5" aria-label="Running the check">
      <div className="skeleton h-[220px] rounded-xl" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-[104px] rounded-xl" />)}</div>
      <div className="skeleton h-[260px] rounded-xl" />
    </div>
  );
}

