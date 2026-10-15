"use client";
import { PieChart, Pie, Cell } from "recharts";

interface Props { score: number; } // -1 to +1

export function SentimentGauge({ score }: Props) {
  const pct   = (score + 1) / 2;           // 0–1
  const angle = pct * 180;                  // 0° = full left, 180° = full right
  const color = score >= 0.2 ? "#22c55e" : score <= -0.2 ? "#ef4444" : "#f59e0b";

  // Semicircle data: filled vs remaining
  const data = [
    { value: pct * 100 },
    { value: (1 - pct) * 100 },
  ];

  // Needle SVG (rotates from -90° to +90° based on angle)
  const needleDeg = angle - 90; // -90 = leftmost, +90 = rightmost

  return (
    <div className="relative flex items-center justify-center" style={{ height: 100 }}>
      <PieChart width={160} height={90}>
        {/* Background arc */}
        <Pie data={[{ value: 100 }]} dataKey="value" cx={80} cy={80}
          innerRadius={50} outerRadius={70} startAngle={180} endAngle={0} strokeWidth={0}>
          <Cell fill="#1e2d45" />
        </Pie>
        {/* Filled arc */}
        <Pie data={data} dataKey="value" cx={80} cy={80}
          innerRadius={50} outerRadius={70} startAngle={180} endAngle={0} strokeWidth={0}>
          <Cell fill={color} />
          <Cell fill="transparent" />
        </Pie>
      </PieChart>

      {/* Needle */}
      <div className="absolute" style={{ bottom: 10, left: "50%", transform: "translateX(-50%)" }}>
        <svg width="160" height="80" viewBox="0 0 160 80" style={{ overflow: "visible" }}>
          <g transform={`translate(80,80) rotate(${needleDeg})`}>
            <line x1="0" y1="0" x2="0" y2="-55" stroke="#e2e8f0" strokeWidth="2" strokeLinecap="round" opacity="0.9" />
          </g>
          <circle cx="80" cy="80" r="5" fill="#1a2233" stroke={color} strokeWidth="2" />
          {/* Labels */}
          <text x="4"   y="78" fill="#ef4444" fontSize="8">Bear</text>
          <text x="125" y="78" fill="#22c55e" fontSize="8">Bull</text>
          {/* Score */}
          <text x="80" y="68" textAnchor="middle" fill={color} fontSize="13" fontWeight="bold" fontFamily="monospace">
            {score >= 0 ? "+" : ""}{score.toFixed(2)}
          </text>
        </svg>
      </div>
    </div>
  );
}
