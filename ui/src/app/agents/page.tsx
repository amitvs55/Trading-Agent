"use client";
import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Bot, CheckCircle2, CircleDashed, Cpu, FlaskConical, Loader2, Pause, Play, XCircle } from "lucide-react";
import type { AgentState, AgentStatus, AgentsResponse, SelfTest } from "@/types/options";
import { cn } from "@/lib/utils";
import { sendJson, useOptionsApi } from "@/lib/optionsApi";
import { fmtDateTime } from "@/lib/optionsFormat";
import { useAuth } from "@/components/auth/AuthGate";
import { LiveAge } from "@/components/common/LiveAge";

const STATUS: Record<AgentStatus, { label: string; icon: typeof CheckCircle2; text: string; ring: string; bar: string }> = {
  ok:       { label: "Working",          icon: CheckCircle2,  text: "text-green",     ring: "border-[#22c55e33] bg-[#22c55e0d]", bar: "bg-green" },
  degraded: { label: "Waiting for data", icon: AlertTriangle, text: "text-yellow",    ring: "border-[#f59e0b33] bg-[#f59e0b0d]", bar: "bg-yellow" },
  error:    { label: "Failing",          icon: XCircle,       text: "text-red",       ring: "border-[#ef444433] bg-[#ef44440d]", bar: "bg-red" },
  idle:     { label: "Not run yet",      icon: CircleDashed,  text: "text-[#94a3b8]", ring: "border-[#1e2d45] bg-card",          bar: "bg-[#334155]" },
};

function StatusPill({ status }: { status: AgentStatus }) {
  const S = STATUS[status] ?? STATUS.idle;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md border whitespace-nowrap", S.text, S.ring)}>
      <S.icon size={11} /> {S.label}
    </span>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl p-4 min-w-0">
      <div className="text-[10px] text-[#64748b] tracking-widest mb-2">{label}</div>
      <div className={cn("font-bold text-xl leading-7 text-[#e2e8f0] truncate", tone)}>{value}</div>
      {sub && <div className="text-[11px] text-[#64748b] mt-1 truncate">{sub}</div>}
    </div>
  );
}

function AgentCard({ label, reads, st }: { label: string; reads: string; st: Partial<AgentState> | undefined }) {
  const status = (st?.status ?? "idle") as AgentStatus;
  return (
    <article className="fade-in bg-surface border border-[#1e2d45] rounded-xl overflow-hidden flex flex-col">
      <div className={cn("h-0.5", STATUS[status]?.bar ?? "bg-[#334155]")} />
      <div className="px-4 pt-3.5 pb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[#e2e8f0]">{label}</h3>
          <p className="text-[11px] text-[#64748b] mt-0.5 leading-snug">{reads}</p>
        </div>
        <StatusPill status={status} />
      </div>
      <div className="px-4 flex-1">
        {st?.error ? (
          <p className="text-[11px] text-[#fca5a5] bg-[#ef44440d] border border-[#ef444433] rounded-lg px-2.5 py-2 font-mono break-words">{st.error}</p>
        ) : (
          <p className="text-[12px] text-[#94a3b8] leading-snug min-h-[34px]">{st?.detail || "No output yet."}</p>
        )}
      </div>
      <div className="px-4 py-2.5 mt-3 border-t border-[#1e2d45] flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-[#64748b]">
        <span>{st?.last_run_at ? <LiveAge iso={st.last_run_at} prefix="ran " /> : "never ran"}</span>
        {st?.ms != null && <span className="font-mono">{st.ms < 1 ? "<1" : st.ms.toFixed(st.ms < 10 ? 1 : 0)} ms</span>}
        {st?.runs != null && st.runs > 0 && <span>{st.runs} run{st.runs === 1 ? "" : "s"} · {st.errors ?? 0} error{st.errors === 1 ? "" : "s"}</span>}
        {status === "error" && st?.last_ok_at && <span>last worked <LiveAge iso={st.last_ok_at} /></span>}
      </div>
    </article>
  );
}

