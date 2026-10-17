"use client";
import { useState } from "react";
import { OctagonX, PauseCircle, PlayCircle, Siren } from "lucide-react";
import type { ControlsState } from "@/types/auth";
import { cn } from "@/lib/utils";
import { sendJson } from "@/lib/optionsApi";
import { fmtDateTime } from "@/lib/optionsFormat";
import { Note, Panel } from "@/components/connectors/SideCards";

type NoteT = { tone: "ok" | "err"; text: string } | null;

/** Pause new signals, and the "exit everything" button, for when the market (or the tool) misbehaves. */
export function ControlsPanel({ controls, openCount, sessionRunning, onChange }: {
  controls: ControlsState | undefined; openCount: number; sessionRunning: boolean;
  onChange: (c: ControlsState) => void;
}) {
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState<"pause" | "exit" | null>(null);
  const [note, setNote] = useState<NoteT>(null);
  const paused = !!controls?.paused;

  const togglePause = async () => {
    setBusy("pause");
    setNote(null);
    try {
      const next = await sendJson<ControlsState>("/api/admin/controls/pause", "PUT", { paused: !paused, reason: paused ? "" : reason });
      onChange(next);
      setReason("");
      setNote({ tone: "ok", text: next.paused
        ? "Paused. No new signals from the next 5-minute check; open signals keep their stop-loss and target alerts. Telegram has been told."
        : "Resumed. New signals can go out from the next 5-minute check." });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Couldn't change it" });
    } finally {
      setBusy(null);
    }
  };

  const exitAll = async () => {
    setBusy("exit");
    setNote(null);
    try {
      onChange(await sendJson<ControlsState>("/api/admin/controls/exit-all", "POST", {}));
      setConfirming(false);
      setNote({ tone: "ok", text: sessionRunning
        ? "Requested. The session closes every open signal at the live bid within a few seconds and sends an exit alert for each. Exit your broker positions too."
        : "Requested. No session is running now, so it happens as soon as the next one starts. Exit your broker positions yourself now." });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Request failed" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Panel icon={<Siren size={14} className="text-[#ff9933]" />} title="Emergency controls"
           subtitle="For a surprise event, a bad data day or anything that doesn't look right. Both work across the API and the recorder, and survive restarts.">
      <div className={cn("flex items-start gap-3 rounded-lg border px-3.5 py-3",
        paused ? "border-[#ef444444] bg-[#ef44440f]" : "border-[#22c55e33] bg-[#22c55e0b]")}>
        {paused ? <PauseCircle size={18} className="text-red flex-shrink-0 mt-0.5" /> : <PlayCircle size={18} className="text-green flex-shrink-0 mt-0.5" />}
        <div className="min-w-0">
          <div className={cn("text-sm font-semibold", paused ? "text-[#fca5a5]" : "text-green")}>
            {!controls ? "Loading…" : paused ? "New signals are paused" : "New signals are on"}
          </div>
          <p className="text-[12px] text-[#94a3b8] mt-0.5 leading-snug">
            {paused
              ? <>by {controls?.paused_by ?? "admin"}{controls?.paused_at ? ` at ${fmtDateTime(controls.paused_at)}` : ""}{controls?.reason ? ` · ${controls.reason}` : ""}. Open signals are still tracked to their exits.</>
              : "Every 5-minute check can send a signal when a setup passes all the rules."}
          </p>
        </div>
      </div>

      {!paused && (
        <div className="mt-3">
          <label htmlFor="pause-reason" className="text-[11px] font-medium text-[#94a3b8]">Reason (optional, shown to everyone)</label>
          <input id="pause-reason" value={reason} onChange={e => setReason(e.target.value)} maxLength={200}
                 placeholder="e.g. RBI surprise, feed looks wrong"
                 className="mt-1.5 w-full bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-base lg:text-sm text-[#e2e8f0] placeholder:text-[#8391a7] outline-none focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]" />
        </div>
      )}
      <div className="mt-3">
        <button type="button" onClick={togglePause} disabled={!controls || busy !== null}
                className={cn("inline-flex items-center gap-2 h-10 rounded-lg px-4 text-sm font-semibold transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]",
                  paused ? "bg-green/90 hover:bg-green text-[#0b0f1a] focus-visible:ring-green" : "bg-[#dc2626] hover:bg-[#b91c1c] text-white focus-visible:ring-[#ef4444]")}>
          {paused ? <PlayCircle size={15} /> : <PauseCircle size={15} />}
          {busy === "pause" ? "Saving…" : paused ? "Resume new signals" : "Pause new signals"}
        </button>
      </div>

      <div className="mt-5 pt-4 border-t border-[#1e2d45]">
        <div className="text-[12px] font-semibold text-[#e2e8f0]">Exit all open signals</div>
        <p className="text-[12px] text-[#94a3b8] mt-1 leading-snug">
          Closes every open signal at the live bid (unfilled ones are cancelled) and sends an exit alert for each.
          It doesn&apos;t touch your broker account: exit your real positions there yourself.
        </p>
        {controls?.exit_all_pending && (
          <p className="mt-2 text-[12px] text-yellow">Requested at {fmtDateTime(controls.exit_all_pending)}; waiting for the session to carry it out.</p>
        )}
        {!confirming ? (
          <button type="button" onClick={() => setConfirming(true)} disabled={busy !== null || openCount === 0}
                  className="mt-3 inline-flex items-center gap-2 h-10 rounded-lg px-4 text-sm font-semibold border border-[#ef444466] text-[#fca5a5] hover:bg-[#ef444414] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ef4444]">
            <OctagonX size={15} /> {openCount ? `Exit all (${openCount} open)` : "No open signals"}
          </button>
        ) : (
          <div role="alertdialog" aria-labelledby="exit-all-q" className="mt-3 rounded-lg border border-[#ef444466] bg-[#ef44440f] px-3.5 py-3">
            <p id="exit-all-q" className="text-[13px] text-[#fca5a5] font-medium">
              Close {openCount} open signal{openCount === 1 ? "" : "s"} now?
            </p>
            <div className="mt-2.5 flex gap-2">
              <button type="button" onClick={exitAll} disabled={busy !== null} autoFocus
                      className="inline-flex items-center gap-1.5 h-10 rounded-lg px-4 text-sm font-semibold bg-[#dc2626] hover:bg-[#b91c1c] text-white disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
                {busy === "exit" ? "Requesting…" : "Yes, exit all"}
              </button>
              <button type="button" onClick={() => setConfirming(false)} disabled={busy !== null}
                      className="h-10 rounded-lg px-4 text-sm font-semibold bg-card border border-[#1e2d45] text-[#e2e8f0] hover:border-[#2d3e58] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
      <Note note={note} />
    </Panel>
  );
}
