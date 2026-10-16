"use client";
import { useState, type FormEvent, type ReactNode } from "react";
import { mutate as globalMutate } from "swr";
import { Ban, Check, KeyRound, Loader2, Pencil, Trash2, UserPlus, UserRound, Users } from "lucide-react";
import type { User, UsersResponse } from "@/types/auth";
import { cn } from "@/lib/utils";
import { ME_KEY, cacheUser, sendJson, apiJson } from "@/lib/optionsApi";
import { fmtDateTime } from "@/lib/optionsFormat";
import { ROLE_HELP, ROLE_LABEL, displayName, initials, suggestUsername } from "@/lib/people";
import { LiveAge } from "@/components/common/LiveAge";
import { Note, Panel, Pw } from "@/components/connectors/SideCards";

type Tone = { tone: "ok" | "err"; text: string } | null;
const errText = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

// Module-level inputs: defined inside a component they would remount (and lose focus) on every keystroke

function Text({ id, label, value, onChange, placeholder, auto, hint, mono }: {
  id: string; label: string; value: string; onChange: (v: string) => void; placeholder?: string; auto?: string;
  hint?: ReactNode; mono?: boolean;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-[11px] font-medium text-[#94a3b8]">{label}</label>
      <input id={id} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} autoComplete={auto}
             spellCheck={false}
             className={cn("mt-1.5 w-full bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-sm text-[#e2e8f0] outline-none focus:border-[#ff9933] placeholder:text-[#475569]",
               mono && "font-mono")} />
      {hint && <p className="text-[10px] text-[#475569] mt-1">{hint}</p>}
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={cn("text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded border uppercase",
      role === "admin" ? "text-[#ff9933] border-[#ff993333] bg-[#ff993314]" : "text-[#93c5fd] border-[#3987e533] bg-[#3987e50d]")}>
      {ROLE_LABEL[role] ?? role}
    </span>
  );
}

function Avatar({ user, size = "md" }: { user: User; size?: "md" | "lg" }) {
  return (
    <span className={cn("grid place-items-center rounded-xl bg-[#ff993326] text-[#ff9933] font-bold tracking-wide flex-shrink-0",
      size === "lg" ? "w-14 h-14 text-lg" : "w-8 h-8 text-[11px]", user.disabled && "opacity-40")}>
      {initials(user)}
    </span>
  );
}

function PrimaryButton({ children, busy, disabled, type = "submit", onClick }: {
  children: ReactNode; busy?: boolean; disabled?: boolean; type?: "submit" | "button"; onClick?: () => void;
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled || busy}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] disabled:opacity-40 transition-colors">
      {busy && <Loader2 size={12} className="animate-spin" />} {children}
    </button>
  );
}

// ── Your profile ─────────────────────────────────────────────────────────────

