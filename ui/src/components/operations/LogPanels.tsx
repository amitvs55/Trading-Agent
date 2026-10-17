"use client";
import { memo } from "react";
import { History, Unplug } from "lucide-react";
import type { AuditEntry, RecorderEvent } from "@/types/auth";
import { fmtDateTime } from "@/lib/optionsFormat";
import { Panel } from "@/components/connectors/SideCards";

const ACTIONS: Record<string, string> = {
  signals_paused: "Paused new signals", signals_resumed: "Resumed new signals", exit_all: "Exit all requested",
  trading_rules: "Changed trading rules", setup_demoted: "Setup moved back to SHADOW", connector_saved: "Saved a connector",
  data_provider: "Changed the data provider", recorder_restart: "Started the session", holiday_added: "Added a holiday",
  holiday_removed: "Removed a holiday", holiday_year: "Holiday list status", event_added: "Added an event",
  event_removed: "Removed an event", user_created: "Created a user", user_updated: "Changed a user",
  user_deleted: "Deleted a user", password_reset: "Reset a password",
};

const EVENTS: Record<string, string> = {
  ws_close: "Feed disconnected", ws_reconnect: "Feed reconnecting", ws_connect: "Feed connected",
  ws_noreconnect: "Feed gave up reconnecting", ws_error: "Feed error", session_summary: "Session summary",
};

const AuditItem = memo(function AuditItem({ e }: { e: AuditEntry }) {
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-[12px] text-[#e2e8f0] font-medium">{ACTIONS[e.action] ?? e.action}</span>
        <span className="text-[11px] text-[#94a3b8] font-mono">{fmtDateTime(e.ts)}</span>
      </div>
      <p className="text-[11px] text-[#94a3b8] leading-snug break-words">
        <span className="text-[#cbd5e1]">{e.actor}</span>{e.detail ? ` · ${e.detail}` : ""}
      </p>
    </li>
  );
});

export function AuditPanel({ entries }: { entries: AuditEntry[] | undefined }) {
  return (
    <Panel icon={<History size={14} className="text-[#ff9933]" />} title="Change log"
           subtitle="Who changed what: trading rules, pauses, connectors, calendars and users. Automatic demotions are listed as auto-demote.">
      {!entries ? <div className="skeleton h-40 rounded-lg" /> : entries.length === 0 ? (
        <p className="text-[12px] text-[#94a3b8] py-6 text-center">No changes recorded yet.</p>
      ) : (
        <ul tabIndex={0} aria-label="Change log" className="divide-y divide-[#1e2d45] max-h-[360px] overflow-y-auto pr-1 -mr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] rounded-md">
          {entries.map(e => <AuditItem key={e.id} e={e} />)}
        </ul>
      )}
    </Panel>
  );
}

export function RecorderEventsPanel({ events }: { events: RecorderEvent[] | undefined }) {
  return (
    <Panel icon={<Unplug size={14} className="text-[#ff9933]" />} title="Recorder events (3 days)"
           subtitle="Market-data disconnects and reconnects, and each day's recording summary.">
      {!events ? <div className="skeleton h-32 rounded-lg" /> : events.length === 0 ? (
        <p className="text-[12px] text-[#94a3b8] py-6 text-center">Nothing logged in the last 3 days.</p>
      ) : (
        <ul tabIndex={0} aria-label="Recorder events" className="divide-y divide-[#1e2d45] max-h-[300px] overflow-y-auto pr-1 -mr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] rounded-md">
          {events.map(e => (
            <li key={e.id} className="py-2">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="text-[12px] text-[#e2e8f0]">{EVENTS[e.kind] ?? e.kind}</span>
                <span className="text-[11px] text-[#94a3b8] font-mono">{fmtDateTime(e.ts)}</span>
              </div>
              {e.detail && <p className="text-[11px] text-[#94a3b8] leading-snug break-words line-clamp-2" title={e.detail}>{e.detail}</p>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
