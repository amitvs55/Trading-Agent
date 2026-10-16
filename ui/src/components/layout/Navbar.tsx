"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, PlugZap, TrendingUp } from "lucide-react";
import { useAuth } from "@/components/auth/AuthGate";
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
  { href: "/connectors",  label: "Connectors"  },
];

function UserMenu() {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  if (!auth) return null;
  const user = auth.user;
  if (!user) {
    // Same footprint as the real button, so nothing moves when the profile arrives
    return <div className="flex-shrink-0 h-[34px] w-[34px] md:w-[96px] rounded-lg border border-[#1e2d45] bg-card" aria-hidden />;
  }
  const initial = user.username.slice(0, 1).toUpperCase();
  return (
    <div className="relative flex-shrink-0" ref={ref}>
      <button onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}
              className="flex items-center gap-2 h-[34px] rounded-lg border border-[#1e2d45] bg-card pl-1 pr-2 hover:border-[#2d3e58] transition-colors">
        <span className="w-6 h-6 rounded-md grid place-items-center bg-[#ff993326] text-[#ff9933] text-xs font-bold">{initial}</span>
        <span className="hidden md:inline text-xs text-[#e2e8f0]">{user.username}</span>
        <ChevronDown size={12} className={cn("text-[#64748b] transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && (
        <div role="menu" className="menu-pop absolute right-0 mt-2 w-56 rounded-xl border border-[#1e2d45] bg-surface shadow-[0_16px_40px_rgba(0,0,0,.5)] p-1.5 z-50">
          <div className="px-3 py-2 border-b border-[#1e2d45] mb-1">
            <div className="text-sm font-semibold text-[#e2e8f0]">{user.username}</div>
            <div className="text-[10px] tracking-widest text-[#64748b] uppercase">{user.role}</div>
          </div>
          <Link href="/connectors" role="menuitem" onClick={() => setOpen(false)}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[#94a3b8] hover:bg-card hover:text-[#e2e8f0]">
            <PlugZap size={14} /> Connectors &amp; health
          </Link>
          <button role="menuitem" onClick={() => auth.logout()}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[#94a3b8] hover:bg-card hover:text-[#fca5a5]">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

// Live values only: nothing is shown until the signal engine has published a board. The slot it
// sits in is always there (see Navbar), so the links beside it never move when it fills in.
function LiveIndices() {
  const { data } = useOptionsApi<BoardResponse>("/api/options/board", 30_000);
  const boards = Object.values(data?.boards ?? {});
  if (!boards.length) return null;
  const vix = boards[0].vix;
  return (
    <div className="fade-in flex items-center gap-5">
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
  const open = !!data && ["opening", "main", "late", "closing"].includes(data.session_phase);
  return (
    <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-card border border-[#1e2d45]">
      <div className={cn("w-2 h-2 rounded-full transition-colors", open ? "bg-green animate-pulse" : "bg-[#475569]")} />
      <span className={cn("transition-colors", open ? "text-green" : "text-[#94a3b8]")}>
        {!data ? "NSE" : open ? "NSE open" : PHASE_LABELS[data.session_phase] ?? "NSE closed"}
      </span>
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

        <div className="hidden xl:flex flex-1 min-w-0 justify-center"><LiveIndices /></div>

        {/* Nav links */}
        <div className="flex items-center gap-0.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [mask-image:linear-gradient(90deg,#000_82%,transparent)] lg:[mask-image:none]">
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
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="hidden 2xl:block"><MarketPill /></div>
          <UserMenu />
        </div>
      </div>
    </nav>
  );
}
