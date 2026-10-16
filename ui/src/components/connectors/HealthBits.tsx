"use client";
import { AlertTriangle, CheckCircle2, CircleDashed, MinusCircle, XCircle } from "lucide-react";
import type { CheckStatus, HealthResult } from "@/types/auth";
import { cn } from "@/lib/utils";
import { LiveAge } from "@/components/common/LiveAge";

export const CHECK_STYLE: Record<CheckStatus | "none", { icon: typeof CheckCircle2; text: string; label: string; ring: string; bar: string }> = {
  ok:   { icon: CheckCircle2,  text: "text-green",     label: "Healthy",     ring: "border-[#22c55e33] bg-[#22c55e0d]", bar: "bg-green" },
  warn: { icon: AlertTriangle, text: "text-yellow",    label: "Attention",   ring: "border-[#f59e0b33] bg-[#f59e0b0d]", bar: "bg-yellow" },
  fail: { icon: XCircle,       text: "text-red",       label: "Failing",     ring: "border-[#ef444433] bg-[#ef44440d]", bar: "bg-red" },
  skip: { icon: MinusCircle,   text: "text-[#94a3b8]", label: "Skipped",     ring: "border-[#1e2d45] bg-card",          bar: "bg-[#475569]" },
  none: { icon: CircleDashed,  text: "text-[#64748b]", label: "Not checked", ring: "border-[#1e2d45] bg-card",          bar: "bg-[#334155]" },
};

export function CheckBadge({ status }: { status: CheckStatus | null | undefined }) {
  const S = CHECK_STYLE[status ?? "none"];
  return (
    <span className={cn("inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md border whitespace-nowrap", S.text, S.ring)}>
      <S.icon size={11} /> {S.label}
    </span>
  );
}

export function CheckMeta({ result }: { result: HealthResult | null | undefined }) {
  if (!result) return <span className="text-[11px] text-[#475569]">Never tested</span>;
  return (
    <span className="text-[11px] text-[#64748b]">
      checked <LiveAge iso={result.checked_at} />{result.latency_ms != null ? ` · ${result.latency_ms.toLocaleString("en-IN")} ms` : ""}
    </span>
  );
}
