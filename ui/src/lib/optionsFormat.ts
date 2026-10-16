// Formatting helpers for the options dashboard. All times are shown in IST, whatever the viewer's timezone.

const IST = "Asia/Kolkata";

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", { timeZone: IST, hour: "2-digit", minute: "2-digit", hour12: false })
    .format(new Date(iso));
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: IST, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(iso));
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.length === 10 ? new Date(`${iso}T12:00:00+05:30`) : new Date(iso);
  return new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short", weekday: "short" }).format(d);
}

export function istDateKey(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST }).format(new Date(iso));   // YYYY-MM-DD
}

export function todayIST(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST }).format(new Date());
}

export function ageSeconds(iso: string | null | undefined, nowMs = Date.now()): number | null {
  if (!iso) return null;
  return Math.max(0, Math.round((nowMs - new Date(iso).getTime()) / 1000));
}

export function fmtAge(seconds: number | null): string {
  if (seconds == null) return "never";
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function fmtNum(v: number | null | undefined, decimals = 0): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function fmtPremium(v: number | null | undefined): string {
  return fmtNum(v, 2);
}

export function fmtRupees(v: number | null | undefined, signed = false): string {
  if (v == null) return "—";
  const s = Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  if (!signed) return `₹${s}`;
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}₹${s}`;
}

export function fmtR(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}R`;
}

export function fmtPct(v: number | null | undefined, decimals = 0): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(decimals)}%`;
}

export const PILLAR_LABELS: Record<string, string> = {
  trend: "Trend", trigger: "Trigger", levels: "Levels & room", momentum: "Momentum",
  futures_flow: "Futures flow", option_chain: "Option chain", volatility: "Volatility",
  option_quality: "Option quality", breadth: "Breadth", macro: "Global & macro",
  events: "Events", news: "News", timing: "Timing",
};

export const PHASE_LABELS: Record<string, string> = {
  pre_market: "Pre-market", opening: "Opening range", main: "Main session",
  late: "Late session", closing: "Closing", closed: "Market closed",
};

export const EXIT_LABELS: Record<string, string> = {
  T2_HIT: "Target 2 hit", SL_HIT: "Stop-loss hit", TRAIL_STOP: "Trailing stop", INVALIDATED: "Invalidated",
  TIME_STOP: "Time stop", SQUARE_OFF: "Square-off 15:15", EXIT_SIGNAL: "Opposite signal", EVENT_EXIT: "Event exit",
  EXPIRED: "Entry not reached", CANCELLED: "Cancelled before entry", KILL: "Kill switch",
};
