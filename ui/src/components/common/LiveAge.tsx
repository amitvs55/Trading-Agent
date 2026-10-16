"use client";
import { useNow } from "@/lib/clock";
import { ageSeconds, fmtAge } from "@/lib/optionsFormat";

/** "updated 12s ago" that keeps counting on its own; only this text re-renders. */
export function LiveAge({ iso, prefix = "", never = "never" }: { iso: string | null | undefined; prefix?: string; never?: string }) {
  const recent = iso ? Date.now() - new Date(iso).getTime() < 120_000 : false;
  const now = useNow(recent ? 1000 : 15_000);               // seconds matter only while it's fresh
  if (!iso) return <>{never}</>;
  const age = now ? ageSeconds(iso, now) : null;
  return <span suppressHydrationWarning>{prefix}{age == null ? "…" : fmtAge(age)}</span>;
}
