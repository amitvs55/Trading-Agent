"use client";
import { ShieldCheck } from "lucide-react";
import type { AlertsResponse, AuditEntry, CalendarResponse, ConnectorsResponse, ControlsState, RecorderEvent } from "@/types/auth";
import type { SignalsResponse } from "@/types/options";
import { useOptionsApi } from "@/lib/optionsApi";
import { ageSeconds } from "@/lib/optionsFormat";
import { RecorderCard } from "@/components/connectors/SideCards";
import { ControlsPanel } from "@/components/operations/ControlsPanel";
import { AlertsPanel } from "@/components/operations/AlertsPanel";
import { CalendarPanel } from "@/components/operations/CalendarPanel";
import { AuditPanel, RecorderEventsPanel } from "@/components/operations/LogPanels";

const OPEN = new Set(["TRIGGERED", "ACTIVE", "T1_HIT"]);

export default function OperationsPage() {
  const controls = useOptionsApi<ControlsState>("/api/admin/controls", 10_000);
  const signals = useOptionsApi<SignalsResponse>("/api/options/signals?days=3", 15_000);
  const conn = useOptionsApi<ConnectorsResponse>("/api/admin/connectors", 15_000);
  const alerts = useOptionsApi<AlertsResponse>("/api/admin/alerts?limit=60", 20_000);
  const calendar = useOptionsApi<CalendarResponse>("/api/admin/calendar", 0);
  const audit = useOptionsApi<{ entries: AuditEntry[] }>("/api/admin/audit?limit=60", 30_000);
  const events = useOptionsApi<{ events: RecorderEvent[] }>("/api/admin/recorder/events?days=3", 60_000);

  const openCount = (signals.data?.signals ?? []).filter(s => OPEN.has(s.state)).length;
  const rec = conn.data?.recorder;
  const sessionRunning = rec?.state === "running" && (ageSeconds(rec.ts) ?? 999) < 120;

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5">
          <ShieldCheck size={20} className="text-[#ff9933]" /> Operations
        </h1>
        <p className="text-sm text-[#94a3b8] mt-1 max-w-3xl">
          Run the tool safely: pause it, exit everything, see that every alert arrived, and keep the trading calendar current.
          Connection keys and health checks are on Connectors.
        </p>
      </div>

      <div className="grid gap-5 grid-cols-1 xl:grid-cols-2">
        <div className="flex flex-col gap-5 min-w-0">
          <ControlsPanel controls={controls.data} openCount={openCount} sessionRunning={sessionRunning}
                         onChange={c => { controls.refresh(c, { revalidate: false }); audit.refresh(); }} />
          <RecorderCard status={rec} />
          <AlertsPanel data={alerts.data} />
        </div>
        <div className="flex flex-col gap-5 min-w-0">
          <CalendarPanel data={calendar.data} onChange={c => { calendar.refresh(c, { revalidate: false }); audit.refresh(); }} />
          <AuditPanel entries={audit.data?.entries} />
          <RecorderEventsPanel events={events.data?.events} />
        </div>
      </div>
    </main>
  );
}
