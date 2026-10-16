"use client";
import type { ReactNode } from "react";
import { Activity, Clock, LogIn, Send, Shield, Wifi, WifiOff } from "lucide-react";
import type { OptionsStatus } from "@/types/options";
import { API_URL, cn } from "@/lib/utils";
import { ageSeconds, fmtAge, fmtDate, fmtNum, PHASE_LABELS } from "@/lib/optionsFormat";

function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className={cn(
      "flex items-center gap-2 text-xs px-3 py-2 rounded-lg border whitespace-nowrap",
      tone === "good" && "border-[#22c55e33] bg-[#22c55e0b]",
      tone === "warn" && "border-[#f59e0b33] bg-[#f59e0b0b]",
      tone === "bad" && "border-[#ef444433] bg-[#ef44440b]",
      tone === "neutral" && "border-[#1e2d45] bg-card",
    )}>{children}</div>
  );
}

export function SessionBar({ status }: { status: OptionsStatus | undefined }) {
  if (!status) {
    return <div className="flex gap-2 flex-wrap">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-9 w-44 rounded-lg" />)}</div>;
  }
  const open = ["opening", "main", "late", "closing"].includes(status.session_phase);
  const dataAge = ageSeconds(status.last_bar_at);
  const fresh = dataAge != null && dataAge < 180;

  return (
    <div className="flex gap-2 flex-wrap">
      <Chip tone={open ? "good" : "neutral"}>
        <span className={cn("w-2 h-2 rounded-full", open ? "bg-green animate-pulse" : "bg-[#475569]")} />
        <span className={open ? "text-green font-medium" : "text-[#94a3b8]"}>{PHASE_LABELS[status.session_phase] ?? status.session_phase}</span>
        {!status.trading_day && <span className="text-[#64748b]">· next session {fmtDate(status.next_trading_day)}</span>}
      </Chip>

      {status.kite_connected_today ? (
        <Chip tone="good"><Wifi size={13} className="text-green" /><span className="text-green font-medium">Kite connected</span></Chip>
      ) : status.kite_configured ? (
        <a href={`${API_URL}/kite/login`} className="group">
          <Chip tone={status.trading_day ? "warn" : "neutral"}>
            <WifiOff size={13} className="text-yellow" />
            <span className="text-yellow font-medium">Kite not logged in today</span>
            <span className="flex items-center gap-1 text-[#ff9933] group-hover:underline"><LogIn size={12} /> Log in</span>
          </Chip>
        </a>
      ) : (
        <Chip tone="bad"><WifiOff size={13} className="text-red" /><span className="text-red font-medium">Kite API keys not set</span></Chip>
      )}

      <Chip tone={fresh ? "good" : open ? "warn" : "neutral"}>
        <Activity size={13} className={fresh ? "text-green" : "text-[#64748b]"} />
        <span className="text-[#94a3b8]">Market data</span>
        <span className="font-mono text-[#e2e8f0]">{fmtAge(dataAge)}</span>
        <span className="text-[#475569]">· {fmtNum(status.bars_today)} bars today</span>
      </Chip>

      <Chip tone={status.telegram_configured ? "neutral" : "warn"}>
        <Send size={13} className={status.telegram_configured ? "text-[#60a5fa]" : "text-yellow"} />
        <span className={status.telegram_configured ? "text-[#94a3b8]" : "text-yellow"}>
          {status.telegram_configured ? "Telegram alerts on" : "Telegram not set up"}
        </span>
      </Chip>

      <Chip>
        <Shield size={13} className="text-[#ff9933]" />
        <span className="text-[#94a3b8]">Risk</span>
        <span className="font-mono text-[#e2e8f0]">{status.risk.risk_per_trade_pct}%/trade</span>
        <span className="text-[#475569]">·</span>
        <span className="font-mono text-[#e2e8f0]">{status.risk.daily_loss_stop_pct}% daily stop</span>
        <span className="text-[#475569]">· ₹{fmtNum(status.risk.capital)}</span>
      </Chip>

      <Chip>
        <Clock size={13} className="text-[#64748b]" />
        <span className="text-[#94a3b8]">Signals on 5-min closes · 09:30–15:00</span>
      </Chip>
    </div>
  );
}
