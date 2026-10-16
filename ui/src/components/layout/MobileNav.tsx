"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { displayName, initials, ROLE_LABEL } from "@/lib/people";
import { useAuth } from "@/components/auth/AuthGate";
import { ACCOUNT_ITEM, isActive, navFor, type NavItem } from "./nav";

function Tab({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link href={item.href} aria-current={active ? "page" : undefined}
          className={cn("flex-1 min-w-0 flex flex-col items-center justify-center gap-0.5 h-14 text-[10px] font-medium transition-colors",
            active ? "text-[#ff9933]" : "text-[#64748b] active:text-[#e2e8f0]")}>
      <span className={cn("grid place-items-center w-10 h-7 rounded-full transition-colors", active && "bg-[#ff99331f]")}>
        <Icon size={18} strokeWidth={active ? 2.4 : 2} />
      </span>
      <span className="truncate max-w-full">{item.label}</span>
    </Link>
  );
}

/**
 * Phones and tablets (below lg): a fixed bottom tab bar with the main pages, and a "More" sheet
 * with the rest, your account and sign-out. Desktop keeps the top bar (Navbar).
 */
export function MobileNav() {
  const auth = useAuth();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const user = auth?.user;
  const items = navFor(user?.role);
  const tabs = items.filter(i => i.primary);
  const rest = [...items.filter(i => !i.primary), ACCOUNT_ITEM];
  const moreActive = !open && rest.some(i => isActive(path, i.href));

  useEffect(() => { setOpen(false); }, [path]);                 // navigating closes the sheet
  useEffect(() => {                                              // closed sheet: not focusable, not read out
    const el = sheetRef.current;
    if (!el) return;
    if (open) el.removeAttribute("inert"); else el.setAttribute("inert", "");
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";                     // no scrolling the page behind the sheet
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    sheetRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    return () => { document.body.style.overflow = prev; document.removeEventListener("keydown", onKey); };
  }, [open]);

  if (!auth) return null;
  return (
    <>
      <nav aria-label="Main" className="lg:hidden fixed inset-x-0 bottom-0 z-50 border-t border-[#1e2d45] bg-[#111827f2] backdrop-blur-md pb-[env(safe-area-inset-bottom)]">
        <div className="flex items-stretch px-1">
          {tabs.map(t => <Tab key={t.href} item={t} active={isActive(path, t.href)} />)}
          <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} aria-controls="more-sheet"
                  className={cn("flex-1 min-w-0 flex flex-col items-center justify-center gap-0.5 h-14 text-[10px] font-medium transition-colors",
                    open || moreActive ? "text-[#ff9933]" : "text-[#64748b]")}>
            <span className={cn("grid place-items-center w-10 h-7 rounded-full transition-colors", (open || moreActive) && "bg-[#ff99331f]")}>
              {open ? <X size={18} /> : <Menu size={18} />}
            </span>
            More
          </button>
        </div>
      </nav>

      {/* The sheet stays mounted so it can slide both ways; inert and hidden from readers when closed */}
      <div className={cn("lg:hidden fixed inset-0 z-40 transition-opacity duration-200", open ? "opacity-100" : "opacity-0 pointer-events-none")}
           aria-hidden={!open}>
        <button type="button" aria-label="Close menu" tabIndex={-1} onClick={() => setOpen(false)}
                className="absolute inset-0 w-full h-full bg-[#0b0f1acc] backdrop-blur-[2px]" />
        <div id="more-sheet" ref={sheetRef} role="dialog" aria-modal="true" aria-label="More"
             className={cn("absolute inset-x-0 bottom-0 rounded-t-2xl border-t border-[#1e2d45] bg-surface shadow-[0_-16px_40px_rgba(0,0,0,.5)]",
               "pb-[calc(56px+env(safe-area-inset-bottom))] transition-transform duration-300 ease-[cubic-bezier(0.2,0,0,1)]",
               open ? "translate-y-0" : "translate-y-full")}>
          <div className="mx-auto mt-2.5 mb-1 h-1 w-10 rounded-full bg-[#334155]" aria-hidden />
          {user && (
            <div className="flex items-center gap-3 px-5 py-3 border-b border-[#1e2d45]">
              <span className="w-11 h-11 rounded-xl grid place-items-center bg-[#ff993326] text-[#ff9933] text-sm font-bold">{initials(user)}</span>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[#e2e8f0] truncate">{displayName(user)}</div>
                <div className="text-[11px] text-[#64748b]">@{user.username} · {ROLE_LABEL[user.role] ?? user.role}</div>
              </div>
            </div>
          )}
          <ul className="grid grid-cols-2 gap-2 p-4">
            {rest.map(item => {
              const Icon = item.icon;
              const active = isActive(path, item.href);
              return (
                <li key={item.href}>
                  <Link href={item.href} onClick={() => setOpen(false)} aria-current={active ? "page" : undefined}
                        className={cn("flex items-center gap-3 h-14 px-4 rounded-xl border text-sm font-medium transition-colors",
                          active ? "border-[#ff993355] bg-[#ff993314] text-[#ff9933]" : "border-[#1e2d45] bg-card text-[#e2e8f0] active:border-[#2d3e58]")}>
                    <Icon size={18} className={active ? "text-[#ff9933]" : "text-[#94a3b8]"} /> {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="px-4">
            <button type="button" onClick={() => auth.logout()}
                    className="w-full h-12 flex items-center justify-center gap-2 rounded-xl border border-[#1e2d45] text-sm text-[#fca5a5] active:bg-[#ef44440d]">
              <LogOut size={16} /> Sign out
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
