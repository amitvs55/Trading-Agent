"use client";
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useState, type FormEvent, type ReactNode } from "react";
import useSWR, { mutate as globalMutate, useSWRConfig } from "swr";
import { Eye, EyeOff, KeyRound, Loader2, Lock, ShieldCheck, TrendingUp, User as UserIcon } from "lucide-react";
import type { SessionResponse, User } from "@/types/auth";
import { API_URL, cn } from "@/lib/utils";
import {
  AUTH_EVENT, AuthRequired, ME_KEY, TOKEN_KEY, apiFetch, apiJson, cacheUser, clearToken, forgetToken, getCachedUser,
  getToken, sendJson, setToken,
} from "@/lib/optionsApi";
import { clearFailures } from "@/lib/connection";

interface AuthValue {
  user: User | null;               // null for a moment on a fresh browser, until /api/auth/me answers
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue | null {
  return useContext(AuthContext);
}

// useLayoutEffect on the client (runs before paint), nothing on the server.
const useBeforePaint = typeof window === "undefined" ? useEffect : useLayoutEffect;

// What the pages need first. Fetched once the browser is idle after sign-in, so moving between
// pages shows real data at once instead of a skeleton (SWR revalidates it on arrival anyway).
const PREFETCH = ["/api/options/status", "/api/options/board", "/api/options/signals?days=7",
  "/api/options/evaluations?hours=12", "/api/options/performance", "/api/options/signals?days=3650", "/api/paper"];
const PREFETCH_ADMIN = ["/api/agents", "/api/admin/connectors", "/api/admin/health"];

function whenIdle(fn: () => void): () => void {
  const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
                                 cancelIdleCallback?: (id: number) => void };
  if (w.requestIdleCallback) {
    const id = w.requestIdleCallback(fn, { timeout: 3_000 });
    return () => w.cancelIdleCallback?.(id);
  }
  const id = window.setTimeout(fn, 1_200);
  return () => window.clearTimeout(id);
}

/**
 * Everything in the app sits behind this. With a saved session the pages render at once and load
 * their data in parallel with the session check (the API enforces auth on every call either way);
 * without one, the sign-in screen shows. No full-screen "Loading…" step in between.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  // The server (and the first client render) assume a session, so pages stay statically rendered.
  // The layout's inline script hides the shell before paint when there's none; this corrects it.
  const [token, setTokenState] = useState<string | null>("assumed");
  const [rejected, setRejected] = useState<string | null>(null);     // the token the API turned down
  const [cached, setCached] = useState<User | null>(null);
  const { cache } = useSWRConfig();

  const sync = useCallback(() => {
    setTokenState(getToken() || null);
    setCached(getCachedUser<User>());
  }, []);
  useBeforePaint(sync, [sync]);
  useEffect(() => {
    const onStorage = (e: StorageEvent) => { if (e.key === null || e.key === TOKEN_KEY) sync(); };   // other tabs
    window.addEventListener(AUTH_EVENT, sync);
    window.addEventListener("storage", onStorage);
    return () => { window.removeEventListener(AUTH_EVENT, sync); window.removeEventListener("storage", onStorage); };
  }, [sync]);

  const { data: me } = useSWR<User>(token ? ME_KEY : null, async (k: string) => {
    const used = getToken();
    if (!used) throw new AuthRequired();                // signed out: no request
    try {
      return await apiJson<User>(k);
    } catch (err) {
      if (err instanceof AuthRequired) setRejected(used);
      throw err;
    }
  }, { shouldRetryOnError: false, revalidateOnFocus: true, onSuccess: cacheUser });
  // Tied to the token it was about, so a rejection of an old session never signs out a new one
  const expired = !!token && rejected === token;
  useEffect(() => { if (expired) forgetToken(); }, [expired]);       // revoked or timed out: start clean

  const user = me ?? cached;
  const signedIn = !!token && !expired;
  useEffect(() => {                                   // keep the pre-paint role marker (layout.tsx) current
    const html = document.documentElement;
    html.classList.remove("role-admin", "role-viewer");
    if (user?.role === "admin" || user?.role === "viewer") html.classList.add(`role-${user.role}`);
  }, [user?.role]);
  const confirmedRole = me?.role;                     // prefetch only once the session is confirmed
  useEffect(() => {
    if (!confirmedRole) return;
    return whenIdle(() => {
      const keys = confirmedRole === "admin" ? [...PREFETCH, ...PREFETCH_ADMIN] : PREFETCH;
      keys.filter(k => cache.get(k) === undefined)      // untouched: no page has loaded or is loading it
          .forEach(k => { globalMutate(k, apiJson(k), { revalidate: false }).catch(() => { /* the page retries */ }); });
    });
  }, [confirmedRole, cache]);

  const logout = useCallback(async () => {
    try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch { /* signing out locally anyway */ }
    clearToken();
    clearFailures();
  }, []);

  if (!signedIn) return <SignedOut />;
  return (
    <AuthContext.Provider value={{ user, logout }}>
      <div data-app-shell>{children}</div>
    </AuthContext.Provider>
  );
}

