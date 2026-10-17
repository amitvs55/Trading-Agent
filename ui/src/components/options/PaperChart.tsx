"use client";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PaperAccount } from "@/types/options";
import { fmtDateTime, fmtRupees } from "@/lib/optionsFormat";

// Same validated palette as the track record charts (blue on the #1a2233 card)
const LINE = "#3987e5";
const GRID = "#1e2d45";
const AXIS = "#8391a7";

export function PaperCurve({ curve, start }: { curve: PaperAccount["curve"]; start: number }) {
  const points = curve.map((p, i) => ({ ...p, n: i }));
  const last = points[points.length - 1]?.balance ?? start;
  return (
    <div className="h-64" role="img" aria-label={`Paper balance after ${points.length - 1} trades: ${fmtRupees(last)}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="paperFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={LINE} stopOpacity={0.25} />
              <stop offset="100%" stopColor={LINE} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="n" tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} allowDecimals={false} />
          <YAxis tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={false} width={70} domain={["auto", "auto"]}
                 tickFormatter={(v: number) => fmtRupees(v)} />
          <ReferenceLine y={start} stroke="#334155" strokeDasharray="3 3" />
          <Tooltip contentStyle={{ background: "#1a2233", border: "1px solid #1e2d45", borderRadius: 8, fontSize: 11, padding: "8px 10px" }}
                   labelStyle={{ color: "#e2e8f0", marginBottom: 4 }} itemStyle={{ color: "#e2e8f0" }}
                   cursor={{ stroke: "#475569", strokeWidth: 1 }}
                   labelFormatter={(n: number) => (n === 0 ? `Start · ${fmtDateTime(points[0]?.t)}` : `Trade ${n} · ${points[n]?.id ?? ""} · ${fmtDateTime(points[n]?.t)}`)}
                   formatter={(v: number) => [fmtRupees(v), "Balance"]} />
          <Area type="linear" dataKey="balance" stroke={LINE} strokeWidth={2} fill="url(#paperFill)" isAnimationActive={false}
                dot={points.length <= 40 ? { r: 3, fill: LINE, stroke: "#1a2233", strokeWidth: 2 } : false}
                activeDot={{ r: 5, fill: LINE, stroke: "#1a2233", strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
