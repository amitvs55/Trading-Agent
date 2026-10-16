"use client";
import { createContext, useContext, useState, type FormEvent, type ReactNode } from "react";
import useSWR from "swr";
import { Eye, EyeOff, KeyRound, Loader2, Lock, ShieldCheck, TrendingUp, User as UserIcon } from "lucide-react";
import type { SessionResponse, User } from "@/types/auth";
import { API_URL, cn } from "@/lib/utils";
import { ApiError, AuthRequired, ME_KEY, apiFetch, apiJson, clearToken, forgetToken, getToken, sendJson, setToken } from "@/lib/optionsApi";

interface AuthValue {
  user: User;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue | null {
  return useContext(AuthContext);
}

async function fetchMe(): Promise<User> {
  if (!getToken()) {
    const res = await fetch(`${API_URL}/api/auth/state`, { cache: "no-store" });
    if (!res.ok) throw new ApiError(res.status, `API error ${res.status}`);
    const state = (await res.json()) as { has_admin: boolean };
    throw new AuthRequired(state.has_admin ? "login_required" : "setup_required");
  }
  try {
    return await apiJson<User>(ME_KEY);
  } catch (err) {
    if (err instanceof AuthRequired) forgetToken();       // expired or revoked: start clean
    throw err;
  }
}

/** Everything in the app sits behind this: no session, no pages (and no API data). */
export function AuthGate({ children }: { children: ReactNode }) {
  const { data: user, error, isLoading, mutate } = useSWR<User>(ME_KEY, fetchMe, {
    shouldRetryOnError: false,
    revalidateOnFocus: true,
  });

  if (user) {
    const logout = async () => {
      try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch { /* signing out locally anyway */ }
      clearToken();
      await mutate(undefined, { revalidate: true });
    };
    return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
  }
  if (isLoading && !error) return <Splash />;
  if (error instanceof AuthRequired) {
    return error.code === "setup_required" ? <SetupScreen /> : <LoginScreen />;
  }
  return (
    <Shell>
      <Card icon={<Lock size={20} className="text-red" />} title="Can't reach the API">
        <p className="text-sm text-[#94a3b8] leading-relaxed">{error?.message ?? "Unknown error"}. The API service may be restarting.</p>
        <button onClick={() => mutate()} className="mt-5 w-full rounded-lg border border-[#1e2d45] bg-card py-2.5 text-sm text-[#e2e8f0] hover:border-[#ff9933] transition-colors">
          Try again
        </button>
      </Card>
    </Shell>
  );
}

// ── Screens ──────────────────────────────────────────────────────────────────

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <div className="india-stripe" />
      <div className="flex-1 grid place-items-center px-4 py-10">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-center gap-2.5 mb-7">
            <div className="w-9 h-9 rounded-lg grid place-items-center bg-[#ff993326] border border-[#ff993359]">
              <TrendingUp size={16} className="text-[#ff9933]" />
            </div>
            <div>
              <span className="font-bold tracking-wide text-[#ff9933]">TradingAgents</span>
              <span className="text-[#64748b] text-sm ml-1.5">India</span>
            </div>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

function Card({ icon, title, subtitle, children }: { icon: ReactNode; title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-2xl p-7 shadow-[0_20px_60px_rgba(0,0,0,.45)]">
      <div className="w-12 h-12 rounded-xl grid place-items-center mb-5 bg-[#ff993314] border border-[#ff993333]">{icon}</div>
      <h1 className="text-lg font-bold text-[#e2e8f0]">{title}</h1>
      {subtitle && <div className="text-sm text-[#64748b] mt-1 mb-5 leading-relaxed">{subtitle}</div>}
      {children}
    </div>
  );
}

function Splash() {
  return (
    <Shell>
      <div className="flex items-center justify-center gap-2 text-sm text-[#64748b]"><Loader2 size={16} className="animate-spin" /> Loading…</div>
    </Shell>
  );
}

function Input({ id, label, icon, type = "text", value, onChange, autoComplete, placeholder, reveal }: {
  id: string; label: string; icon: ReactNode; type?: string; value: string; onChange: (v: string) => void;
  autoComplete?: string; placeholder?: string; reveal?: boolean;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className="mb-3.5">
      <label htmlFor={id} className="text-[10px] tracking-widest text-[#64748b]">{label}</label>
      <div className="mt-1.5 flex items-center gap-2 bg-card border border-[#1e2d45] rounded-lg px-3 focus-within:border-[#ff9933] transition-colors">
        <span className="text-[#64748b]">{icon}</span>
        <input id={id} type={reveal && shown ? "text" : type} value={value} autoComplete={autoComplete} placeholder={placeholder}
               onChange={e => onChange(e.target.value)} spellCheck={false}
               className="flex-1 min-w-0 bg-transparent py-2.5 text-sm text-[#e2e8f0] outline-none placeholder:text-[#475569]" />
        {reveal && (
          <button type="button" onClick={() => setShown(s => !s)} className="text-[#64748b] hover:text-[#e2e8f0]" aria-label={shown ? "Hide" : "Show"}>
            {shown ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
    </div>
  );
}

function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button type="submit" disabled={busy}
            className="mt-2 w-full flex items-center justify-center gap-2 rounded-lg bg-[#ff9933] hover:bg-[#ffa94d] disabled:opacity-60 text-[#0b0f1a] font-semibold text-sm py-2.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]">
      {busy && <Loader2 size={14} className="animate-spin" />} {children}
    </button>
  );
}

function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return <div role="alert" className="mb-3 rounded-lg border border-[#ef444433] bg-[#ef44440d] px-3 py-2 text-xs text-[#fca5a5]">{message}</div>;
}

function LoginScreen() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await sendJson<SessionResponse>("/api/auth/login", "POST", { username, password });
      setToken(res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setBusy(false);
    }
  };

  return (
    <Shell>
      <form onSubmit={submit}>
        <Card icon={<Lock size={20} className="text-[#ff9933]" />} title="Sign in"
              subtitle="Live signals, connectors and settings are private to your account.">
          <ErrorLine message={error} />
          <Input id="login-user" label="USERNAME" icon={<UserIcon size={14} />} value={username} onChange={setUsername} autoComplete="username" />
          <Input id="login-pass" label="PASSWORD" icon={<KeyRound size={14} />} type="password" value={password} onChange={setPassword}
                 autoComplete="current-password" reveal />
          <SubmitButton busy={busy}>Sign in</SubmitButton>
        </Card>
      </form>
    </Shell>
  );
}

