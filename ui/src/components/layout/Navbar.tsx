"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOptionsApi } from "@/lib/optionsApi";
import { fmtNum, PHASE_LABELS } from "@/lib/optionsFormat";
import type { BoardResponse, OptionsStatus } from "@/types/options";

const LINKS = [
  { href: "/signals",     label: "Signals"     },
  { href: "/performance", label: "Performance" },
  { href: "/",            label: "Research"    },
  { href: "/history",     label: "History"     },
  { href: "/usage",       label: "Usage"       },
];

// Live values only: nothing is shown until the signal engine has published a board.
function LiveIndices() {
  const { data } = useOptionsApi<BoardResponse>("/api/options/board", 30_000);
  const boards = Object.values(data?.boards ?? {});
  if (!boards.length) return null;
  const vix = boards[0].vix;
  return (
    <div className="hidden xl:flex items-center gap-5">
      {boards.map((b, i) => (
        <div key={b.index} className="flex items-center gap-5">
          {i > 0 && <div className="w-px h-3.5 bg-[#1e2d45]" />}
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#64748b]">{b.index === "NIFTY" ? "NIFTY 50" : b.index}</span>
            <span className="text-xs font-mono font-bold text-[#e2e8f0]">{fmtNum(b.spot, 2)}</span>
            <span className={cn("text-[10px]", b.htf_trend === "up" ? "text-green" : b.htf_trend === "down" ? "text-red" : "text-[#94a3b8]")}>
              {b.htf_trend === "up" ? "▲ trend up" : b.htf_trend === "down" ? "▼ trend down" : "◆ flat"}
            </span>
          </div>
        </div>
      ))}
      {vix != null && (
        <>
          <div className="w-px h-3.5 bg-[#1e2d45]" />
          <div className="flex items-center gap-2"><span className="text-xs text-[#64748b]">INDIA VIX</span><span className="text-xs font-mono font-bold text-[#e2e8f0]">{fmtNum(vix, 2)}</span></div>
        </>
      )}
    </div>
  );
}

function MarketPill() {
  const { data } = useOptionsApi<OptionsStatus>("/api/options/status", 60_000);
  if (!data) {
    return (
      <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-card border border-[#1e2d45]">
        <span className="text-[#64748b]">NSE 9:15–15:30 IST</span>
      </div>
    );
  }
  const open = ["opening", "main", "late", "closing"].includes(data.session_phase);
  return (
    <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-card border border-[#1e2d45]">
      <div className={cn("w-2 h-2 rounded-full", open ? "bg-green animate-pulse" : "bg-[#475569]")} />
      <span className={open ? "text-green" : "text-[#94a3b8]"}>{open ? "NSE open" : PHASE_LABELS[data.session_phase] ?? "NSE closed"}</span>
      <span className="text-[#64748b]">9:15–15:30 IST</span>
    </div>
  );
}

export function Navbar() {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`));

  return (
    <nav className="sticky top-0 z-50 bg-surface border-b border-[#1e2d45]">
      <div className="india-stripe" />
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">

        {/* Logo */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(255,153,51,.15)", border: "1px solid rgba(255,153,51,.35)" }}>
            <TrendingUp size={15} className="text-[#ff9933]" />
          </div>
          <div className="hidden sm:block">
            <span className="font-bold text-sm tracking-wide text-[#ff9933]">TradingAgents</span>
            <span className="text-[#64748b] text-xs ml-1.5">India</span>
          </div>
        </div>

        <LiveIndices />

        {/* Nav links */}
        <div className="flex items-center gap-0.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "px-3 py-1 text-sm font-medium transition-colors border-b-2 whitespace-nowrap",
                active(href)
                  ? "text-[#ff9933] border-[#ff9933]"
                  : "text-[#94a3b8] border-transparent hover:text-[#e2e8f0]"
              )}
            >
              {label}
            </Link>
          ))}
        </div>

        {/* Right */}
        <div className="hidden 2xl:flex items-center gap-3 flex-shrink-0">
          <MarketPill />
        </div>
      </div>
    </nav>
  );
}
