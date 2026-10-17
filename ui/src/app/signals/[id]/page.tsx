"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Gauge, ListChecks, ScrollText } from "lucide-react";
import type { SignalDetail } from "@/types/options";
import { useOptionsApi } from "@/lib/optionsApi";
import { fmtDateTime, fmtPremium, fmtR, fmtRupees } from "@/lib/optionsFormat";
import { SignalCard } from "@/components/options/SignalCard";
import { ChecksList } from "@/components/options/ChecksList";
import { SignalCardSkeleton } from "@/components/options/Skeletons";
import { ConfidenceBreakdown, ConfidenceMeter } from "@/components/options/Confidence";

const KIND_LABELS: Record<string, string> = {
  CREATED: "Signal created", ENTRY_FILLED: "Entry filled", T1_HIT: "Target 1 reached", T2_HIT: "Target 2 reached",
  SL_HIT: "Stop-loss hit", TRAIL_STOP: "Trailing stop hit", INVALIDATED: "Invalidated", TIME_STOP: "Time stop",
  SQUARE_OFF: "Square-off", EXPIRED: "Expired unfilled", CANCELLED: "Cancelled", EXIT_SIGNAL: "Exit: opposite signal",
  EVENT_EXIT: "Exit: event window",
};

export default function SignalDetailPage() {
  const params = useParams<{ id: string }>();          // Next 16: a page's params prop is a Promise
  const { data, error } = useOptionsApi<SignalDetail>(`/api/options/signals/${encodeURIComponent(params.id)}`, 10_000);
  const s = data?.signal;

  return (
    <>
      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-6">
        <Link href="/signals" className="inline-flex items-center gap-1.5 text-xs text-[#94a3b8] hover:text-[#e2e8f0] mb-4">
          <ArrowLeft size={13} /> Live signals
        </Link>
        {!s && error && "status" in error && (error as { status: number }).status === 404 ? (
          <div className="fade-in bg-surface border border-[#1e2d45] rounded-xl px-6 py-12 text-center text-sm text-[#94a3b8]">
            Signal {params.id} doesn&apos;t exist.
          </div>
        ) : !s ? (
          <div className="grid gap-5 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px]" aria-hidden>
            <SignalCardSkeleton />
            <div className="skeleton h-80 rounded-xl" />
          </div>
        ) : (
          <div className="fade-in grid gap-5 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px]">
            <h1 className="sr-only">Signal {s.signal_id}: {s.action.replace("_", " ")} {s.contract.tradingsymbol}</h1>
            <div className="flex flex-col gap-5 min-w-0">
              <SignalCard s={s} setupLabel={data.setup_label} wide showConfidence={false} />
              {s.confidence && (
                <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center gap-2">
                    <Gauge size={13} className="text-[#ff9933]" />
                    <span className="text-xs font-semibold text-[#e2e8f0]">Confidence</span>
                    <span className="text-[10px] text-[#8391a7]">where each of the {s.confidence.max} points came from</span>
                  </div>
                  <div className="p-4 flex flex-col gap-4">
                    <ConfidenceMeter c={s.confidence} />
                    <ConfidenceBreakdown c={s.confidence} />
                  </div>
                </section>
              )}
              <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center gap-2">
                  <ListChecks size={13} className="text-[#ff9933]" />
                  <span className="text-xs font-semibold text-[#e2e8f0]">Analysis at signal time</span>
                  <span className="text-[10px] text-[#8391a7]">all 13 checks, including the ones that disagreed</span>
                </div>
                <div className="px-4"><ChecksList checks={s.checks} /></div>
              </section>
            </div>

            <aside className="flex flex-col gap-5 min-w-0">
              <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center gap-2">
                  <ScrollText size={13} className="text-[#ff9933]" />
                  <span className="text-xs font-semibold text-[#e2e8f0]">Lifecycle</span>
                </div>
                <ol className="px-4 py-3 relative">
                  {data.events.map((e, i) => (
                    <li key={e.id} className="relative pl-6 pb-4 last:pb-0">
                      {i < data.events.length - 1 && <span className="absolute left-[5px] top-3 bottom-0 w-px bg-[#1e2d45]" />}
                      <span className="absolute left-0 top-1 w-[11px] h-[11px] rounded-full border-2 border-[#ff9933] bg-[#111827]" />
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[#e2e8f0]">{KIND_LABELS[e.kind] ?? e.kind}</span>
                        <span className="font-mono text-[10px] text-[#8391a7]">{fmtDateTime(e.ts)}</span>
                      </div>
                      <p className="text-[11px] text-[#94a3b8] mt-0.5">{e.message}</p>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="bg-surface border border-[#1e2d45] rounded-xl p-4">
                <div className="text-xs font-semibold text-[#e2e8f0] mb-3">Result</div>
                <dl className="grid grid-cols-2 gap-y-2.5 text-[12px]">
                  <dt className="text-[#8391a7]">Fill (ask)</dt><dd className="text-right font-mono text-[#e2e8f0]">{fmtPremium(s.fill_price)}</dd>
                  <dt className="text-[#8391a7]">Exit (bid)</dt><dd className="text-right font-mono text-[#e2e8f0]">{fmtPremium(s.exit_price)}</dd>
                  <dt className="text-[#8391a7]">Units</dt><dd className="text-right font-mono text-[#e2e8f0]">{s.lots * s.contract.lot_size}</dd>
                  <dt className="text-[#8391a7]">Risk at entry</dt><dd className="text-right font-mono text-[#e2e8f0]">{fmtRupees(s.risk_rupees)}</dd>
                  <dt className="text-[#8391a7]">Net P&amp;L after charges</dt>
                  <dd className="text-right font-mono font-bold text-[#e2e8f0]">{fmtRupees(s.pnl_rupees, true)}</dd>
                  <dt className="text-[#8391a7]">R multiple</dt><dd className="text-right font-mono text-[#e2e8f0]">{fmtR(s.r_multiple)}</dd>
                </dl>
                <p className="text-[10px] text-[#8391a7] mt-3 leading-relaxed">
                  Entry is assumed at the live ask, exits at the live bid. Charges include brokerage, STT (0.15% on sell
                  premium), exchange, SEBI, stamp duty and GST.
                </p>
              </section>
            </aside>
          </div>
        )}
      </main>
    </>
  );
}
