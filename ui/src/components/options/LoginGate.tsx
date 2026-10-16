"use client";
import { useState, type FormEvent, type ReactNode } from "react";
import { KeyRound, Lock } from "lucide-react";
import { setToken } from "@/lib/optionsApi";

/** Shown instead of the page when the API answers 401 (DASHBOARD_TOKEN is set). */
export function LoginGate({ needsLogin, children }: { needsLogin: boolean; children: ReactNode }) {
  const [value, setValue] = useState("");
  if (!needsLogin) return <>{children}</>;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) setToken(value.trim());
  };

  return (
    <div className="min-h-[60vh] grid place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-surface border border-[#1e2d45] rounded-2xl p-7 shadow-[0_20px_60px_rgba(0,0,0,.45)]">
        <div className="w-12 h-12 rounded-xl grid place-items-center mb-5 bg-[#ff993314] border border-[#ff993333]">
          <Lock size={20} className="text-[#ff9933]" />
        </div>
        <h1 className="text-lg font-bold text-[#e2e8f0]">Dashboard login</h1>
        <p className="text-sm text-[#64748b] mt-1 mb-5 leading-relaxed">
          Live market data is for your personal use, so this dashboard is password-protected.
          Enter the <span className="font-mono text-[#94a3b8]">DASHBOARD_TOKEN</span> set on the API.
        </p>
        <label htmlFor="dash-token" className="text-[10px] tracking-widest text-[#64748b]">PASSWORD</label>
        <div className="mt-1.5 flex items-center gap-2 bg-card border border-[#1e2d45] rounded-lg px-3 focus-within:border-[#ff9933] transition-colors">
          <KeyRound size={14} className="text-[#64748b]" />
          <input id="dash-token" type="password" autoComplete="current-password" value={value}
                 onChange={e => setValue(e.target.value)}
                 className="flex-1 bg-transparent py-2.5 text-sm text-[#e2e8f0] outline-none placeholder:text-[#475569]"
                 placeholder="••••••••" />
        </div>
        <button type="submit"
                className="mt-4 w-full rounded-lg bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] font-semibold text-sm py-2.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]">
          Unlock dashboard
        </button>
      </form>
    </div>
  );
}
