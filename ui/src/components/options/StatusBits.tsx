"use client";
import { AlertTriangle, CheckCircle2, CircleDot, MinusCircle, XCircle, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import type { SignalState, Status } from "@/types/options";
import { cn } from "@/lib/utils";

// Status always ships as icon + word, never colour alone.
export const STATUS_STYLE: Record<Status, { icon: typeof CheckCircle2; text: string; label: string; ring: string }> = {
  pass: { icon: CheckCircle2,  text: "text-green",       label: "Pass",    ring: "border-[#22c55e33] bg-[#22c55e0d]" },
  warn: { icon: AlertTriangle, text: "text-yellow",      label: "Caution", ring: "border-[#f59e0b33] bg-[#f59e0b0d]" },
  fail: { icon: XCircle,       text: "text-red",         label: "Against", ring: "border-[#ef444433] bg-[#ef44440d]" },
  na:   { icon: MinusCircle,   text: "text-[#8391a7]",   label: "No data", ring: "border-[#1e2d45] bg-card" },
};

export function StatusIcon({ status, size = 14, className }: { status: Status; size?: number; className?: string }) {
  const S = STATUS_STYLE[status];
  return <S.icon size={size} className={cn(S.text, "flex-shrink-0", className)} aria-label={S.label} />;
}

export function BiasMark({ bias, status, size = 12 }: { bias: number; status: Status | null; size?: number }) {
  if (status) {
    const S = STATUS_STYLE[status];
    return (
      <span className={cn("inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider", S.text)}>
        <S.icon size={size} /> {S.label}
      </span>
    );
  }
  if (bias > 0) return <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-green"><ArrowUpRight size={size} /> Bullish</span>;
  if (bias < 0) return <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-red"><ArrowDownRight size={size} /> Bearish</span>;
  return <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[#94a3b8]"><Minus size={size} /> Neutral</span>;
}

const STATE_STYLE: Record<SignalState, { label: string; cls: string; live?: boolean }> = {
  TRIGGERED: { label: "Waiting for entry", cls: "text-[#ff9933] border-[#ff993344] bg-[#ff99330f]", live: true },
  ACTIVE:    { label: "In trade",          cls: "text-[#60a5fa] border-[#3987e544] bg-[#3987e50f]", live: true },
  T1_HIT:    { label: "T1 hit · trailing", cls: "text-green border-[#22c55e44] bg-[#22c55e0f]", live: true },
  CLOSED:    { label: "Closed",            cls: "text-[#94a3b8] border-[#1e2d45] bg-card" },
  EXPIRED:   { label: "Not filled",        cls: "text-[#8391a7] border-[#1e2d45] bg-card" },
  CANCELLED: { label: "Cancelled",         cls: "text-[#8391a7] border-[#1e2d45] bg-card" },
};

export function StateBadge({ state }: { state: SignalState }) {
  const s = STATE_STYLE[state];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-md border whitespace-nowrap", s.cls)}>
      {s.live ? <span className="relative flex w-1.5 h-1.5"><span className="absolute inset-0 rounded-full bg-current opacity-60 animate-ping" /><span className="relative w-1.5 h-1.5 rounded-full bg-current" /></span>
              : <CircleDot size={10} />}
      {s.label}
    </span>
  );
}

export function GradeBadge({ grade, score }: { grade: string; score: number }) {
  return (
    <span className={cn(
      "inline-flex items-baseline gap-1 px-2 py-0.5 rounded-md border font-mono text-xs font-bold",
      grade === "A" ? "text-[#ff9933] border-[#ff993355] bg-[#ff993314]" : "text-[#e2e8f0] border-[#1e2d45] bg-card",
    )} title={`Confluence score ${score.toFixed(0)} of 100`}>
      {grade}<span className="text-[10px] font-normal text-[#94a3b8]">{score.toFixed(0)}</span>
    </span>
  );
}

export function ModeTag({ mode }: { mode: "SHADOW" | "LIVE" }) {
  return mode === "LIVE"
    ? <span className="text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded bg-[#22c55e1a] text-green border border-[#22c55e33]">LIVE</span>
    : <span className="text-[10px] font-bold tracking-widest px-1.5 py-0.5 rounded bg-card text-[#94a3b8] border border-[#1e2d45]" title="Shadow test: tracked automatically, not yet approved for trading">SHADOW</span>;
}

export function DirectionPill({ action }: { action: "BUY_CE" | "BUY_PE" }) {
  const up = action === "BUY_CE";
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold tracking-wide border",
      up ? "text-green border-[#22c55e44] bg-[#22c55e14]" : "text-red border-[#ef444444] bg-[#ef444414]",
    )}>
      {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />} {up ? "BUY CE" : "BUY PE"}
    </span>
  );
}
