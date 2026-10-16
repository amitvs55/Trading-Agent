import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Empty → relative /api/* calls go through the next.config rewrite proxy (local/docker-compose).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a number as Indian Rupees with ₹ symbol */
export function formatINR(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "—";
  return "₹" + value.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Format large INR values (Cr / L) */
export function formatINRShort(value: number | null | undefined): string {
  if (value == null) return "—";
  if (Math.abs(value) >= 1e12) return `₹${(value / 1e12).toFixed(2)}L Cr`;
  if (Math.abs(value) >= 1e7)  return `₹${(value / 1e7).toFixed(2)} Cr`;
  if (Math.abs(value) >= 1e5)  return `₹${(value / 1e5).toFixed(2)} L`;
  return formatINR(value, 0);
}

/** Format percentage */
export function formatPct(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "—";
  const sign = value >= 0 ? "+" : "";
  return sign + value.toFixed(decimals) + "%";
}

/** Format volume in Indian units */
export function formatVolume(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e7) return (value / 1e7).toFixed(2) + " Cr";
  if (value >= 1e5) return (value / 1e5).toFixed(2) + " L";
  return value.toLocaleString("en-IN");
}

/** USD→INR rate used for the secondary rupee figure next to LLM costs */
export const USD_INR = Number(process.env.NEXT_PUBLIC_USD_INR) || 84;

/** Format an LLM cost in dollars: 4 decimals under $1, 2 above */
export function formatUSD(value: number | null | undefined): string {
  if (value == null) return "—";
  return "$" + value.toFixed(Math.abs(value) < 1 ? 4 : 2);
}

/** Format token counts compactly: 950, 12.4K, 1.20M */
export function formatTokens(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1e6) return (value / 1e6).toFixed(2) + "M";
  if (value >= 1e4) return (value / 1e3).toFixed(1) + "K";
  return value.toLocaleString("en-US");
}

/** Format seconds as "1m 23s" */
export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/** Color class for change values */
export function changeColor(v: number | null | undefined): string {
  if (v == null) return "text-[#94a3b8]";
  return v >= 0 ? "text-green" : "text-red";
}

/** Impact color */
export function impactColor(impact: string): string {
  const map: Record<string, string> = {
    very_positive: "text-green",
    positive:      "text-[#86efac]",
    neutral:       "text-[#94a3b8]",
    negative:      "text-[#fca5a5]",
    very_negative: "text-red",
  };
  return map[impact] ?? "text-[#94a3b8]";
}

/** NSE/BSE yfinance suffix */
export function toYFTicker(symbol: string, exchange: string): string {
  const s = symbol.toUpperCase();
  if (s.includes(".")) return s;
  return s + (exchange === "BSE" ? ".BO" : ".NS");
}
