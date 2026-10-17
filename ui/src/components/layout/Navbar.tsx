"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, MoreHorizontal, PlugZap, TrendingUp, UserRound } from "lucide-react";
import { useAuth } from "@/components/auth/AuthGate";
import { cn } from "@/lib/utils";
import { displayName, initials, ROLE_LABEL } from "@/lib/people";
import { useOptionsApi } from "@/lib/optionsApi";
import { fmtNum } from "@/lib/optionsFormat";
import type { BoardResponse } from "@/types/options";
import { LiveClock } from "./LiveClock";
import { BAR_CLASS, MORE_CLASS, isActive, navFor, type NavItem } from "./nav";


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
    return <div className="flex-shrink-0 h-[34px] w-[50px] 2xl:w-[96px] rounded-lg border border-[#1e2d45] bg-card" aria-hidden />;
  }
  const name = displayName(user);
  return (
    <div className="relative flex-shrink-0" ref={ref}>
      <button onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open} aria-label={`${initials(user)}: account menu for ${name}`}
              className="flex items-center gap-2 h-[34px] rounded-lg border border-[#1e2d45] bg-card pl-1 pr-2 hover:border-[#2d3e58] transition-colors">
        <span className="w-6 h-6 rounded-md grid place-items-center bg-[#ff993326] text-[#ff9933] text-[10px] font-bold tracking-wide">{initials(user)}</span>
        <span className="hidden 2xl:inline text-xs text-[#e2e8f0] max-w-[120px] truncate">{name}</span>
        <ChevronDown size={12} className={cn("text-[#8391a7] transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && (
        <div role="menu" className="menu-pop absolute right-0 mt-2 w-56 rounded-xl border border-[#1e2d45] bg-surface shadow-[0_16px_40px_rgba(0,0,0,.5)] p-1.5 z-50">
          <div className="px-3 py-2 border-b border-[#1e2d45] mb-1">
            <div className="text-sm font-semibold text-[#e2e8f0] truncate">{name}</div>
            <div className="text-[10px] tracking-widest text-[#8391a7] uppercase">@{user.username} · {ROLE_LABEL[user.role] ?? user.role}</div>
          </div>
          <Link href="/account" role="menuitem" onClick={() => setOpen(false)}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[#94a3b8] hover:bg-card hover:text-[#e2e8f0]">
            <UserRound size={14} /> {user.role === "admin" ? "Your account & users" : "Your account"}
          </Link>
          {user.role === "admin" && (
            <Link href="/connectors" role="menuitem" onClick={() => setOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[#94a3b8] hover:bg-card hover:text-[#e2e8f0]">
              <PlugZap size={14} /> Connectors &amp; health
            </Link>
          )}
          <button role="menuitem" onClick={() => auth.logout()}
                  className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[#94a3b8] hover:bg-card hover:text-[#fca5a5]">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/** Links that don't fit the desktop bar at the current width (by tier) live under "More". */
function NavMore({ items, path }: { items: NavItem[]; path: string }) {
  const [open, setOpen] = useState(false);
  const [shownFor, setShownFor] = useState(path);
  if (shownFor !== path) {                             // navigated: close the menu
    setShownFor(path);
    setOpen(false);
  }
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (!items.length) return null;
  const activeTier = items.find(i => isActive(path, i.href))?.tier;
  return (
    <div className="relative hidden lg:inline-flex 2xl:hidden" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}
              className={cn("inline-flex items-center gap-1 px-2 xl:px-2.5 py-1 text-sm font-medium border-b-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] rounded-sm",
                activeTier === 3 ? "text-[#ff9933]" : activeTier === 2 ? "text-[#ff9933] xl:text-[#94a3b8]" : "text-[#94a3b8] hover:text-[#e2e8f0]")}>
        <MoreHorizontal size={15} aria-hidden /> More <ChevronDown size={12} className={cn("transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="menu-pop absolute right-0 top-full mt-2 w-52 rounded-xl border border-[#1e2d45] bg-surface shadow-[0_16px_40px_rgba(0,0,0,.5)] p-1.5 z-50">
          {items.map(({ href, label, icon: Icon, tier }) => (
            <Link key={href} href={href} role="menuitem" aria-current={isActive(path, href) ? "page" : undefined}
                  className={cn(MORE_CLASS[tier], "items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]",
                    isActive(path, href) ? "text-[#ff9933]" : "text-[#cbd5e1] hover:text-[#e2e8f0]")}>
              <Icon size={14} aria-hidden /> {label}
            </Link>
          ))}
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
            <span className="text-xs text-[#8391a7]">{b.index === "NIFTY" ? "NIFTY 50" : b.index}</span>
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
          <div className="flex items-center gap-2"><span className="text-xs text-[#8391a7]">INDIA VIX</span><span className="text-xs font-mono font-bold text-[#e2e8f0]">{fmtNum(vix, 2)}</span></div>
        </>
      )}
    </div>
  );
}

export function Navbar() {
  const path = usePathname();
  const auth = useAuth();
  const links = navFor(auth?.user?.role);

  return (
    <nav className="sticky top-0 z-50 bg-surface border-b border-[#1e2d45] pt-[env(safe-area-inset-top)]">
      <div className="india-stripe" />
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">

        {/* Logo (on phones the bar has room for the name; on laptops the links need it) */}
        <Link href="/signals" className="flex items-center gap-3 flex-shrink-0" aria-label="TradingAgents India, live signals">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(255,153,51,.15)", border: "1px solid rgba(255,153,51,.35)" }}>
            <TrendingUp size={15} className="text-[#ff9933]" />
          </div>
          <div className="block lg:hidden 2xl:block">
            <span className="font-bold text-sm tracking-wide text-[#ff9933]">TradingAgents</span>{" "}
            <span className="text-[#8391a7] text-xs ml-1 hidden min-[400px]:inline">India</span>
          </div>
        </Link>

        <div className="hidden 2xl:flex flex-1 min-w-0 justify-center"><LiveIndices /></div>

        {/* Nav links: desktop only (phones and tablets use MobileNav's bottom bar) */}
        <div className="hidden lg:flex items-center gap-0.5">
          {links.map(({ href, label, tier }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(path, href) ? "page" : undefined}
              className={cn(
                BAR_CLASS[tier],
                "px-2 xl:px-2.5 2xl:px-3 py-1 text-sm font-medium transition-colors border-b-2 whitespace-nowrap",
                isActive(path, href)
                  ? "text-[#ff9933] border-[#ff9933]"
                  : "text-[#94a3b8] border-transparent hover:text-[#e2e8f0]"
              )}
            >
              {label}
            </Link>
          ))}
          <NavMore items={links.filter(l => l.tier > 1)} path={path} />
        </div>

        {/* Right */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <LiveClock />
          <div className="hidden lg:block"><UserMenu /></div>
        </div>
      </div>
    </nav>
  );
}
