"use client";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import type { CheckContractRef, ResolveResponse } from "@/types/check";
import { apiJson } from "@/lib/optionsApi";
import { fmtDate } from "@/lib/optionsFormat";
import { cn } from "@/lib/utils";

/** What the typed text means, as you type: the exact listed contract, or the problem and real alternatives. */
export function useResolve(text: string) {
  const [state, setState] = useState<{ q: string; res: ResolveResponse | null; busy: boolean }>({ q: "", res: null, busy: false });
  const seq = useRef(0);
  useEffect(() => {
    const q = text.trim();
    if (q.length < 3) return;
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      setState(s => ({ ...s, busy: true }));
      try {
        const res = await apiJson<ResolveResponse>(`/api/options/check/resolve?q=${encodeURIComponent(q)}`);
        if (mine === seq.current) setState({ q, res, busy: false });
      } catch {
        if (mine === seq.current) setState(s => ({ ...s, busy: false }));
      }
    }, 220);
    return () => clearTimeout(t);
  }, [text]);
  const current = text.trim().length >= 3 ? state : { q: "", res: null, busy: false };
  return current;
}

export function contractText(c: CheckContractRef): string {
  const d = new Date(`${c.expiry}T00:00:00+05:30`);
  const day = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
  return `NIFTY ${day} ${c.strike} ${c.right}`;
}

export function ContractInput({ value, onChange, onPick, disabled, onResolved, id = "check-contract" }: {
  value: string; onChange: (v: string) => void; onPick: (text: string) => void; disabled?: boolean;
  onResolved?: (c: CheckContractRef | null) => void; id?: string;
}) {
  const { res, busy } = useResolve(value);
  const ok = res?.ok && res.contract;
  const picked = ok ? res!.contract! : null;
  const lastToken = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    if (!onResolved || busy || lastToken.current === (picked?.token ?? null)) return;
    lastToken.current = picked?.token ?? null;
    onResolved(picked);
  }, [picked, busy, onResolved]);
  return (
    <div>
      <label htmlFor={id} className="text-[10px] tracking-widest text-[#8391a7]">CONTRACT</label>
      <input id={id} value={value} onChange={e => onChange(e.target.value)} disabled={disabled}
             autoComplete="off" spellCheck={false} placeholder="e.g. Nifty 27th Oct 25000 ce"
             aria-describedby={`${id}-status`}
             className="mt-1.5 w-full bg-card border border-[#1e2d45] rounded-lg px-3 h-11 text-[15px] text-[#e2e8f0] placeholder:text-[#64748b] focus:outline-none focus:border-[#ff9933] focus:ring-2 focus:ring-[#ff993333]" />
      {/* One fixed-height line, so the form never jumps while it reads what you type */}
      <div id={`${id}-status`} aria-live="polite" className="h-5 mt-1.5 flex items-center gap-1.5 text-[12px] min-w-0">
        {value.trim().length < 3 ? <span className="text-[#8391a7] truncate">Index, expiry, strike and CE/PE, in any order</span>
          : busy && !res ? <><Loader2 size={12} className="animate-spin text-[#8391a7]" aria-hidden /><span className="text-[#8391a7]">Reading…</span></>
          : ok ? <><CheckCircle2 size={13} className="text-green flex-shrink-0" aria-hidden />
                   <span className="text-[#e2e8f0] truncate font-mono">{res!.contract!.symbol}</span>
                   <span className="text-[#8391a7] truncate">· expires {fmtDate(res!.contract!.expiry)} · lot {res!.contract!.lot_size}</span></>
          : res?.problem ? <><AlertTriangle size={13} className="text-yellow flex-shrink-0" aria-hidden />
                             <span className="text-yellow truncate">{res.problem}</span></>
          : null}
      </div>
      <div className="h-7 mt-1 flex items-center gap-1.5 overflow-x-auto overflow-y-hidden" role="group" aria-label="Suggestions">
        {!ok && res?.suggestions.slice(0, 6).map(s => (
          <button key={s.token} type="button" onClick={() => onPick(contractText(s))}
                  className={cn("flex-shrink-0 h-6 px-2 rounded-md border border-[#1e2d45] bg-card text-[11px] font-mono text-[#cbd5e1]",
                                "hover:border-[#ff993366] hover:text-[#ff9933] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]")}>
            {contractText(s)}
          </button>
        ))}
      </div>
    </div>
  );
}
