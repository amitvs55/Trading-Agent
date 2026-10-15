"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

const INDICES = [
  { label: "NIFTY 50",   value: "22,147.90", change: "+0.48%", up: true },
  { label: "SENSEX",     value: "73,088.33", change: "+0.42%", up: true },
  { label: "BANK NIFTY", value: "47,832.15", change: "−0.31%", up: false },
];

export function Navbar() {
  const path = usePathname();

  return (
    <nav className="sticky top-0 z-50 bg-surface border-b border-[#1e2d45]">
      <div className="india-stripe" />
      <div className="max-w-screen-2xl mx-auto px-6 h-14 flex items-center justify-between gap-6">

        {/* Logo */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(255,153,51,.15)", border: "1px solid rgba(255,153,51,.35)" }}>
            <TrendingUp size={15} className="text-[#ff9933]" />
          </div>
          <div>
            <span className="font-bold text-sm tracking-wide text-[#ff9933]">TradingAgents</span>
            <span className="text-[#64748b] text-xs ml-1.5">India</span>
          </div>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-card text-[#64748b] font-mono">v1.0</span>
        </div>

        {/* Live indices */}
        <div className="hidden lg:flex items-center gap-5">
          {INDICES.map((idx, i) => (
            <div key={idx.label} className="flex items-center gap-5">
              {i > 0 && <div className="w-px h-3.5 bg-[#1e2d45]" />}
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#64748b]">{idx.label}</span>
                <span className={cn("text-xs font-mono font-bold", idx.up ? "text-green" : "text-red")}>{idx.value}</span>
                <span className={cn("text-xs", idx.up ? "text-green" : "text-red")}>{idx.up ? "▲" : "▼"} {idx.change}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {[
            { href: "/",        label: "Dashboard" },
            { href: "/history", label: "History"   },
          ].map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "px-4 py-1 text-sm font-medium transition-colors border-b-2",
                path === href
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
          <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-md bg-card border border-[#1e2d45]">
            <div className="w-2 h-2 rounded-full bg-green animate-pulse" />
            <span className="text-green">NSE Open</span>
            <span className="text-[#64748b]">9:15–15:30 IST</span>
          </div>
        </div>
      </div>
    </nav>
  );
}
