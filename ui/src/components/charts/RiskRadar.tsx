"use client";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import type { RiskAssessment } from "@/types/pipeline";

interface Props { assessments: RiskAssessment[]; }

export function RiskRadar({ assessments }: Props) {
  if (!assessments.length) return null;

  const agg  = assessments.find(a => a.profile === "aggressive");
  const neut = assessments.find(a => a.profile === "neutral");
  const cons = assessments.find(a => a.profile === "conservative");

  const data = [
    { subject: "Risk Score",    Aggressive: agg?.risk_score ?? 0,            Neutral: neut?.risk_score ?? 0,            Conservative: cons?.risk_score ?? 0 },
    { subject: "Max Position",  Aggressive: agg?.max_position_size_pct ?? 0, Neutral: neut?.max_position_size_pct ?? 0, Conservative: cons?.max_position_size_pct ?? 0 },
    { subject: "Approve",       Aggressive: agg?.approve ? 10 : 0,           Neutral: neut?.approve ? 10 : 0,           Conservative: cons?.approve ? 10 : 0 },
    { subject: "Concerns",      Aggressive: Math.min(10, (agg?.concerns.length ?? 0) * 2),  Neutral: Math.min(10, (neut?.concerns.length ?? 0) * 2), Conservative: Math.min(10, (cons?.concerns.length ?? 0) * 2) },
  ];

  return (
    <ResponsiveContainer width="100%" height={160}>
      <RadarChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: 16 }}>
        <PolarGrid stroke="#1e2d45" />
        <PolarAngleAxis dataKey="subject" tick={{ fill: "#8391a7", fontSize: 9 }} />
        <Radar name="Aggressive"   dataKey="Aggressive"   stroke="#ef4444" fill="#ef4444" fillOpacity={0.08} strokeWidth={1.5} />
        <Radar name="Neutral"      dataKey="Neutral"      stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.08} strokeWidth={1.5} />
        <Radar name="Conservative" dataKey="Conservative" stroke="#22c55e" fill="#22c55e" fillOpacity={0.08} strokeWidth={1.5} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
