"use client";
import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type StageStatus = "pending" | "running" | "complete";

interface Props {
  stageNumber: number;
  title:       string;
  subtitle?:   string;
  status:      StageStatus;
  badge?:      ReactNode;
  children?:   ReactNode;
  defaultOpen?: boolean;
}

export function StageCard({ stageNumber, title, subtitle, status, badge, children, defaultOpen }: Props) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  const canExpand = status === "complete" && !!children;

  return (
    <div className={cn(
      "rounded-xl border overflow-hidden transition-all",
      status === "complete" && "border-[#22c55e44] bg-surface",
      status === "running"  && "border-[#ff993344] bg-surface animate-stage-pulse",
      status === "pending"  && "border-[#1e2d45] bg-surface opacity-50",
    )}>
      {/* Header */}
      <div
        className={cn("flex items-center justify-between px-5 py-4", canExpand && "cursor-pointer")}
        onClick={() => canExpand && setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          {/* Icon */}
          <div className={cn(
            "w-7 h-7 rounded-lg flex items-center justify-center border",
            status === "complete" && "bg-[#22c55e22] border-[#22c55e44]",
            status === "running"  && "bg-[#ff993311] border-[#ff993344]",
            status === "pending"  && "bg-card border-[#1e2d45]",
          )}>
            {status === "complete" && <Check size={11} className="text-green" strokeWidth={3} />}
            {status === "running"  && <Loader2 size={11} className="text-[#ff9933] animate-spin" />}
            {status === "pending"  && <span className="text-[10px] font-bold text-[#8391a7]">{stageNumber}</span>}
          </div>

          {/* Text */}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm text-[#e2e8f0]">{title}</span>
              {status === "complete" && (
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[#22c55e22] text-green">COMPLETE</span>
              )}
              {status === "running" && (
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[#ff993311] text-[#ff9933] border border-[#ff993333]">RUNNING</span>
              )}
              {status === "pending" && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-card text-[#8391a7]">PENDING</span>
              )}
            </div>
            {subtitle && <div className="text-xs mt-0.5 text-[#8391a7]">{subtitle}</div>}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {badge}
          {canExpand && (
            <ChevronDown
              size={15}
              className={cn("text-[#8391a7] transition-transform", open && "rotate-180")}
            />
          )}
          {status === "running" && (
            <div className="flex gap-1">
              {[0, 0.2, 0.4].map(d => (
                <div key={d} className="w-1 h-1 rounded-full bg-[#ff9933] animate-pulse" style={{ animationDelay: `${d}s` }} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Body — accordion */}
      {status === "running" && (
        <div className="border-t border-[#1e2d45] p-5">
          <SkeletonBlock />
        </div>
      )}

      {status === "complete" && children && (
        <div className={cn("border-t border-[#1e2d45]", open ? "accordion-open" : "accordion-close")}>
          {children}
        </div>
      )}
    </div>
  );
}

function SkeletonBlock() {
  return (
    <div className="flex flex-col gap-3">
      <div className="skeleton h-4 w-1/3 rounded" />
      <div className="skeleton h-3 w-2/3 rounded" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
        {[1,2,3,4].map(i => <div key={i} className="skeleton h-16 rounded-lg" />)}
      </div>
    </div>
  );
}