export function ProfileCard({ user }: { user: User }) {
  const [name, setName] = useState(user.full_name ?? "");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Tone>(null);
  const dirty = name.trim() !== (user.full_name ?? "");

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      const updated = await sendJson<User>("/api/auth/profile", "PATCH", { full_name: name.trim() });
      cacheUser(updated);
      await globalMutate(ME_KEY, updated, { revalidate: false });     // the navbar shows the new name at once
      setNote({ tone: "ok", text: "Saved." });
    } catch (err) {
      setNote({ tone: "err", text: errText(err, "Couldn't save") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel icon={<UserRound size={14} className="text-[#ff9933]" />} title="Your profile">
      <div className="flex items-center gap-4 mb-4">
        <Avatar user={{ ...user, full_name: name || user.full_name }} size="lg" />
        <div className="min-w-0">
          <div className="text-base font-semibold text-[#e2e8f0] truncate">{displayName({ ...user, full_name: name || user.full_name })}</div>
          <div className="flex items-center gap-2 mt-1 text-[11px] text-[#64748b]">
            <span className="font-mono">@{user.username}</span><RoleBadge role={user.role} />
          </div>
        </div>
      </div>
      <form onSubmit={save} className="grid gap-3">
        <Text id="profile-name" label="Full name" value={name} onChange={setName} placeholder="e.g. Amit Shinde" auto="name"
              hint="Shown in the top bar and on the users list." />
        <div><PrimaryButton busy={busy} disabled={!dirty}>Save name</PrimaryButton></div>
      </form>
      <Note note={note} />
      <dl className="mt-4 pt-3 border-t border-[#1e2d45] grid grid-cols-2 gap-y-1.5 text-[12px]">
        <dt className="text-[#64748b]">Member since</dt><dd className="text-right text-[#e2e8f0]">{fmtDateTime(user.created_at)}</dd>
        <dt className="text-[#64748b]">Last sign-in</dt><dd className="text-right text-[#e2e8f0]">{user.last_login_at ? <LiveAge iso={user.last_login_at} /> : "—"}</dd>
      </dl>
    </Panel>
  );
}

export function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Tone>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < 10) return setNote({ tone: "err", text: "Use at least 10 characters." });
    if (next !== confirm) return setNote({ tone: "err", text: "The new passwords don't match." });
    setBusy(true);
    setNote(null);
    try {
      await sendJson("/api/auth/password", "POST", { current_password: current, new_password: next });
      setCurrent(""); setNext(""); setConfirm("");
      setNote({ tone: "ok", text: "Password changed. Your other devices have been signed out." });
    } catch (err) {
      setNote({ tone: "err", text: errText(err, "Couldn't change the password") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel icon={<KeyRound size={14} className="text-[#ff9933]" />} title="Password">
      <form onSubmit={submit} className="grid gap-3">
        <Pw id="me-pw-cur" label="Current password" value={current} onChange={setCurrent} auto="current-password" />
        <Pw id="me-pw-new" label="New password (10+ characters)" value={next} onChange={setNext} auto="new-password" />
        <Pw id="me-pw-conf" label="Confirm new password" value={confirm} onChange={setConfirm} auto="new-password" />
        <div><PrimaryButton busy={busy} disabled={!current || !next}>Change password</PrimaryButton></div>
      </form>
      <Note note={note} />
    </Panel>
  );
}

// ── Users (admins) ───────────────────────────────────────────────────────────

function RolePicker({ value, onChange, name }: { value: string; onChange: (v: string) => void; name: string }) {
  return (
    <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Role">
      {["admin", "viewer"].map(r => (
        <label key={r} className={cn("cursor-pointer rounded-lg border px-3 py-2 transition-colors",
          value === r ? "border-[#ff993366] bg-[#ff993310]" : "border-[#1e2d45] bg-card hover:border-[#2d3e58]")}>
          <input type="radio" name={name} value={r} checked={value === r} onChange={() => onChange(r)} className="sr-only" />
          <span className="text-xs font-semibold text-[#e2e8f0]">{ROLE_LABEL[r]}</span>
          <span className="block text-[10px] text-[#64748b] leading-snug mt-0.5">{ROLE_HELP[r]}</span>
        </label>
      ))}
    </div>
  );
}

function AddUserForm({ onDone, onCancel }: { onDone: (u: User) => void; onCancel: () => void }) {
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [touchedUsername, setTouchedUsername] = useState(false);
  const [role, setRole] = useState("viewer");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Tone>(null);
  const shownUsername = touchedUsername ? username : suggestUsername(fullName);
  const problems = [
    !fullName.trim() && "a full name",
    shownUsername.length < 3 && "a username of 3+ characters",
    password.length < 10 && "a password of 10+ characters",
    password && confirm !== password && "matching passwords",
  ].filter(Boolean) as string[];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (problems.length) return setNote({ tone: "err", text: `Still needed: ${problems.join(", ")}.` });
    setBusy(true);
    setNote(null);
    try {
      const made = await sendJson<User>("/api/admin/users", "POST",
        { full_name: fullName.trim(), username: shownUsername, password, role });
      onDone(made);
    } catch (err) {
      setNote({ tone: "err", text: errText(err, "Couldn't create the account") });
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="menu-pop grid gap-3 rounded-xl border border-[#1e2d45] bg-card/40 p-4 mb-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Text id="new-name" label="Full name" value={fullName} onChange={setFullName} placeholder="Amit Shinde" auto="off" />
        <Text id="new-username" label="Username (for signing in)" value={shownUsername} mono auto="off"
              onChange={v => { setTouchedUsername(true); setUsername(v.toLowerCase().replace(/[^a-z0-9_.-]/g, "")); }}
              placeholder="amit" hint="Letters, digits, dot, dash or underscore." />
      </div>
      <RolePicker value={role} onChange={setRole} name="new-role" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Pw id="new-pw" label="Password (10+ characters)" value={password} onChange={setPassword} auto="new-password" />
        <Pw id="new-pw2" label="Confirm password" value={confirm} onChange={setConfirm} auto="new-password" />
      </div>
      <p className="text-[10px] text-[#475569]">Give the password to the person privately; they can change it under Your account after signing in.</p>
      <div className="flex items-center gap-2">
        <PrimaryButton busy={busy}><UserPlus size={12} /> Create account</PrimaryButton>
        <button type="button" onClick={onCancel} className="px-2 py-1.5 text-xs text-[#64748b] hover:text-[#e2e8f0]">Cancel</button>
      </div>
      <Note note={note} />
    </form>
  );
}

function ResetPasswordForm({ user, onDone, onCancel }: { user: User; onDone: () => void; onCancel: () => void }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Tone>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pw.length < 10) return setNote({ tone: "err", text: "Use at least 10 characters." });
    setBusy(true);
    try {
      await sendJson(`/api/admin/users/${user.id}/password`, "POST", { new_password: pw });
      onDone();
    } catch (err) {
      setNote({ tone: "err", text: errText(err, "Couldn't reset the password") });
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="menu-pop mt-2 flex flex-wrap items-end gap-2">
      <div className="min-w-[220px] flex-1"><Pw id={`reset-${user.id}`} label={`New password for ${displayName(user)}`} value={pw} onChange={setPw} auto="new-password" /></div>
      <PrimaryButton busy={busy}>Set password</PrimaryButton>
      <button type="button" onClick={onCancel} className="px-2 py-1.5 text-xs text-[#64748b] hover:text-[#e2e8f0]">Cancel</button>
      <div className="basis-full"><Note note={note} /></div>
    </form>
  );
}

