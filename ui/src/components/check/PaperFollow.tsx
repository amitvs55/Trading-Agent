"use client";
import { useState } from "react";
import { Loader2, Wallet } from "lucide-react";
import type { PaperFollow } from "@/types/check";
import { sendJson } from "@/lib/optionsApi";
import { useLiveIndices } from "@/lib/liveIndices";
import { fmtDateTime, fmtPremium, fmtRupees } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";
import { pnlTone } from "./Money";

/** Follow a check as a paper trade: live P&L while the recorder streams the contract, close at the bid. */
export function PaperFollowCard({ checkId, symbol, paper, onChange, priced }: {
  checkId: string; symbol: string; paper: PaperFollow | null | undefined; onChange: (p: PaperFollow) => void; priced: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const live = useLiveIndices().levels[symbol];
  const open = paper && !paper.closed_at;
  const mark = open && live ? (live.bid ?? live.ltp) : null;
  const unrealised = open && mark != null && paper.entry && paper.units ? (mark - paper.entry) * paper.units : null;

  async function act(path: string) {
    setBusy(true);
    setError(null);
    try {
      const r = await sendJson<{ paper: PaperFollow }>(path, "POST", {});
      onChange(r.paper);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Didn't work, try again");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl p-4 flex flex-wrap items-center justify-between gap-3" aria-label="Paper trade">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2"><Wallet size={14} className="text-[#ff9933]" aria-hidden /> Paper trade</h3>
        <p className="text-[12px] text-[#94a3b8] mt-0.5">
          {!paper ? "Follow this check with virtual money: entry at the price above, tracked live, settled at expiry."
            : open ? <>Following {paper.units} qty from ₹{fmtPremium(paper.entry)}
                     {mark != null ? <> · now ₹{fmtPremium(mark)} · <span className={cn("font-mono font-semibold", pnlTone(unrealised))}>{fmtRupees(unrealised, true)}</span></>
                                   : " · live price appears during market hours"}</>
            : <>Closed at ₹{fmtPremium(paper.exit)} on {fmtDateTime(paper.closed_at)} ·{" "}
                <span className={cn("font-mono font-semibold", pnlTone(paper.pnl))}>{fmtRupees(paper.pnl, true)}</span> after charges</>}
        </p>
        {error && <p className="text-[11px] text-[#fca5a5] mt-1" role="alert">{error}</p>}
      </div>
      {(!paper || open) && (
        <button type="button" disabled={busy || (!paper && !priced)}
                onClick={() => act(paper ? `/api/options/check/${checkId}/paper/close` : `/api/options/check/${checkId}/paper`)}
                className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-[#ff993366] text-[#ff9933] text-[12px] font-medium hover:bg-[#ff99331a] disabled:opacity-50">
          {busy && <Loader2 size={13} className="animate-spin" aria-hidden />}
          {paper ? "Close at the bid" : "Follow as paper trade"}
        </button>
      )}
    </section>
  );
}