function SelfTestBanner({ t }: { t: SelfTest }) {
  const ok = t.passed;
  return (
    <div className={cn("fade-in flex items-start gap-2.5 rounded-xl border px-4 py-3 text-[12px] leading-relaxed",
      ok ? "border-[#22c55e33] bg-[#22c55e0b] text-[#94a3b8]" : "border-[#ef444433] bg-[#ef44440b] text-[#fca5a5]")}>
      {ok ? <CheckCircle2 size={15} className="text-green mt-0.5 flex-shrink-0" /> : <XCircle size={15} className="text-red mt-0.5 flex-shrink-0" />}
      <span>
        <b className={ok ? "text-green" : "text-red"}>{ok ? "Self-test passed" : `Self-test: ${t.errors} agent${t.errors === 1 ? "" : "s"} failing`}</b>
        {" · "}{t.source === "recorded" ? `replayed the first 45 min of the ${t.day} session` : "synthetic NIFTY market"}
        {t.degraded > 0 && ` · ${t.degraded} waiting for data`} · <LiveAge iso={t.ran_at} />
        {t.note && <span className="block text-[11px] text-[#64748b]">{t.note}</span>}
      </span>
    </div>
  );
}

export default function AgentsPage() {
  const auth = useAuth();
  const isAdmin = auth?.user?.role === "admin";
  const { data, refresh } = useOptionsApi<AgentsResponse>("/api/agents", 10_000);
  const [view, setView] = useState<"live" | "selftest">("live");
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);

  const index = data ? Object.keys(data.signal)[0] : undefined;
  const live = index ? data?.signal[index] : undefined;
  const test = data?.selftest ?? undefined;
  const showing: "live" | "selftest" = live ? (test ? view : "live") : "selftest";
  const group = showing === "live" ? live?.agents : test?.agents;
  const statuses = data ? data.catalog.map(a => (group?.[a.id]?.status ?? "idle") as AgentStatus) : [];
  const working = statuses.filter(s => s === "ok" || s === "degraded").length;
  const failing = statuses.filter(s => s === "error").length;
  const research = data?.research ?? [];
  const lastResearch = research.map(r => r.last_run_at).filter(Boolean).sort().pop() ?? null;
  const researchFailing = research.filter(r => r.status === "error").length;

  const runSelfTest = async () => {
    setTesting(true);
    setTestError(null);
    try {
      await sendJson("/api/admin/agents/selftest", "POST", {});
      await refresh();
      setView("selftest");
    } catch (e) {
      setTestError(e instanceof Error ? e.message : "Self-test failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><Bot size={20} className="text-[#ff9933]" /> Agents</h1>
          <p className="text-sm text-[#64748b] mt-1">
            Every agent behind the signals and the research pages: whether it ran, how long it took and what it concluded.
          </p>
        </div>
        {isAdmin && (
          <button onClick={runSelfTest} disabled={testing}
                  className="flex items-center gap-2 bg-[#ff9933] hover:bg-[#ffa94d] disabled:opacity-60 text-[#0b0f1a] rounded-lg px-4 py-2 text-sm font-semibold transition-colors">
            {testing ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />} {testing ? "Testing every agent…" : "Run self-test"}
          </button>
        )}
      </div>
      {testError && <div className="mb-4 rounded-xl border border-[#ef444433] bg-[#ef44440d] px-4 py-3 text-sm text-[#fca5a5]">⚠ {testError}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {!data ? [0, 1, 2, 3].map(i => <div key={i} className="skeleton h-[94px] rounded-xl" />) : (
          <>
            <Tile label="SIGNAL AGENTS" tone={failing ? "text-red" : working === statuses.length ? "text-green" : undefined}
                  value={`${working} / ${statuses.length} working`}
                  sub={showing === "live" && live ? <>Live {index} session · <LiveAge iso={live.as_of} /></> :
                       test ? <>Self-test · <LiveAge iso={test.ran_at} /></> : "No session or self-test yet"} />
            <Tile label="NEW SIGNALS" tone={live?.signals_paused ? "text-yellow" : undefined}
                  value={live ? (live.signals_paused ? <span className="inline-flex items-center gap-1.5"><Pause size={16} /> Paused</span>
                                                     : <span className="inline-flex items-center gap-1.5"><Play size={16} /> Allowed</span>) : "—"}
                  sub={live?.signals_paused ? `waiting for ${live.failed.join(", ")}` : live ? "all agents answering" : "starts with the session"} />
            <Tile label="RECORDER" value={data.recorder ? (data.recorder.state === "running" ? "Running" : "Waiting") : "Not reporting"}
                  tone={data.recorder?.state === "running" ? "text-green" : undefined}
                  sub={data.recorder?.state === "running" ? <>heartbeat <LiveAge iso={data.recorder.ts} /></> :
                       data.recorder?.next_start ? `next session ${fmtDateTime(data.recorder.next_start)}` : "deploy the recorder service"} />
            <Tile label="RESEARCH AGENTS" tone={researchFailing ? "text-red" : undefined}
                  value={researchFailing ? `${researchFailing} failing` : lastResearch ? `${research.length} tracked` : "Not run yet"}
                  sub={lastResearch ? <>last run <LiveAge iso={lastResearch} /></> : "they run when you analyse a stock"} />
          </>
        )}
      </div>

      <section className="mb-6">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
          <h2 className="text-sm font-semibold text-[#e2e8f0] flex items-center gap-2"><Cpu size={14} className="text-[#ff9933]" />
            Signal agents <span className="text-[#64748b] font-normal">· run on every 5-minute close, one after another</span></h2>
          {live && test && (
            <div className="flex rounded-lg border border-[#1e2d45] bg-card p-0.5 text-xs" role="tablist">
              {(["live", "selftest"] as const).map(v => (
                <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
                        className={cn("px-3 py-1 rounded-md transition-colors", view === v ? "bg-[#ff993322] text-[#ff9933]" : "text-[#94a3b8] hover:text-[#e2e8f0]")}>
                  {v === "live" ? "Live session" : "Self-test"}
                </button>
              ))}
            </div>
          )}
        </div>
        {showing === "selftest" && test && <div className="mb-3"><SelfTestBanner t={test} /></div>}
        {data && !live && !test && (
          <div className="mb-3 rounded-xl border border-dashed border-[#1e2d45] px-4 py-3 text-[12px] text-[#64748b]">
            No market session has run yet, so there&apos;s nothing live to show. {isAdmin ? "Run the self-test to check every agent now." : "An admin can run the self-test."}
          </div>
        )}
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
          {!data ? Array.from({ length: 9 }, (_, i) => <div key={i} className="skeleton h-[150px] rounded-xl" />) :
            data.catalog.map(a => <AgentCard key={a.id} label={a.label} reads={a.reads} st={group?.[a.id]} />)}
        </div>
        <p className="text-[11px] text-[#475569] mt-3 leading-relaxed max-w-3xl">
          If an agent fails, its check counts as missing data, no new signal is sent until it works again, and Telegram tells you after two
          failed checks in a row. Open trades keep being managed. &ldquo;Waiting for data&rdquo; means the agent ran but its input wasn&apos;t there yet
          (for example, the first 15 minutes of futures data).
        </p>
      </section>

      <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-[#1e2d45] flex items-center justify-between gap-3 flex-wrap">
          <span className="text-xs font-semibold text-[#e2e8f0] flex items-center gap-2"><Bot size={13} className="text-[#ff9933]" /> Research agents
            <span className="text-[10px] font-normal text-[#64748b]">the 13-step stock analysis on the <Link href="/" className="text-[#ff9933] hover:underline">Research</Link> page</span></span>
          {data && !data.openai_configured && <span className="text-[11px] text-yellow">OpenAI key not set: they can&apos;t run (<Link href="/connectors" className="underline">Connectors</Link>)</span>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead><tr className="text-[10px] tracking-widest text-[#64748b] text-left">
              <th className="px-4 py-2 font-medium">STAGE</th><th className="px-2 py-2 font-medium">AGENT</th>
              <th className="px-2 py-2 font-medium">STATUS</th><th className="px-2 py-2 font-medium">LAST RUN</th>
              <th className="px-2 py-2 font-medium text-right">TIME</th><th className="px-4 py-2 font-medium text-right">RUNS / ERRORS</th>
            </tr></thead>
            <tbody className="divide-y divide-[#1e2d45]">
              {!data ? Array.from({ length: 5 }, (_, i) => <tr key={i}><td colSpan={6} className="px-4 py-2"><div className="skeleton h-4 rounded" /></td></tr>) :
                research.map(r => (
                  <tr key={r.id} className="hover:bg-[#ffffff04] align-top">
                    <td className="px-4 py-2 font-mono text-[#64748b]">{r.stage}</td>
                    <td className="px-2 py-2 text-[#e2e8f0] whitespace-nowrap">{r.label}
                      {r.error && <div className="text-[11px] text-[#fca5a5] font-mono whitespace-normal max-w-md mt-0.5">{r.error}</div>}</td>
                    <td className="px-2 py-2"><StatusPill status={r.status} /></td>
                    <td className="px-2 py-2 text-[#94a3b8] whitespace-nowrap">{r.last_run_at ? <LiveAge iso={r.last_run_at} /> : "—"}</td>
                    <td className="px-2 py-2 text-right font-mono text-[#94a3b8]">{r.seconds != null ? `${r.seconds.toFixed(1)} s` : "—"}</td>
                    <td className="px-4 py-2 text-right font-mono text-[#94a3b8]">{r.runs} / {r.errors}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
