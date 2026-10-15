"use client";
import { useEffect, useState } from "react";
import {
  ComposedChart, Line, Area, ReferenceLine,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import type { TradeProposal } from "@/types/pipeline";
import type { Candle } from "@/types/pipeline";
import { formatINR, API_URL } from "@/lib/utils";

interface Props {
  ticker:   string;
  proposal?: TradeProposal | null;
}

export function TechnicalChart({ ticker, proposal }: Props) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    fetch(`${API_URL}/api/pricehistory/${encodeURIComponent(ticker)}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.candles) setCandles(d.candles); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [ticker]);

  // Compute SMA
  function sma(data: Candle[], period: number): (number | null)[] {
    return data.map((_, i) => {
      if (i < period - 1) return null;
      const slice = data.slice(i - period + 1, i + 1);
      return slice.reduce((s, c) => s + c.close, 0) / period;
    });
  }

  const sma20 = sma(candles, 20);
  const sma50 = sma(candles, 50);

  const chartData = candles.map((c, i) => ({
    date:  c.date.slice(5), // MM-DD
    close: c.close,
    sma20: sma20[i],
    sma50: sma50[i],
  }));

  if (loading) {
    return (
      <div className="h-48 flex items-center justify-center">
        <div className="w-5 h-5 rounded-full border-2 border-[#1e2d45] border-t-[#ff9933] animate-spin" />
      </div>
    );
  }

  if (!candles.length) {
    return <div className="h-48 flex items-center justify-center text-xs text-[#64748b]">No price data</div>;
  }

  const prices = candles.map(c => c.close);
  const yMin   = Math.min(...prices) * 0.995;
  const yMax   = Math.max(...prices) * 1.005;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1e2d45" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: "#475569", fontSize: 9, fontFamily: "monospace" }}
          tickLine={false}
          axisLine={false}
          interval={Math.floor(chartData.length / 4)}
        />
        <YAxis
          domain={[yMin, yMax]}
          tick={{ fill: "#475569", fontSize: 9, fontFamily: "monospace" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={v => `₹${(v/1000).toFixed(0)}k`}
          width={42}
        />
        <Tooltip
          contentStyle={{ background: "#1a2233", border: "1px solid #1e2d45", borderRadius: 8, fontSize: 11 }}
          labelStyle={{ color: "#64748b" }}
          formatter={(val: number, name: string) => [formatINR(val), name === "close" ? "Price" : name === "sma20" ? "SMA20" : "SMA50"]}
        />
        {/* Price area */}
        <Area dataKey="close" fill="#ff9933" fillOpacity={0.08} stroke="#ff9933" strokeWidth={2} dot={false} />
        {/* SMAs */}
        <Line dataKey="sma20" stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="5 3" dot={false} connectNulls />
        <Line dataKey="sma50" stroke="#f97316" strokeWidth={1.5} strokeDasharray="5 3" dot={false} connectNulls />
        {/* Trade levels */}
        {proposal?.entry_price && (
          <ReferenceLine y={proposal.entry_price} stroke="#ff9933" strokeDasharray="4 4" strokeWidth={1}
            label={{ value: `Entry ₹${proposal.entry_price.toFixed(0)}`, fill: "#ff9933", fontSize: 9, position: "insideTopLeft" }} />
        )}
        {proposal?.take_profit && (
          <ReferenceLine y={proposal.take_profit} stroke="#22c55e" strokeDasharray="4 4" strokeWidth={1}
            label={{ value: `TP ₹${proposal.take_profit.toFixed(0)}`, fill: "#22c55e", fontSize: 9, position: "insideTopLeft" }} />
        )}
        {proposal?.stop_loss && (
          <ReferenceLine y={proposal.stop_loss} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1}
            label={{ value: `SL ₹${proposal.stop_loss.toFixed(0)}`, fill: "#ef4444", fontSize: 9, position: "insideBottomLeft" }} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
