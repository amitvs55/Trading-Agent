"use client";
import { useNow } from "@/lib/clock";
import { ageSeconds, fmtAge } from "@/lib/optionsFormat";

/** "updated 12s ago" that keeps counting on its own; only this text re-renders. */
export function LiveAge({ iso, prefix = "", never = "never" }: { iso: string | null | undefined; prefix?: string; never?: string }) {
  // Seconds matter only while it's fresh: a coarse 15 s reading picks the pace (no clock read during render)
  const coarse = useNow(15_000);
  const recent = !!iso && (!coarse || coarse - new Date(iso).getTime() < 135_000);
  const now = useNow(recent ? 1000 : 15_000);
  if (!iso) return <>{never}</>;
  const age = now ? ageSeconds(iso, now) : null;
  return <span suppressHydrationWarning>{prefix}{age == null ? "…" : fmtAge(age)}</span>;
}
