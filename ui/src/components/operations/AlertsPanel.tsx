"use client";
import { memo } from "react";
import { BellRing, CheckCircle2, Clock3, Mail, Send, XCircle } from "lucide-react";
import type { AlertRow, AlertStatus, AlertsResponse } from "@/types/auth";
import { cn } from "@/lib/utils";
import { fmtDateTime } from "@/lib/optionsFormat";
import { Panel } from "@/components/connectors/SideCards";

const STATUS: Record<AlertStatus, { label: string; cls: string; icon: typeof CheckCircle2 }> = {
  sent:    { label: "Delivered", cls: "text-green border-[#22c55e33] bg-[#22c55e0d]", icon: CheckCircle2 },
  pending: { label: "Waiting",   cls: "text-yellow border-[#f59e0b33] bg-[#f59e0b0d]", icon: Clock3 },
  failed:  { label: "Rejected",  cls: "text-[#fca5a5] border-[#ef444433] bg-[#ef44440d]", icon: XCircle },
  expired: { label: "Not delivered", cls: "text-[#fca5a5] border-[#ef444433] bg-[#ef44440d]", icon: XCircle },
};

/** Alerts are written in Telegram's HTML: show them as plain text. DOMParser builds an inert
 *  document (no scripts, no image loads), unlike innerHTML on a detached element. */
function plain(text: string): string {
  if (typeof DOMParser === "undefined") return text.replace(/<[^>]+>/g, "");
  return new DOMParser().parseFromString(text, "text/html").body.textContent ?? "";
}

const AlertItem = memo(function AlertItem({ a }: { a: AlertRow }) {
  const S = STATUS[a.status];
  const body = plain(a.text);
  const [first, ...rest] = body.split("\n");
  return (
    <li className="py-2.5 flex items-start gap-3">
      <span className={cn("inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md border whitespace-nowrap flex-shrink-0", S.cls)}>
        <S.icon size={11} aria-hidden /> {S.label}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] text-[#e2e8f0] leading-snug break-words">{first}</p>
        {rest.length > 0 && <p className="text-[11px] text-[#94a3b8] leading-snug line-clamp-1 break-words">{rest.join(" · ")}</p>}
        <p className="text-[11px] text-[#94a3b8] mt-0.5 flex flex-wrap gap-x-2">
          <span>{fmtDateTime(a.created_at)}</span>
          {a.channel && <span className="inline-flex items-center gap-1">{a.channel === "email" ? <Mail size={10} aria-hidden /> : <Send size={10} aria-hidden />} {a.channel}</span>}
          {a.attempts > 1 && <span>{a.attempts} tries</span>}
          {a.last_error && a.status !== "sent" && <span className="text-[#fca5a5]">{a.last_error}</span>}
          {a.last_error && a.status === "sent" && <span>after: {a.last_error}</span>}
        </p>
      </div>
    </li>
  );
});

export function AlertsPanel({ data }: { data: AlertsResponse | undefined }) {
  const c = data?.last_24h ?? {};
  const lost = (c.failed ?? 0) + (c.expired ?? 0);
  return (
    <Panel icon={<BellRing size={14} className="text-[#ff9933]" />} title="Alert delivery"
           subtitle="Every Telegram message goes through a queue that retries for 15 minutes, then falls back to e-mail when it's set up. Nothing blocks the signal engine.">
      <div className="flex flex-wrap gap-2 mb-3" aria-label="Last 24 hours">
        <span className="text-[11px] text-[#94a3b8] self-center">Last 24 h:</span>
        <span className="text-[11px] px-2 py-1 rounded-md border border-[#22c55e33] bg-[#22c55e0d] text-green">{c.sent ?? 0} delivered</span>
        {!!c.pending && <span className="text-[11px] px-2 py-1 rounded-md border border-[#f59e0b33] bg-[#f59e0b0d] text-yellow">{c.pending} waiting</span>}
        <span className={cn("text-[11px] px-2 py-1 rounded-md border", lost ? "border-[#ef444433] bg-[#ef44440d] text-[#fca5a5]" : "border-[#1e2d45] bg-card text-[#94a3b8]")}>
          {lost} not delivered
        </span>
      </div>
      {!data ? <div className="skeleton h-40 rounded-lg" /> : data.alerts.length === 0 ? (
        <p className="text-[12px] text-[#94a3b8] py-6 text-center">No alerts yet. They appear here from the first recording session.</p>
      ) : (
        <ul tabIndex={0} aria-label="Recent alerts" className="divide-y divide-[#1e2d45] max-h-[420px] overflow-y-auto pr-1 -mr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] rounded-md">
          {data.alerts.map(a => <AlertItem key={a.id} a={a} />)}
        </ul>
      )}
    </Panel>
  );
}
