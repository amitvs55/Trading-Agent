"use client";
import { useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, CalendarDays, CheckCircle2, Plus, Trash2 } from "lucide-react";
import type { CalendarResponse, MarketEvent } from "@/types/auth";
import { cn } from "@/lib/utils";
import { sendJson } from "@/lib/optionsApi";
import { useNow } from "@/lib/clock";
import { Note, Panel } from "@/components/connectors/SideCards";

type NoteT = { tone: "ok" | "err"; text: string } | null;

// "Thu 15 Jan 2026" and "Wed 28 Oct 2026, 23:30": built from parts, since locales punctuate dates differently
const PARTS = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Kolkata" });

function fmt(d: Date, withTime: boolean): string {
  const p = Object.fromEntries(PARTS.formatToParts(d).map(x => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month} ${p.year}` + (withTime ? `, ${p.hour}:${p.minute}` : "");
}

const input = "bg-card border border-[#1e2d45] rounded-lg px-3 py-2 text-base lg:text-sm text-[#e2e8f0] placeholder:text-[#8391a7] outline-none focus-visible:border-[#ff9933] focus-visible:ring-2 focus-visible:ring-[#ff993355]";
const addBtn = "inline-flex items-center justify-center gap-1.5 h-10 rounded-lg px-3 text-sm font-semibold bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]";

function RemoveButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
            className="grid place-items-center w-9 h-9 rounded-lg text-[#94a3b8] hover:text-[#fca5a5] hover:bg-[#ef44440d] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]">
      <Trash2 size={14} />
    </button>
  );
}

/** NSE holidays and market-moving events: both change every year, so they're edited here, not in code. */
export function CalendarPanel({ data, onChange }: { data: CalendarResponse | undefined; onChange: (c: CalendarResponse) => void }) {
  const thisYear = Number(new Date().toLocaleString("en-CA", { timeZone: "Asia/Kolkata", year: "numeric" }));
  const [year, setYear] = useState(thisYear);
  const [day, setDay] = useState("");
  const [name, setName] = useState("");
  const [evName, setEvName] = useState("");
  const [evAt, setEvAt] = useState("");
  const [evImpact, setEvImpact] = useState<"high" | "medium">("high");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<NoteT>(null);

  const holidays = useMemo(() => (data?.holidays ?? []).filter(h => h.date.startsWith(String(year))), [data, year]);
  const yearInfo = data?.years.find(y => y.year === year);
  const hour = useNow(3_600_000);
  const events = useMemo(() => {
    const since = hour - 86_400_000;
    return (data?.events ?? []).filter(e => !hour || new Date(e.at).getTime() > since);
  }, [data, hour]);

  const call = async (key: string, fn: () => Promise<CalendarResponse>, ok: string) => {
    setBusy(key);
    setNote(null);
    try {
      onChange(await fn());
      setNote({ tone: "ok", text: ok });
      return true;
    } catch (e) {
      setNote({ tone: "err", text: e instanceof Error ? e.message : "Couldn't save it" });
      return false;
    } finally {
      setBusy(null);
    }
  };

  const addHoliday = async (e: FormEvent) => {
    e.preventDefault();
    if (await call("holiday", () => sendJson("/api/admin/calendar/holidays", "POST", { date: day, name }),
      "Holiday added. The recorder skips that day and expiries shift around it.")) {
      setYear(Number(day.slice(0, 4)));
      setDay(""); setName("");
    }
  };

  const addEvent = async (e: FormEvent) => {
    e.preventDefault();
    const at = `${evAt}:00+05:30`;               // the input is IST wall-clock time
    if (await call("event", () => sendJson("/api/admin/calendar/events", "POST", { name: evName, at, impact: evImpact }),
      "Event added. No new intraday entries from 30 minutes before it to 15 minutes after; no positional entries in the two days before a high-impact one.")) {
      setEvName(""); setEvAt("");
    }
  };

  return (
    <Panel icon={<CalendarDays size={14} className="text-[#ff9933]" />} title="Trading calendar"
           subtitle="NSE publishes next year's holidays in December, and the RBI its policy dates once a year. Add them here; the recorder reads them at each session start.">
      {data?.warning && (
        <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-[#f59e0b44] bg-[#f59e0b0f] px-3 py-2.5 text-[12px] text-yellow">
          <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" aria-hidden /> {data.warning}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3" role="tablist" aria-label="Holiday year">
        {(data?.years ?? []).map(y => (
          <button key={y.year} type="button" role="tab" aria-selected={y.year === year} onClick={() => setYear(y.year)}
                  className={cn("inline-flex items-center gap-1.5 h-9 rounded-lg px-3 text-[12px] font-semibold border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]",
                    y.year === year ? "border-[#ff993366] bg-[#ff993314] text-[#e2e8f0]" : "border-[#1e2d45] bg-card text-[#94a3b8] hover:text-[#e2e8f0]")}>
            {y.year}
            {y.complete ? <CheckCircle2 size={12} className="text-green" aria-label="complete" />
                        : <AlertTriangle size={12} className="text-yellow" aria-label="incomplete" />}
          </button>
        ))}
      </div>

      <div className="rounded-lg border border-[#1e2d45] bg-card">
        <div className="flex items-center justify-between gap-3 px-3 py-2 border-b border-[#1e2d45]">
          <span className="text-[12px] text-[#94a3b8]">
            {holidays.length} weekday holiday{holidays.length === 1 ? "" : "s"} in {year}
            {yearInfo?.built_in ? " · built in" : ""}
          </span>
          {yearInfo && !yearInfo.built_in && (
            <label className="inline-flex items-center gap-2 text-[12px] text-[#e2e8f0] cursor-pointer">
              <input type="checkbox" checked={yearInfo.complete} disabled={busy !== null}
                     onChange={e => call("year", () => sendJson(`/api/admin/calendar/years/${year}`, "PUT", { complete: e.target.checked }),
                       e.target.checked ? `${year} marked complete: the missing-list warning stops.` : `${year} marked incomplete.`)}
                     className="w-4 h-4 accent-[#ff9933]" />
              Full list entered
            </label>
          )}
        </div>
        {!data ? <div className="h-64 p-3" aria-hidden><div className="skeleton h-full rounded-md" /></div>
        : holidays.length === 0 ? (
          <p className="h-64 grid place-items-center px-3 text-center text-[12px] text-[#94a3b8]">No holidays entered for {year}.</p>
        ) : (
          <ul tabIndex={0} aria-label={`Holidays in ${year}`} className="divide-y divide-[#1e2d45] h-64 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] rounded-md">
            {holidays.map(h => (
              <li key={h.date} className="flex items-center justify-between gap-3 px-3 py-1.5 min-h-[44px]">
                <span className="text-[12px] text-[#e2e8f0] font-mono">{fmt(new Date(`${h.date}T12:00:00+05:30`), false)}</span>
                <span className="flex-1 min-w-0 truncate text-[12px] text-[#94a3b8]">{h.name ?? ""}</span>
                {h.source === "added"
                  ? <RemoveButton label={`Remove ${h.date}`} disabled={busy !== null}
                                  onClick={() => call("rm", () => sendJson(`/api/admin/calendar/holidays/${h.date}`, "DELETE", {}), "Holiday removed.")} />
                  : <span className="text-[10px] uppercase tracking-wider text-[#94a3b8] px-1.5">built in</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <form onSubmit={addHoliday} className="mt-3 grid grid-cols-1 sm:grid-cols-[150px_minmax(0,1fr)_auto] gap-2 items-end">
        <div>
          <label htmlFor="hol-date" className="text-[11px] font-medium text-[#94a3b8]">Holiday date</label>
          <input id="hol-date" type="date" required value={day} onChange={e => setDay(e.target.value)} className={cn(input, "mt-1 w-full")} />
        </div>
        <div>
          <label htmlFor="hol-name" className="text-[11px] font-medium text-[#94a3b8]">Name</label>
          <input id="hol-name" required maxLength={80} value={name} onChange={e => setName(e.target.value)} placeholder="Republic Day" className={cn(input, "mt-1 w-full")} />
        </div>
        <button type="submit" disabled={busy !== null || !day || !name} className={addBtn}><Plus size={14} /> Add</button>
      </form>

      <div className="mt-6 pt-4 border-t border-[#1e2d45]">
        <div className="text-[12px] font-semibold text-[#e2e8f0] mb-2">Upcoming events</div>
        {!data ? <div className="skeleton h-[240px] rounded-lg" aria-hidden />
          : events.length === 0 ? <p className="text-[12px] text-[#94a3b8]">No events ahead.</p> : (
          <ul className="divide-y divide-[#1e2d45] rounded-lg border border-[#1e2d45] bg-card">
            {events.map((e: MarketEvent) => (
              <li key={`${e.source}-${e.id ?? e.at}-${e.name}`} className="flex items-center gap-3 px-3 py-1.5 min-h-[44px]">
                <span className={cn("text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border flex-shrink-0",
                  e.impact === "high" ? "text-[#fca5a5] border-[#ef444433]" : "text-yellow border-[#f59e0b33]")}>{e.impact}</span>
                <span className="flex-1 min-w-0">
                  <span className="block text-[12px] text-[#e2e8f0] truncate">{e.name}</span>
                  <span className="block text-[11px] text-[#94a3b8] font-mono">{fmt(new Date(e.at), true)} IST</span>
                </span>
                {e.source === "added" && e.id
                  ? <RemoveButton label={`Remove ${e.name}`} disabled={busy !== null}
                                  onClick={() => call("rm", () => sendJson(`/api/admin/calendar/events/${e.id}`, "DELETE", {}), "Event removed.")} />
                  : <span className="text-[10px] uppercase tracking-wider text-[#94a3b8] px-1.5">built in</span>}
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={addEvent} className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          <div className="sm:col-span-2">
            <label htmlFor="ev-name" className="text-[11px] font-medium text-[#94a3b8]">Event</label>
            <input id="ev-name" required maxLength={80} value={evName} onChange={e => setEvName(e.target.value)}
                   placeholder="RBI MPC decision" className={cn(input, "mt-1 w-full")} />
          </div>
          <div>
            <label htmlFor="ev-at" className="text-[11px] font-medium text-[#94a3b8]">Date and time (IST)</label>
            <input id="ev-at" type="datetime-local" required value={evAt} onChange={e => setEvAt(e.target.value)} className={cn(input, "mt-1 w-full")} />
          </div>
          <div>
            <label htmlFor="ev-impact" className="text-[11px] font-medium text-[#94a3b8]">Impact</label>
            <select id="ev-impact" value={evImpact} onChange={e => setEvImpact(e.target.value as "high" | "medium")} className={cn(input, "mt-1 w-full")}>
              <option value="high">High: also blocks positional entries</option>
              <option value="medium">Medium: intraday window only</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <button type="submit" disabled={busy !== null || !evName || !evAt} className={addBtn}><Plus size={14} /> Add event</button>
          </div>
        </form>
      </div>
      <Note note={note} />
    </Panel>
  );
}