function SetupScreen() {
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooShort = password.length > 0 && password.length < 10;
  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 10) return setError("Use at least 10 characters for the password.");
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    setError(null);
    try {
      const res = await sendJson<SessionResponse>("/api/auth/setup", "POST", { setup_code: code, username, password });
      setToken(res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed");
      setBusy(false);
    }
  };

  return (
    <Shell>
      <form onSubmit={submit}>
        <Card icon={<ShieldCheck size={20} className="text-[#ff9933]" />} title="Create the admin account"
              subtitle={<>First run: this account manages connectors and settings. Find the one-time <b className="text-[#94a3b8]">setup code</b> in
                the API service&apos;s logs on Railway (a line starting <span className="font-mono text-[#94a3b8]">ADMIN SETUP CODE</span>).</>}>
          <ErrorLine message={error} />
          <Input id="setup-code" label="SETUP CODE" icon={<KeyRound size={14} />} value={code} onChange={v => setCode(v.toUpperCase())}
                 placeholder="ABCDE-FGHJK" autoComplete="one-time-code" />
          <Input id="setup-user" label="USERNAME" icon={<UserIcon size={14} />} value={username} onChange={setUsername} autoComplete="username" />
          <Input id="setup-pass" label="PASSWORD (10+ CHARACTERS)" icon={<Lock size={14} />} type="password" value={password}
                 onChange={setPassword} autoComplete="new-password" reveal />
          <Input id="setup-confirm" label="CONFIRM PASSWORD" icon={<Lock size={14} />} type="password" value={confirm}
                 onChange={setConfirm} autoComplete="new-password" reveal />
          <div className={cn("text-[11px] -mt-1 mb-2", tooShort || mismatch ? "text-yellow" : "text-[#475569]")}>
            {tooShort ? "At least 10 characters." : mismatch ? "Passwords don't match yet." : "A passphrase of a few words works well."}
          </div>
          <SubmitButton busy={busy}>Create account and sign in</SubmitButton>
        </Card>
      </form>
    </Shell>
  );
}
