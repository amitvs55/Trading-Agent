"use client";
import type { PillarCheck } from "@/types/options";
import { cn } from "@/lib/utils";
import { PILLAR_LABELS } from "@/lib/optionsFormat";
import { STATUS_STYLE } from "./StatusBits";

export function ChecksList({ checks }: { checks: PillarCheck[] }) {
  return (
    <ul className="divide-y divide-[#1e2d45]">
      {checks.map(c => {
        const S = STATUS_STYLE[c.status];
        return (
          <li key={c.pillar} className="flex items-start gap-3 py-2.5">
            <S.icon size={15} className={cn(S.text, "mt-0.5 flex-shrink-0")} aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-[#e2e8f0]">{PILLAR_LABELS[c.pillar] ?? c.pillar}</span>
                <span className={cn("text-[9px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded border", S.text, S.ring)}>{S.label}</span>
              </div>
              <p className="text-[12px] text-[#94a3b8] mt-0.5 leading-snug break-words">{c.detail}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
