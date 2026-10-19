"use client";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CheckReport } from "@/types/check";
import { fmtNum, fmtRupees } from "@/lib/optionsFormat";

// Validated pair on the dark surface (dataviz palette check passes): blue = at your exit, orange (dashed) = at expiry.
// The reference lines stay neutral and carry their own labels, so no colour means two things.
const EXIT = "#3987e5";
const EXPIRY = "#d95926";
const GRID = "#1e2d45";
const AXIS = "#8391a7";

/** ₹ P&L across NIFTY levels: at your exit (and at expiry, if you exit earlier), with the market's ±1σ range. */
export function PayoffChart({ report }: { report: CheckReport }) {
  const curve = report.curve!;
  const settles = report.horizon!.settles;
  const be = report.position!.breakeven;
  const lo = curve.points[0].x, hi = curve.points[curve.points.length - 1].x;
  const label = `Profit or loss across NIFTY levels from ${fmtNum(lo)} to ${fmtNum(hi)}; breakeven at expiry ${fmtNum(be)}.`;
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl p-5" aria-label="Payoff chart">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[#e2e8f0]">Profit or loss by where NIFTY ends up</h3>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[#94a3b8]">
          <li className="flex items-center gap-1.5 whitespace-nowrap"><span className="w-4 h-[2px]" style={{ background: EXIT }} aria-hidden />
            {settles ? "at expiry" : "at your exit"}</li>
          {!settles && <li className="flex items-center gap-1.5 whitespace-nowrap"><span className="w-4 h-0 border-t-2 border-dashed" style={{ borderColor: EXPIRY }} aria-hidden />
            at expiry</li>}
          <li className="flex items-center gap-1.5 whitespace-nowrap"><span className="w-3 h-3 rounded-sm bg-[#3987e51f] border border-[#3987e533]" aria-hidden />
            ±1σ range</li>
        </ul>
      </div>
      <p className="text-[11px] text-[#8391a7] mt-1">
        {settles ? "At expiry" : `Exit ${report.horizon!.label}`} · the shaded band is where the options market expects NIFTY two times in three
      </p>
      <div className="h-72 mt-3" role="img" aria-label={label}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curve.points} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <ReferenceArea x1={curve.spot - curve.sd} x2={curve.spot + curve.sd} fill="#3987e5" fillOpacity={0.08} stroke="none" />
            <XAxis dataKey="x" type="number" domain={[lo, hi]} tick={{ fill: AXIS, fontSize: 10 }} tickLine={false}
                   axisLine={{ stroke: GRID }} tickFormatter={(v: number) => fmtNum(v)} tickCount={7} />
            <YAxis tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={false} width={72}
                   tickFormatter={(v: number) => fmtRupees(v, true)} />
            <ReferenceLine y={0} stroke="#475569" />
            <ReferenceLine x={curve.spot} stroke="#94a3b8" strokeDasharray="3 3"
                           label={{ value: "now", fill: "#cbd5e1", fontSize: 10, position: "insideTopLeft" }} />
            {be >= lo && be <= hi && (
              <ReferenceLine x={be} stroke="#e2e8f0" strokeDasharray="1 4"
                             label={{ value: "breakeven", fill: "#e2e8f0", fontSize: 10, position: "insideTopRight" }} />
            )}
            <Tooltip contentStyle={{ background: "#1a2233", border: "1px solid #1e2d45", borderRadius: 8, fontSize: 11, padding: "8px 10px" }}
                     labelStyle={{ color: "#e2e8f0", marginBottom: 4 }} itemStyle={{ color: "#e2e8f0" }}
                     cursor={{ stroke: "#475569", strokeWidth: 1 }}
                     labelFormatter={(x: number) => `NIFTY ${fmtNum(x)} (${((x / curve.spot - 1) * 100).toFixed(2)}%)`}
                     formatter={(v: number, name: string) => [fmtRupees(v, true), name === "exit" ? (settles ? "At expiry" : "At your exit") : "At expiry"]} />
            <Line type="monotone" dataKey="exit" stroke={EXIT} strokeWidth={2} dot={false} isAnimationActive={false}
                  activeDot={{ r: 4, fill: EXIT, stroke: "#1a2233", strokeWidth: 2 }} />
            {!settles && <Line type="linear" dataKey="expiry" stroke={EXPIRY} strokeWidth={2} strokeDasharray="5 4" dot={false}
                               isAnimationActive={false} activeDot={{ r: 4, fill: EXPIRY, stroke: "#1a2233", strokeWidth: 2 }} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