function UserRow({ u, me, onChanged }: { u: User; me: User; onChanged: (text: string) => void }) {
  const [mode, setMode] = useState<"view" | "edit" | "password" | "delete">("view");
  const [name, setName] = useState(u.full_name ?? "");
  const [role, setRole] = useState(u.role);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isMe = u.id === me.id;

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setMode("view");
      onChanged(done);
    } catch (err) {
      setError(errText(err, "That didn't work"));
    } finally {
      setBusy(false);
    }
  };
  const patch = (body: object, done: string) => act(() => sendJson(`/api/admin/users/${u.id}`, "PATCH", body), done);

  return (
    <li className="py-3">
      <div className="flex items-center gap-3">
        <Avatar user={u} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("text-sm font-medium truncate", u.disabled ? "text-[#64748b] line-through" : "text-[#e2e8f0]")}>{displayName(u)}</span>
            <RoleBadge role={u.role} />
            {isMe && <span className="text-[10px] text-[#64748b]">you</span>}
            {u.disabled && <span className="text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded border border-[#ef444433] text-[#fca5a5] uppercase">Disabled</span>}
          </div>
          <div className="text-[11px] text-[#64748b] mt-0.5"><span className="font-mono">@{u.username}</span> · last sign-in {u.last_login_at ? <LiveAge iso={u.last_login_at} /> : "never"}</div>
        </div>
        {mode === "view" && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <IconButton label="Edit name and role" onClick={() => setMode("edit")}><Pencil size={13} /></IconButton>
            <IconButton label="Reset password" onClick={() => setMode("password")}><KeyRound size={13} /></IconButton>
            {!isMe && (
              <IconButton label={u.disabled ? "Enable account" : "Disable account"} busy={busy}
                          onClick={() => patch({ disabled: !u.disabled }, u.disabled ? `${displayName(u)} can sign in again.` : `${displayName(u)} is disabled and signed out.`)}>
                {u.disabled ? <Check size={13} /> : <Ban size={13} />}
              </IconButton>
            )}
            {!isMe && <IconButton label="Delete account" danger onClick={() => setMode("delete")}><Trash2 size={13} /></IconButton>}
          </div>
        )}
      </div>

      {mode === "edit" && (
        <form className="menu-pop mt-3 grid gap-3" onSubmit={e => { e.preventDefault(); patch(isMe ? { full_name: name } : { full_name: name, role }, "Saved."); }}>
          <Text id={`edit-name-${u.id}`} label="Full name" value={name} onChange={setName} auto="off" />
          {!isMe && <RolePicker value={role} onChange={setRole} name={`role-${u.id}`} />}
          <div className="flex items-center gap-2">
            <PrimaryButton busy={busy}>Save</PrimaryButton>
            <button type="button" onClick={() => { setMode("view"); setName(u.full_name ?? ""); setRole(u.role); }}
                    className="px-2 py-1.5 text-xs text-[#64748b] hover:text-[#e2e8f0]">Cancel</button>
          </div>
        </form>
      )}
      {mode === "password" && (
        <ResetPasswordForm user={u} onCancel={() => setMode("view")}
                           onDone={() => { setMode("view"); onChanged(`Password reset${isMe ? "" : `; ${displayName(u)} has been signed out`}.`); }} />
      )}
      {mode === "delete" && (
        <div className="menu-pop mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-[#ef444433] bg-[#ef44440d] px-3 py-2 text-xs text-[#fca5a5]">
          Delete {displayName(u)}&apos;s account? This can&apos;t be undone.
          <button type="button" disabled={busy} onClick={() => act(() => apiJson(`/api/admin/users/${u.id}`, { method: "DELETE" }), `${displayName(u)} was deleted.`)}
                  className="inline-flex items-center gap-1 rounded-md bg-[#ef4444] hover:bg-[#f05252] text-white px-2.5 py-1 font-semibold disabled:opacity-50">
            {busy && <Loader2 size={11} className="animate-spin" />} Delete
          </button>
          <button type="button" onClick={() => setMode("view")} className="px-2 py-1 text-[#94a3b8] hover:text-[#e2e8f0]">Keep</button>
        </div>
      )}
      {error && <p className="mt-2 text-[11px] text-[#fca5a5]">{error}</p>}
    </li>
  );
}

