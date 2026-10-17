"use client";
import { Activity, BellRing, Bot, CalendarDays, Cpu, Database, Globe2, Loader2, Mail, Radio, Send, Signal } from "lucide-react";
import type { HealthResponse } from "@/types/auth";
import { cn } from "@/lib/utils";
import { CHECK_STYLE, CheckMeta } from "./HealthBits";

const ORDER: { id: string; icon: typeof Database }[] = [
  { id: "database", icon: Database }, { id: "recorder", icon: Cpu }, { id: "market_data", icon: Activity },
  { id: "angel", icon: Signal }, { id: "kite", icon: Radio }, { id: "telegram", icon: Send },
  { id: "email", icon: Mail }, { id: "alerts", icon: BellRing }, { id: "calendar", icon: CalendarDays },
  { id: "openai", icon: Bot }, { id: "macro", icon: Globe2 },
];

export function HealthOverview({ health, running }: { health: HealthResponse | undefined; running: Set<string> }) {
  const results = health?.results ?? {};
  const counted = ORDER.map(o => results[o.id]?.status).filter(Boolean);
  const failing = counted.filter(s => s === "fail").length;
  const warnings = counted.filter(s => s === "warn").length;

  return (
    <section aria-label="System health">
      <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
        <h2 className="text-sm font-semibold text-[#e2e8f0]">System health</h2>
        <span className={cn("text-xs", failing ? "text-red" : warnings ? "text-yellow" : counted.length ? "text-green" : "text-[#8391a7]")}>
          {!counted.length ? "No checks run yet" : failing ? `${failing} failing` + (warnings ? ` · ${warnings} need attention` : "")
            : warnings ? `${warnings} need attention` : "All checks healthy"}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {ORDER.map(({ id, icon: Icon }) => {
          const r = results[id];
          const S = CHECK_STYLE[r?.status ?? "none"];
          const busy = running.has(id);
          return (
            <div key={id} className="relative bg-surface border border-[#1e2d45] rounded-xl p-3.5 overflow-hidden min-w-0">
              <div className={cn("absolute left-0 inset-y-0 w-0.5", S.bar, busy && "animate-pulse")} />
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 min-w-0">
                  <Icon size={14} className="text-[#8391a7] flex-shrink-0" />
                  <span className="text-xs font-semibold text-[#e2e8f0] truncate">{health?.checks[id] ?? id}</span>
                </span>
                {busy ? <Loader2 size={15} className="text-[#ff9933] animate-spin flex-shrink-0" aria-label="Checking" />
                      : <S.icon size={15} className={cn(S.text, "flex-shrink-0")} aria-label={S.label} />}
              </div>
              <p className="text-[12px] text-[#94a3b8] leading-snug mt-2 line-clamp-2 min-h-[2.4em]" title={r?.message}>
                {busy ? "Checking…" : r?.message ?? "Not checked yet"}
              </p>
              <div className="mt-1.5"><CheckMeta result={r} /></div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
