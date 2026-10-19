"use client";
import type { ReactNode } from "react";
import Link from "next/link";
import { Activity, Clock, LogIn, PauseCircle, Send, Shield, Wifi, WifiOff } from "lucide-react";
import type { OptionsStatus } from "@/types/options";
import { API_URL, cn } from "@/lib/utils";
import { fmtAge, fmtDate, fmtNum, PHASE_LABELS } from "@/lib/optionsFormat";
import { SessionBarSkeleton } from "./Skeletons";
import { useAuth } from "@/components/auth/AuthGate";
import { useNow } from "@/lib/clock";
import { DELAYED_AFTER_MS, useLiveIndices } from "@/lib/liveIndices";

function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className={cn(
      "flex flex-wrap items-center gap-x-2 gap-y-0.5 min-h-[34px] py-1.5 max-w-full text-xs px-3 rounded-lg border sm:whitespace-nowrap transition-colors",
      tone === "good" && "border-[#22c55e33] bg-[#22c55e0b]",
      tone === "warn" && "border-[#f59e0b33] bg-[#f59e0b0b]",
      tone === "bad" && "border-[#ef444433] bg-[#ef44440b]",
      tone === "neutral" && "border-[#1e2d45] bg-card",
    )}>{children}</div>
  );
}

// Setup links go to admin pages: viewers see the same chips without them
function SetupLink({ admin, href, children }: { admin: boolean; href: string; children: ReactNode }) {
  return admin ? <Link href={href} className="group">{children}</Link> : <>{children}</>;
}

/** Newest market data we know of: the live NIFTY tick, or the end of the last saved 1-minute bar
 *  (a bar is stamped with its start, so counting from that read "78s ago" when it was 18 s old). */
function useNewestData(lastBarAt: string | null | undefined): number | null {
  const tick = useLiveIndices().levels["NIFTY 50"]?.ts ?? 0;
  const barEnd = lastBarAt ? new Date(lastBarAt).getTime() + 60_000 : 0;
  return Math.max(tick, barEnd) || null;
}

function DataAge({ at }: { at: number | null }) {
  const now = useNow(1000);
  if (!at) return <>never</>;
  if (!now) return <>…</>;
  const ms = Math.max(0, now - at);
  return <>{ms <= DELAYED_AFTER_MS ? "live" : fmtAge(Math.round(ms / 1000))}</>;
}

export function SessionBar({ status }: { status: OptionsStatus | undefined }) {
  const admin = useAuth()?.user?.role === "admin";
  const newest = useNewestData(status?.last_bar_at);
  const coarse = useNow(15_000);
  if (!status) return <SessionBarSkeleton />;
  const open = ["opening", "main", "late", "closing"].includes(status.session_phase);
  const fresh = newest != null && coarse > 0 && coarse - newest < 180_000;

  return (
    <div className="fade-in flex gap-2 flex-wrap">
      <Chip tone={open ? "good" : "neutral"}>
        <span className={cn("w-2 h-2 rounded-full", open ? "bg-green animate-pulse" : "bg-[#475569]")} />
        <span className={open ? "text-green font-medium" : "text-[#94a3b8]"}>{PHASE_LABELS[status.session_phase] ?? status.session_phase}</span>
        {!status.trading_day && <span className="text-[#8391a7]">· next session {fmtDate(status.next_trading_day)}</span>}
      </Chip>

      {status.signals_paused && (
        <Chip tone="bad">
          <PauseCircle size={13} className="text-red" />
          <span className="text-red font-medium">New signals paused</span>
          <span className="text-[#94a3b8]">
            {status.signals_paused.by ? `by ${status.signals_paused.by}` : ""}
            {status.signals_paused.reason ? ` · ${status.signals_paused.reason}` : ""} · open signals still tracked
          </span>
        </Chip>
      )}

      {status.data_connected_today ? (
        <Chip tone="good"><Wifi size={13} className="text-green" /><span className="text-green font-medium">{status.data_provider_name} connected</span></Chip>
      ) : !status.data_configured ? (
        <SetupLink admin={admin} href="/connectors">
          <Chip tone="bad"><WifiOff size={13} className="text-red" /><span className="text-red font-medium">{status.data_provider_name} keys not set</span>
            {admin && <span className="text-[#ff9933] group-hover:underline">Set up</span>}</Chip>
        </SetupLink>
      ) : status.data_needs_manual_login ? (
        <a href={`${API_URL}/kite/login`} className="group">
          <Chip tone={status.trading_day ? "warn" : "neutral"}>
            <WifiOff size={13} className="text-yellow" />
            <span className="text-yellow font-medium">{status.data_provider_name} not logged in today</span>
            <span className="flex items-center gap-1 text-[#ff9933] group-hover:underline"><LogIn size={12} /> Log in</span>
          </Chip>
        </a>
      ) : (
        <Chip tone={open ? "warn" : "neutral"}>
          <WifiOff size={13} className={open ? "text-yellow" : "text-[#8391a7]"} />
          <span className={open ? "text-yellow font-medium" : "text-[#94a3b8]"}>
            {open ? `${status.data_provider_name} not connected yet` : `${status.data_provider_name} logs in at 08:30`}
          </span>
        </Chip>
      )}

      <Chip tone={fresh ? "good" : open ? "warn" : "neutral"}>
        <Activity size={13} className={fresh ? "text-green" : "text-[#8391a7]"} />
        <span className="text-[#94a3b8]">Market data</span>
        <span className="font-mono text-[#e2e8f0] inline-block min-w-[7ch]"><DataAge at={newest} /></span>
        <span className="text-[#8391a7]">· {fmtNum(status.bars_today)} bars today</span>
      </Chip>

      <SetupLink admin={admin} href="/connectors">
        <Chip tone={status.telegram_configured ? "neutral" : "warn"}>
          <Send size={13} className={status.telegram_configured ? "text-[#60a5fa]" : "text-yellow"} />
          <span className={status.telegram_configured ? "text-[#94a3b8]" : "text-yellow"}>
            {status.telegram_configured ? "Telegram alerts on" : "Telegram not set up"}
          </span>
          {!status.telegram_configured && admin && <span className="text-[#ff9933] group-hover:underline">Set up</span>}
        </Chip>
      </SetupLink>

      <Chip>
        <Shield size={13} className="text-[#ff9933]" />
        <span className="text-[#94a3b8]">Risk</span>
        <span className="font-mono text-[#e2e8f0]">{status.risk.risk_per_trade_pct}%/trade</span>
        <span className="text-[#8391a7]">·</span>
        <span className="font-mono text-[#e2e8f0]">{status.risk.daily_loss_stop_pct}% daily stop</span>
        <span className="text-[#8391a7]">· ₹{fmtNum(status.risk.capital)}</span>
      </Chip>

      <Chip>
        <Clock size={13} className="text-[#8391a7]" />
        <span className="text-[#94a3b8]">Signals on 5-min closes · 09:30–15:00</span>
      </Chip>
    </div>
  );
}