function IconButton({ children, label, onClick, danger, busy }: {
  children: ReactNode; label: string; onClick: () => void; danger?: boolean; busy?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} disabled={busy} aria-label={label} title={label}
            className={cn("w-8 h-8 grid place-items-center rounded-lg border border-transparent text-[#64748b] transition-colors disabled:opacity-50",
              danger ? "hover:text-[#fca5a5] hover:border-[#ef444433]" : "hover:text-[#e2e8f0] hover:border-[#1e2d45]")}>
      {busy ? <Loader2 size={13} className="animate-spin" /> : children}
    </button>
  );
}

export function UsersCard({ me, data, refresh }: { me: User; data: UsersResponse | undefined; refresh: () => Promise<unknown> }) {
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState<Tone>(null);
  const changed = async (text: string) => {
    setNote({ tone: "ok", text });
    await refresh();
    globalMutate(ME_KEY);                          // your own name or role may have changed
  };
  return (
    <Panel icon={<Users size={14} className="text-[#ff9933]" />} title="Users"
           subtitle="Everyone who can sign in. Admins manage everything; viewers can look but not change anything.">
      {!adding ? (
        <div className="mb-3"><PrimaryButton type="button" onClick={() => { setAdding(true); setNote(null); }}><UserPlus size={12} /> Add user</PrimaryButton></div>
      ) : (
        <AddUserForm onCancel={() => setAdding(false)}
                     onDone={u => { setAdding(false); changed(`${displayName(u)} (@${u.username}) can now sign in.`); }} />
      )}
      <Note note={note} />
      {!data ? (
        <div className="flex flex-col gap-3 mt-3">{[0, 1].map(i => <div key={i} className="skeleton h-12 rounded-lg" />)}</div>
      ) : (
        <ul className="divide-y divide-[#1e2d45] mt-1">
          {data.users.map(u => <UserRow key={u.id} u={u} me={me} onChanged={changed} />)}
        </ul>
      )}
      <p className="mt-3 text-[10px] text-[#475569]">
        There is always at least one active admin: the last one can&apos;t be disabled, demoted or deleted.</p>
    </Panel>
  );
}
