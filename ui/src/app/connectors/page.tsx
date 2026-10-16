"use client";
import { useState } from "react";
import { PlugZap, RefreshCw, ShieldAlert } from "lucide-react";
import type { ConnectorsResponse, HealthResponse, HealthResult } from "@/types/auth";
import { sendJson, useOptionsApi } from "@/lib/optionsApi";
import { useAuth } from "@/components/auth/AuthGate";
import { HealthOverview } from "@/components/connectors/HealthOverview";
import { ConnectorCard } from "@/components/connectors/ConnectorCard";
import { AccountCard, RecorderCard, TradingCard } from "@/components/connectors/SideCards";

const ALL_CHECKS = ["database", "recorder", "market_data", "angel", "kite", "telegram", "openai", "macro"];

export default function ConnectorsPage() {
  const auth = useAuth();
  const conn = useOptionsApi<ConnectorsResponse>("/api/admin/connectors", 30_000);
  const health = useOptionsApi<HealthResponse>("/api/admin/health", 30_000);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [runError, setRunError] = useState<string | null>(null);

  const run = async (ids: string[], sendTelegramTest = false) => {
    setRunning(s => { const n = new Set(s); ids.forEach(i => n.add(i)); return n; });
    setRunError(null);
    try {
      const res = await sendJson<{ results: Record<string, HealthResult> }>("/api/admin/health/run", "POST",
        { ids, send_telegram_test: sendTelegramTest });
      await health.refresh(prev => prev ? { ...prev, results: { ...prev.results, ...res.results } } : prev, { revalidate: true });
      await conn.refresh();
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Health check failed");
    } finally {
      setRunning(s => { const n = new Set(s); ids.forEach(i => n.delete(i)); return n; });
    }
  };

  const onSaved = (payload: ConnectorsResponse) => {
    conn.refresh(payload, { revalidate: false });
    health.refresh();                          // a save stores its test result: pick it up for the tiles
  };
  const data = conn.data;
  const forbidden = conn.error && "status" in conn.error && (conn.error as { status: number }).status === 403;
  const anyRunning = running.size > 0;

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><PlugZap size={20} className="text-[#ff9933]" /> Connectors &amp; health</h1>
          <p className="text-sm text-[#64748b] mt-1">
            Every third-party key lives here, encrypted. Nothing needs editing in .env or on Railway; the recorder picks up changes at its next session start.
          </p>
        </div>
        <button onClick={() => run(ALL_CHECKS)} disabled={anyRunning}
                className="flex items-center gap-2 bg-[#ff9933] hover:bg-[#ffa94d] disabled:opacity-60 text-[#0b0f1a] rounded-lg px-4 py-2 text-sm font-semibold transition-colors">
          <RefreshCw size={14} className={anyRunning ? "animate-spin" : ""} /> {anyRunning ? "Running checks…" : "Run all health checks"}
        </button>
      </div>

      {forbidden && (
        <div className="mb-5 flex items-center gap-2 bg-[#f59e0b11] border border-[#f59e0b33] rounded-xl px-5 py-3 text-sm text-yellow">
          <ShieldAlert size={15} /> Only admins can manage connectors.
        </div>
      )}
      {(runError || (conn.error && !forbidden)) && (
        <div className="mb-5 bg-[#ef444411] border border-[#ef444433] rounded-xl px-5 py-3 text-sm text-red">
          ⚠ {runError ?? conn.error?.message}
        </div>
      )}

      <div className="mb-6"><HealthOverview health={health.data} running={running} /></div>

      <div className="grid gap-5 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex flex-col gap-5 min-w-0">
          <h2 className="text-sm font-semibold text-[#e2e8f0] -mb-1">Connectors</h2>
          {!data ? [0, 1, 2].map(i => <div key={i} className="skeleton h-64 rounded-xl" />) :
            data.connectors.map(c => (
              <ConnectorCard key={c.id} c={c} activeProvider={data.data_provider} onSaved={onSaved}
                             testing={running.has(c.id)} onTested={(id, send) => run([id], send)} />
            ))}
        </div>
        <aside className="flex flex-col gap-5 min-w-0">
          <RecorderCard status={data?.recorder ?? health.data?.recorder} />
          {data ? <TradingCard trading={data.trading} onSaved={onSaved} /> : <div className="skeleton h-80 rounded-xl" />}
          {auth && <AccountCard username={auth.user.username} secretKeyFromEnv={!!data?.secret_key_from_env} />}
        </aside>
      </div>
    </main>
  );
}