function SignedOut() {
  // Login is the usual case, so it shows straight away; the one-time setup screen replaces it only
  // if the API says no admin exists yet.
  const { data } = useSWR<{ has_admin: boolean }>("/api/auth/state", async (k: string) => {
    const res = await fetch(`${API_URL}${k}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, { revalidateOnFocus: false });
  return data && !data.has_admin ? <SetupScreen /> : <LoginScreen />;
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
              <span className="text-[#8391a7] text-sm ml-1.5">India</span>
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
    <div className="fade-in bg-surface border border-[#1e2d45] rounded-2xl p-7 shadow-[0_20px_60px_rgba(0,0,0,.45)]">
      <div className="w-12 h-12 rounded-xl grid place-items-center mb-5 bg-[#ff993314] border border-[#ff993333]">{icon}</div>
      <h1 className="text-lg font-bold text-[#e2e8f0]">{title}</h1>
      {subtitle && <div className="text-sm text-[#8391a7] mt-1 mb-5 leading-relaxed">{subtitle}</div>}
      {children}
    </div>
  );
}

function Input({ id, label, icon, type = "text", value, onChange, autoComplete, placeholder, reveal }: {
  id: string; label: string; icon: ReactNode; type?: string; value: string; onChange: (v: string) => void;
  autoComplete?: string; placeholder?: string; reveal?: boolean;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className="mb-3.5">
      <label htmlFor={id} className="text-[10px] tracking-widest text-[#8391a7]">{label}</label>
      <div className="mt-1.5 flex items-center gap-2 bg-card border border-[#1e2d45] rounded-lg px-3 focus-within:border-[#ff9933] transition-colors">
        <span className="text-[#8391a7]">{icon}</span>
        <input id={id} type={reveal && shown ? "text" : type} value={value} autoComplete={autoComplete} placeholder={placeholder}
               onChange={e => onChange(e.target.value)} spellCheck={false}
               className="flex-1 min-w-0 bg-transparent py-2.5 text-sm text-[#e2e8f0] outline-none placeholder:text-[#8391a7]" />
        {reveal && (
          <button type="button" onClick={() => setShown(s => !s)} className="text-[#8391a7] hover:text-[#e2e8f0]" aria-label={shown ? "Hide" : "Show"}>
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
          <div className={cn("text-[11px] -mt-1 mb-2", tooShort || mismatch ? "text-yellow" : "text-[#8391a7]")}>
            {tooShort ? "At least 10 characters." : mismatch ? "Passwords don't match yet." : "A passphrase of a few words works well."}
          </div>
          <SubmitButton busy={busy}>Create account and sign in</SubmitButton>
        </Card>
      </form>
    </Shell>
  );
}
