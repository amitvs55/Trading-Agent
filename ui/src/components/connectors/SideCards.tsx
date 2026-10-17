"use client";
import { useState, type FormEvent, type ReactNode } from "react";
import { Cpu, KeyRound, Play, Shield, SlidersHorizontal } from "lucide-react";
import type { ConnectorsResponse, RecorderStatus, TradingSettings } from "@/types/auth";
import { cn } from "@/lib/utils";
import { sendJson } from "@/lib/optionsApi";
import { ageSeconds, fmtDateTime, fmtNum } from "@/lib/optionsFormat";
import { Button } from "./ConnectorCard";
import { LiveAge } from "@/components/common/LiveAge";

export function Panel({ icon, title, children, subtitle }: { icon: ReactNode; title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[#1e2d45]">
        <div className="flex items-center gap-2">{icon}<h3 className="text-sm font-semibold text-[#e2e8f0]">{title}</h3></div>
        {subtitle && <p className="text-[11px] text-[#8391a7] mt-1 leading-snug">{subtitle}</p>}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function Note({ note }: { note: { tone: "ok" | "err"; text: string } | null }) {
  if (!note) return null;
  return (
    <div role="status" className={cn("mt-3 rounded-lg border px-3 py-2 text-xs",
      note.tone === "ok" ? "border-[#22c55e33] bg-[#22c55e0d] text-green" : "border-[#ef444433] bg-[#ef44440d] text-[#fca5a5]")}>
      {note.text}
    </div>
  );
}

// Small inputs live at module level: defined inside a component they'd remount on every keystroke

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 text-[12px]">
      <dt className="text-[#8391a7]">{k}</dt><dd className="text-right text-[#e2e8f0] min-w-0">{v}</dd>
    </div>
  );
}

function Num({ id, label, value, onChange, suffix, hint }: {
  id: string; label: string; value: string; onChange: (v: string) => void; suffix: string; hint: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-[11px] font-medium text-[#94a3b8]">{label}</label>
      <div className="mt-1.5 flex items-center gap-2 bg-card border border-[#1e2d45] rounded-lg px-3 focus-within:border-[#ff9933]">
        <input id={id} inputMode="decimal" value={value} onChange={e => onChange(e.target.value)}
               className="flex-1 min-w-0 bg-transparent py-2 text-sm font-mono text-[#e2e8f0] outline-none" />
        <span className="text-[11px] text-[#8391a7]">{suffix}</span>
      </div>
      <p className="text-[10px] text-[#8391a7] mt-1">{hint}</p>
    </div>
  );
}

export function Pw({ id, label, value, onChange, auto }: {
  id: string; label: string; value: string; onChange: (v: string) => void; auto: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-[11px] font-medium text-[#94a3b8]">{label}</label>
      <input id={id} type="password" value={value} onChange={e => onChange(e.target.value)} autoComplete={auto}
             className="mt-1.5 w-full bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#ff9933]" />
    </div>
  );
}

// ── Recorder ─────────────────────────────────────────────────────────────────

const EXIT_LABELS: Record<number, string> = { 0: " · finished normally", 1: " · crashed", 2: " · credentials missing", 3: " · login failed" };

export function RecorderCard({ status }: { status: RecorderStatus | null | undefined }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const age = ageSeconds(status?.ts);
  const alive = age != null && age < 120;
  const running = alive && status?.state === "running";
  const restarting = alive && status?.state === "restarting";
  const gaveUp = alive && !!status?.gave_up;

  const restart = async () => {
    setBusy(true);
    setNote(null);
    try {
      await sendJson("/api/admin/recorder/restart", "POST", {});
      setNote({ tone: "ok", text: "Requested. The recorder picks it up within about 15 seconds and starts a fresh session with the saved settings." });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel icon={<Cpu size={14} className="text-[#ff9933]" />} title="Recorder service"
           subtitle="Records the market and runs the signal engine. It reads the settings saved on this page each time a session starts.">
      <div className="flex items-center gap-2 mb-2">
        <span className={cn("w-2 h-2 rounded-full", gaveUp ? "bg-red" : running ? "bg-green animate-pulse" : restarting ? "bg-yellow animate-pulse" : alive ? "bg-[#60a5fa]" : "bg-red")} />
        <span className={cn("text-sm font-semibold", gaveUp ? "text-red" : running ? "text-green" : restarting ? "text-yellow" : alive ? "text-[#93c5fd]" : "text-red")}>
          {!status ? "No heartbeat yet" : !alive ? "Not responding" : gaveUp ? "Stopped: no more automatic restarts today"
            : running ? "Recording today's session" : restarting ? "Session stopped, restarting" : "Waiting for the next session"}
        </span>
      </div>
      <dl className="divide-y divide-[#1e2d45]">
        <Row k="Last heartbeat" v={status ? <LiveAge iso={status.ts} /> : "—"} />
        {!running && <Row k={restarting ? "Restarting at" : "Next session"} v={status?.next_start ? fmtDateTime(status.next_start) : "—"} />}
        {!!status?.restarts_today && <Row k="Automatic restarts today" v={<span className="text-yellow">{status.restarts_today} of 3</span>} />}
        <Row k="Session started" v={status?.session_started_at ? fmtDateTime(status.session_started_at) : "—"} />
        <Row k="Last exit code" v={status?.last_exit_code == null ? "—" :
          <span className={status.last_exit_code === 0 ? "text-green" : "text-yellow"}>{status.last_exit_code}{EXIT_LABELS[status.last_exit_code] ?? ""}</span>} />
        {status?.last_command && <Row k="Last command" v={<span className="text-[#94a3b8]">{status.last_command}</span>} />}
      </dl>
      <div className="mt-3">
        <Button onClick={restart} disabled={busy} busy={busy}><Play size={12} /> Start today&apos;s session now</Button>
      </div>
      <p className="text-[10px] text-[#8391a7] mt-2 leading-snug">Use this after saving new market data credentials during a trading day (before 15:00), or after the session stopped for good. A session that crashes is restarted automatically up to 3 times a day.</p>
      <Note note={note} />
    </Panel>
  );
}

// ── Trading settings ─────────────────────────────────────────────────────────

export function TradingCard({ trading, onSaved }: { trading: TradingSettings; onSaved: (p: ConnectorsResponse) => void }) {
  const [capital, setCapital] = useState(String(trading.capital));
  const [risk, setRisk] = useState(String(trading.risk_per_trade_pct));
  const [stop, setStop] = useState(String(trading.daily_loss_stop_pct));
  const [live, setLive] = useState<string[]>(trading.live_setups);
  const [keep, setKeep] = useState(String(trading.bars_retention_days));
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [syncedTo, setSyncedTo] = useState(trading);
  if (syncedTo !== trading) {                            // saved values changed: show them
    setSyncedTo(trading);
    setCapital(String(trading.capital)); setRisk(String(trading.risk_per_trade_pct));
    setStop(String(trading.daily_loss_stop_pct)); setLive(trading.live_setups);
    setKeep(String(trading.bars_retention_days));
  }

  const cap = Number(capital), r = Number(risk), s = Number(stop), k = Number(keep);
  const dirty = cap !== trading.capital || r !== trading.risk_per_trade_pct || s !== trading.daily_loss_stop_pct
    || k !== trading.bars_retention_days || live.slice().sort().join() !== trading.live_setups.slice().sort().join();

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      onSaved(await sendJson<ConnectorsResponse>("/api/admin/trading", "PUT",
        { capital: cap, risk_per_trade_pct: r, daily_loss_stop_pct: s, live_setups: live, bars_retention_days: k }));
      setNote({ tone: "ok", text: "Saved. The engine uses these from the next session start." });
    } catch (err) {
      setNote({ tone: "err", text: err instanceof Error ? err.message : "Save failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel icon={<SlidersHorizontal size={14} className="text-[#ff9933]" />} title="Trading rules"
           subtitle="Position sizing and which setups send LIVE signals. Every other setup keeps running in SHADOW mode.">
      <form onSubmit={save}>
        <div className="grid grid-cols-1 gap-3">
          <Num id="t-cap" label="Capital" value={capital} onChange={setCapital} suffix="₹" hint={`₹${fmtNum(cap || 0)}`} />
          <div className="grid grid-cols-2 gap-3">
            <Num id="t-risk" label="Risk per trade" value={risk} onChange={setRisk} suffix="%" hint={`₹${fmtNum((cap * r) / 100 || 0)} per trade`} />
            <Num id="t-stop" label="Daily loss stop" value={stop} onChange={setStop} suffix="%" hint={`₹${fmtNum((cap * s) / 100 || 0)} per day`} />
          </div>
          <Num id="t-keep" label="Keep 1-minute market data" value={keep} onChange={setKeep} suffix="days"
               hint="Older bars are deleted after each session. They are the backtest data, so keep at least a year." />
        </div>
        <div className="mt-4">
          <div className="text-[11px] font-medium text-[#94a3b8] mb-1.5">Setups</div>
          <ul className="divide-y divide-[#1e2d45] rounded-lg border border-[#1e2d45] bg-card">
            {Object.entries(trading.setups).map(([id, label]) => {
              const on = live.includes(id);
              return (
                <li key={id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="text-[12px] text-[#e2e8f0]">{label}</span>
                  <button type="button" role="switch" aria-checked={on} aria-label={`${label}: ${on ? "live" : "shadow"}`}
                          onClick={() => setLive(l => on ? l.filter(x => x !== id) : [...l, id])}
                          className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-bold tracking-widest border transition-colors",
                            on ? "text-green border-[#22c55e44] bg-[#22c55e14]" : "text-[#94a3b8] border-[#1e2d45] bg-surface")}>
                    <span className={cn("w-1.5 h-1.5 rounded-full", on ? "bg-green" : "bg-[#475569]")} /> {on ? "LIVE" : "SHADOW"}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="text-[10px] text-[#8391a7] mt-1.5 leading-snug">
            Promote a setup to LIVE only after its shadow record shows 50+ trades with positive results after costs (Performance page).
            A LIVE setup whose last 30 trades lose money after costs is moved back to SHADOW automatically.
          </p>
        </div>
        <div className="mt-4"><button type="submit" disabled={!dirty || busy}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] disabled:opacity-40">
          Save rules</button></div>
        <Note note={note} />
      </form>
    </Panel>
  );
}

// ── Account ──────────────────────────────────────────────────────────────────

export function AccountCard({ username, secretKeyFromEnv }: { username: string; secretKeyFromEnv: boolean }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 10) return setNote({ tone: "err", text: "Use at least 10 characters." });
    if (next !== confirm) return setNote({ tone: "err", text: "The new passwords don't match." });
    setBusy(true);
    setNote(null);
    try {
      await sendJson("/api/auth/password", "POST", { current_password: current, new_password: next });
      setCurrent(""); setNext(""); setConfirm("");
      setNote({ tone: "ok", text: "Password changed. Other devices have been signed out." });
    } catch (err) {
      setNote({ tone: "err", text: err instanceof Error ? err.message : "Couldn't change the password" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel icon={<KeyRound size={14} className="text-[#ff9933]" />} title="Account" subtitle={`Signed in as ${username} (admin)`}>
      <form onSubmit={submit} className="grid gap-3">
        <Pw id="pw-cur" label="Current password" value={current} onChange={setCurrent} auto="current-password" />
        <Pw id="pw-new" label="New password" value={next} onChange={setNext} auto="new-password" />
        <Pw id="pw-conf" label="Confirm new password" value={confirm} onChange={setConfirm} auto="new-password" />
        <div><button type="submit" disabled={busy || !current || !next}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold bg-card border border-[#1e2d45] text-[#e2e8f0] hover:border-[#2d3e58] disabled:opacity-40">
          Change password</button></div>
      </form>
      <Note note={note} />
      <div className="mt-4 flex items-start gap-2 rounded-lg border border-[#1e2d45] bg-card px-3 py-2.5">
        <Shield size={13} className="text-[#8391a7] mt-0.5 flex-shrink-0" />
        <p className="text-[11px] text-[#8391a7] leading-snug">
          Secrets are encrypted in the database and never sent back to the browser.
          {secretKeyFromEnv ? " The encryption key comes from the SECRET_KEY variable." :
            " The encryption key is stored in the database; setting a SECRET_KEY variable on Railway keeps it separate."}
        </p>
      </div>
    </Panel>
  );
}
