"use client";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Performance } from "@/types/options";
import { fmtDateTime, fmtRupees } from "@/lib/optionsFormat";

// Validated (dataviz validator, dark, on the #1a2233 card): blue ↔ red diverging poles, gray midpoint.
const GAIN = "#3987e5";
const LOSS = "#e66767";
const NEUTRAL = "#475569";
const GRID = "#1e2d45";
const AXIS = "#64748b";

const tooltipStyle = {
  contentStyle: { background: "#1a2233", border: "1px solid #1e2d45", borderRadius: 8, fontSize: 11, padding: "8px 10px" },
  labelStyle: { color: "#e2e8f0", marginBottom: 4 },
  itemStyle: { color: "#e2e8f0" },
};

export function EquityChart({ data }: { data: Performance["equity"] }) {
  const points = [{ t: "", equity: 0, pnl: 0, id: "start", mode: "" }, ...data].map((d, i) => ({ ...d, n: i }));
  const last = points[points.length - 1]?.equity ?? 0;
  return (
    <div className="h-72" aria-label={`Cumulative P&L after ${data.length} trades: ${fmtRupees(last, true)}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 10, right: 12, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={GAIN} stopOpacity={0.25} />
              <stop offset="100%" stopColor={GAIN} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="n" tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }}
                 label={{ value: "trade #", position: "insideBottomRight", offset: -2, fill: AXIS, fontSize: 10 }} />
          <YAxis tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={false} width={64}
                 tickFormatter={(v: number) => fmtRupees(v, true)} />
          <ReferenceLine y={0} stroke="#334155" />
          <Tooltip {...tooltipStyle} cursor={{ stroke: "#475569", strokeWidth: 1 }}
                   labelFormatter={(n: number) => (n === 0 ? "Start" : `Trade #${n} · ${points[n]?.id} · ${fmtDateTime(points[n]?.t)}`)}
                   formatter={(v: number, _name, item) => [`${fmtRupees(v, true)} (this trade ${fmtRupees(item.payload.pnl, true)})`, "Cumulative"]} />
          <Area type="linear" dataKey="equity" stroke={GAIN} strokeWidth={2} fill="url(#eqFill)"
                dot={points.length <= 40 ? { r: 3, fill: GAIN, stroke: "#1a2233", strokeWidth: 2 } : false}
                activeDot={{ r: 5, fill: GAIN, stroke: "#1a2233", strokeWidth: 2 }} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

const BINS = [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3];

export function RDistribution({ values }: { values: number[] }) {
  const bins = BINS.slice(0, -1).map((lo, i) => {
    const hi = BINS[i + 1];
    const last = i === BINS.length - 2;
    const first = i === 0;
    const count = values.filter(v => (first ? v < hi : last ? v >= lo : v >= lo && v < hi)).length;
    const sign = (x: number) => (x > 0 ? `+${x}` : x < 0 ? `−${Math.abs(x)}` : "0");
    const label = first ? `<${sign(hi)}` : last ? `≥${sign(lo)}` : sign(lo);
    const range = first ? `below ${sign(hi)}R` : last ? `${sign(lo)}R and above` : `${sign(lo)}R to ${sign(hi)}R`;
    return { label, range, count, mid: (lo + hi) / 2 };
  });
  return (
    <div className="h-60" aria-label="Distribution of trade results in R multiples">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bins} margin={{ top: 16, right: 8, left: 0, bottom: 8 }} barCategoryGap={2}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0}
                 label={{ value: "R multiple", position: "insideBottomRight", offset: -2, fill: AXIS, fontSize: 10 }} />
          <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 10 }} tickLine={false} axisLine={false} width={28} />
          <Tooltip {...tooltipStyle} cursor={{ fill: "#ffffff08" }}
                   labelFormatter={(_l: string, items) => items?.[0]?.payload?.range ?? ""}
                   formatter={(v: number) => [`${v} trade${v === 1 ? "" : "s"}`, "Count"]} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false}
               label={{ position: "top", fill: "#94a3b8", fontSize: 10, formatter: (v: number) => (v ? v : "") }}>
            {bins.map(b => <Cell key={b.label} fill={b.mid > 0 ? GAIN : b.mid < 0 ? LOSS : NEUTRAL} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
