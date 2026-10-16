"use client";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Bot, ExternalLink, Eye, EyeOff, Loader2, LogIn, Radio, Send, Signal, Trash2, Undo2, Zap } from "lucide-react";
import type { Connector, ConnectorField, ConnectorsResponse } from "@/types/auth";
import { API_URL, cn } from "@/lib/utils";
import { sendJson } from "@/lib/optionsApi";
import { CheckBadge, CheckMeta } from "./HealthBits";

const ICONS: Record<Connector["id"], typeof Signal> = { angel: Signal, kite: Radio, telegram: Send, openai: Bot };

const SOURCE: Record<ConnectorField["source"], { label: string; cls: string }> = {
  app:   { label: "Saved here",       cls: "text-[#93c5fd] border-[#3987e533] bg-[#3987e50d]" },
  env:   { label: "From environment", cls: "text-[#c4b5fd] border-[#a78bfa33] bg-[#a78bfa0d]" },
  unset: { label: "Not set",          cls: "text-[#64748b] border-[#1e2d45] bg-card" },
};

function FieldRow({ f, value, cleared, onChange, onClear, onUndo }: {
  f: ConnectorField; value: string; cleared: boolean;
  onChange: (v: string) => void; onClear: () => void; onUndo: () => void;
}) {
  const [shown, setShown] = useState(false);
  const id = `field-${f.key}`;
  const placeholder = cleared ? "Will be removed when you save"
    : f.secret && f.is_set ? `Saved (${f.display}). Type to replace` : f.placeholder || (f.required ? "Required" : "Optional");
  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <label htmlFor={id} className="text-[11px] font-medium text-[#94a3b8]">
          {f.label}{!f.required && <span className="text-[#475569] font-normal"> · optional</span>}
        </label>
        <span className={cn("text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border", SOURCE[f.source].cls)}>
          {SOURCE[f.source].label}
        </span>
      </div>
      <div className={cn("flex items-center gap-2 bg-card border rounded-lg px-3 transition-colors",
        cleared ? "border-[#ef444455]" : "border-[#1e2d45] focus-within:border-[#ff9933]")}>
        <input id={id} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
               type={f.secret && !shown ? "password" : "text"} autoComplete="off" spellCheck={false} disabled={cleared}
               className="flex-1 min-w-0 bg-transparent py-2 text-sm font-mono text-[#e2e8f0] outline-none placeholder:font-sans placeholder:text-[#475569] disabled:opacity-60" />
        {f.secret && !cleared && (
          <button type="button" onClick={() => setShown(s => !s)} className="text-[#64748b] hover:text-[#e2e8f0]" aria-label={shown ? "Hide" : "Show"}>
            {shown ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
        {f.source === "app" && (cleared
          ? <button type="button" onClick={onUndo} className="text-[#64748b] hover:text-[#e2e8f0]" aria-label="Keep saved value" title="Keep the saved value"><Undo2 size={14} /></button>
          : <button type="button" onClick={onClear} className="text-[#64748b] hover:text-[#fca5a5]" aria-label="Remove saved value" title="Remove the saved value"><Trash2 size={14} /></button>)}
      </div>
      {f.help && <p className="text-[10px] text-[#475569] mt-1 leading-snug">{f.help}</p>}
    </div>
  );
}

export function ConnectorCard({ c, activeProvider, onSaved, onTested, testing }: {
  c: Connector;
  activeProvider: string;
  onSaved: (payload: ConnectorsResponse) => void;
  onTested: (id: string, sendTest?: boolean) => Promise<void>;
  testing: boolean;
}) {
  const initial = useMemo(() => Object.fromEntries(c.fields.map(f => [f.key, f.secret ? "" : f.display])), [c.fields]);
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [cleared, setCleared] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"save" | "provider" | null>(null);
  const [note, setNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  useEffect(() => { setValues(initial); setCleared(new Set()); }, [initial]);

  const changes = useMemo(() => {
    const out: Record<string, string | null> = {};
    for (const f of c.fields) {
      if (cleared.has(f.key)) out[f.key] = null;
      else if (values[f.key] !== initial[f.key] && values[f.key].trim() !== "") out[f.key] = values[f.key].trim();
    }
    return out;
  }, [c.fields, cleared, values, initial]);
  const dirty = Object.keys(changes).length > 0;
  const isProvider = c.id === "angel" || c.id === "kite";
  const active = isProvider && activeProvider === c.id;
  const Icon = ICONS[c.id];
  const loginUrl = c.id === "kite" && c.health?.details?.login_url ? `${API_URL}/kite/login` : null;

  const save = async () => {
    setBusy("save");
    setNote(null);
    try {
      const payload = await sendJson<ConnectorsResponse>(`/api/admin/connectors/${c.id}`, "PUT", { values: changes });
      onSaved(payload);
      setNote({ tone: "ok", text: "Saved. Testing the connection…" });
      await onTested(c.id);
      setNote({ tone: "ok", text: "Saved and tested." });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setBusy(null);
    }
  };

  const useAsProvider = async () => {
    setBusy("provider");
    try {
      onSaved(await sendJson<ConnectorsResponse>("/api/admin/data-provider", "PUT", { provider: c.id }));
      setNote({ tone: "ok", text: `${c.name} is now the market data source. It takes effect at the next session start.` });
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Couldn't switch" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <article className={cn("bg-surface border rounded-xl overflow-hidden", active ? "border-[#ff993355]" : "border-[#1e2d45]")}>
      <header className="px-5 py-4 border-b border-[#1e2d45] flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className={cn("w-10 h-10 rounded-xl grid place-items-center flex-shrink-0 border",
            active ? "bg-[#ff993314] border-[#ff993344]" : "bg-card border-[#1e2d45]")}>
            <Icon size={17} className={active ? "text-[#ff9933]" : "text-[#94a3b8]"} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-[#e2e8f0]">{c.name}</h3>
              <span className="text-[10px] tracking-wider uppercase text-[#64748b]">{c.role}</span>
              {active && <span className="text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded bg-[#ff993314] text-[#ff9933] border border-[#ff993333]">ACTIVE SOURCE</span>}
            </div>
            <p className="text-[12px] text-[#64748b] mt-0.5 leading-snug">{c.description}</p>
          </div>
        </div>
        <CheckBadge status={c.health?.status} />
      </header>

      <div className="px-5 py-4 grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3.5">
        {c.fields.map(f => (
          <FieldRow key={f.key} f={f} value={values[f.key] ?? ""} cleared={cleared.has(f.key)}
                    onChange={v => setValues(s => ({ ...s, [f.key]: v }))}
                    onClear={() => setCleared(s => new Set(s).add(f.key))}
                    onUndo={() => setCleared(s => { const n = new Set(s); n.delete(f.key); return n; })} />
        ))}
      </div>

      <div className="mx-5 mb-4 rounded-lg bg-card border border-[#1e2d45] px-3 py-2.5 flex items-start justify-between gap-3">
        <p className="text-[12px] text-[#94a3b8] leading-snug min-w-0">
          {testing ? "Testing…" : c.health?.message ?? (c.configured ? "Not tested yet." : `Missing: ${c.missing.join(", ")}`)}
        </p>
        <span className="flex-shrink-0"><CheckMeta result={c.health} /></span>
      </div>

      {note && (
        <div role="status" className={cn("mx-5 mb-4 rounded-lg border px-3 py-2 text-xs",
          note.tone === "ok" ? "border-[#22c55e33] bg-[#22c55e0d] text-green" : "border-[#ef444433] bg-[#ef44440d] text-[#fca5a5]")}>
          {note.text}
        </div>
      )}

      <footer className="px-5 py-3 border-t border-[#1e2d45] flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Button onClick={save} disabled={!dirty || busy !== null} primary busy={busy === "save"}>Save &amp; test</Button>
          <Button onClick={() => onTested(c.id)} disabled={testing || busy !== null} busy={testing && busy === null}>
            <Zap size={13} /> Test
          </Button>
          {c.id === "telegram" && (
            <Button onClick={() => onTested(c.id, true)} disabled={testing || !c.configured}>
              <Send size={13} /> Send test message
            </Button>
          )}
          {isProvider && !active && (
            <Button onClick={useAsProvider} disabled={busy !== null} busy={busy === "provider"}>Use for market data</Button>
          )}
          {loginUrl && <a href={loginUrl} className="inline-flex items-center gap-1.5 text-xs text-[#ff9933] hover:underline px-2"><LogIn size={13} /> Log in to Kite today</a>}
        </div>
        {c.docs_url && (
          <a href={c.docs_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-[#64748b] hover:text-[#e2e8f0]">
            Where to get these <ExternalLink size={11} />
          </a>
        )}
      </footer>
    </article>
  );
}

export function Button({ children, onClick, disabled, primary, busy }: {
  children: ReactNode; onClick: () => void; disabled?: boolean; primary?: boolean; busy?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
            className={cn("inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
              primary ? "bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a]" : "bg-card border border-[#1e2d45] text-[#e2e8f0] hover:border-[#2d3e58]")}>
      {busy && <Loader2 size={12} className="animate-spin" />} {children}
    </button>
  );
}
