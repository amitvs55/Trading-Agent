"use client";
import { useState } from "react";
import { cn, formatINR, formatINRShort, formatPct, formatVolume, changeColor, impactColor } from "@/lib/utils";
import type { MarketDataOutput, SentimentOutput, NewsOutput, FundamentalsOutput } from "@/types/pipeline";

interface Props {
  market:       MarketDataOutput;
  sentiment:    SentimentOutput;
  news:         NewsOutput;
  fundamentals: FundamentalsOutput;
}

const TABS = ["Market Data", "Sentiment", "News", "Fundamentals"] as const;
type Tab = typeof TABS[number];

export function Stage1DataCollection({ market, sentiment, news, fundamentals }: Props) {
  const [tab, setTab] = useState<Tab>("Market Data");
  const ind = market.indicators;

  return (
    <div>
      {/* Tab bar */}
      <div className="flex border-b border-[#1e2d45]">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-5 py-2.5 text-xs font-semibold border-b-2 transition-colors",
              tab === t ? "text-[#ff9933] border-[#ff9933]" : "text-[#64748b] border-transparent hover:text-[#e2e8f0]"
            )}
          >{t}</button>
        ))}
      </div>

      {/* ── Market Data ── */}
      {tab === "Market Data" && (
        <div className="p-5">
          {/* Price header */}
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-bold font-mono text-[#e2e8f0]">{formatINR(market.current_price, 2)}</span>
                <span className={cn("text-xs font-semibold px-2 py-1 rounded", market.price_change_pct_1d != null && market.price_change_pct_1d >= 0 ? "bg-[#22c55e22] text-green" : "bg-[#ef444422] text-red")}>
                  {market.price_change_pct_1d != null ? (market.price_change_pct_1d >= 0 ? "▲" : "▼") : ""} {formatPct(market.price_change_pct_1d)}
                </span>
              </div>
              <div className="text-xs mt-1 text-[#64748b]">{market.ticker} · NSE/BSE</div>
            </div>
            <div className={cn(
              "px-4 py-2 rounded-lg border text-center",
              market.trend_signal === "bullish" ? "bg-[#22c55e22] border-[#22c55e44]" :
              market.trend_signal === "bearish" ? "bg-[#ef444422] border-[#ef444433]" : "bg-card border-[#1e2d45]"
            )}>
              <div className="text-xs text-[#64748b] mb-1">Trend</div>
              <div className={cn("font-bold text-sm uppercase",
                market.trend_signal === "bullish" ? "text-green" :
                market.trend_signal === "bearish" ? "text-red" : "text-[#94a3b8]"
              )}>{market.trend_signal}</div>
            </div>
          </div>

          {/* Indicators grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
            {/* RSI */}
            <div className="bg-bg border border-[#1e2d45] rounded-lg p-3">
              <div className="text-xs text-[#64748b] mb-2">RSI (14)</div>
              <div className={cn("text-xl font-bold font-mono", ind.rsi_14 != null && ind.rsi_14 > 70 ? "text-red" : ind.rsi_14 != null && ind.rsi_14 < 30 ? "text-green" : "text-yellow")}>
                {ind.rsi_14?.toFixed(1) ?? "—"}
              </div>
              <div className="text-xs mt-1 text-[#64748b]">
                {ind.rsi_14 != null ? (ind.rsi_14 > 70 ? "Overbought" : ind.rsi_14 < 30 ? "Oversold" : "Neutral zone") : ""}
              </div>
              {ind.rsi_14 != null && (
                <div className="mt-2 h-1 bg-[#1e2d45] rounded">
                  <div className="h-1 rounded" style={{ width: `${ind.rsi_14}%`, background: ind.rsi_14 > 70 ? "#ef4444" : ind.rsi_14 < 30 ? "#22c55e" : "#f59e0b" }} />
                </div>
              )}
            </div>
            {/* MACD */}
            <div className="bg-bg border border-[#1e2d45] rounded-lg p-3">
              <div className="text-xs text-[#64748b] mb-2">MACD</div>
              <div className={cn("text-xl font-bold font-mono", ind.macd_line != null && ind.macd_line >= 0 ? "text-green" : "text-red")}>
                {ind.macd_line != null ? (ind.macd_line >= 0 ? "+" : "") + ind.macd_line.toFixed(2) : "—"}
              </div>
              <div className="text-xs mt-1 text-[#64748b]">
                Signal: {ind.macd_signal?.toFixed(2) ?? "—"} · Hist: {ind.macd_histogram != null ? (ind.macd_histogram >= 0 ? "+" : "") + ind.macd_histogram.toFixed(2) : "—"}
              </div>
              {ind.macd_histogram != null && (
                <div className={cn("text-xs mt-2", ind.macd_histogram >= 0 ? "text-green" : "text-red")}>
                  {ind.macd_histogram >= 0 ? "▲ Bullish" : "▼ Bearish"}
                </div>
              )}
            </div>
            {/* Volume */}
            <div className="bg-bg border border-[#1e2d45] rounded-lg p-3">
              <div className="text-xs text-[#64748b] mb-2">Volume</div>
              <div className="text-xl font-bold font-mono text-[#e2e8f0]">{formatVolume(market.volume)}</div>
              <div className="text-xs mt-1 text-[#64748b]">Avg: {formatVolume(market.avg_volume_10d)} (10d)</div>
              {market.volume != null && market.avg_volume_10d != null && (
                <div className={cn("text-xs mt-2", market.volume > market.avg_volume_10d ? "text-green" : "text-red")}>
                  {formatPct((market.volume - market.avg_volume_10d) / market.avg_volume_10d * 100)} vs avg
                </div>
              )}
            </div>
          </div>

          {/* BB + MA */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="bg-bg border border-[#1e2d45] rounded-lg p-3">
              <div className="text-xs text-[#64748b] mb-2">Bollinger Bands (20)</div>
              <div className="flex justify-between text-xs font-mono">
                <span className="text-red">↓ {formatINR(ind.bollinger_lower, 0)}</span>
                <span className="text-[#64748b]">Mid: {formatINR(ind.bollinger_middle, 0)}</span>
                <span className="text-green">↑ {formatINR(ind.bollinger_upper, 0)}</span>
              </div>
              {ind.bollinger_lower != null && ind.bollinger_upper != null && (
                <div className="mt-2 h-1.5 bg-[#ff993315] rounded relative">
                  <div className="absolute top-0 h-1.5 w-0.5 bg-[#ff9933] rounded"
                    style={{ left: `${Math.max(0, Math.min(100, (market.current_price - ind.bollinger_lower) / (ind.bollinger_upper - ind.bollinger_lower) * 100))}%`, boxShadow: "0 0 6px #ff9933" }} />
                </div>
              )}
            </div>
            <div className="bg-bg border border-[#1e2d45] rounded-lg p-3">
              <div className="text-xs text-[#64748b] mb-2">Moving Averages</div>
              {[
                { label: "SMA 20", val: ind.sma_20 },
                { label: "SMA 50", val: ind.sma_50 },
                { label: "EMA 12", val: ind.ema_12 },
              ].map(({ label, val }) => (
                <div key={label} className="flex justify-between text-xs font-mono mb-1">
                  <span className="text-[#64748b]">{label}</span>
                  <span className="text-yellow">{formatINR(val, 0)}</span>
                  {val != null && (
                    <span className={cn("text-[10px]", market.current_price >= val ? "text-green" : "text-red")}>
                      {market.current_price >= val ? "▲ Above" : "▼ Below"}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 52-week range */}
          {market.fifty_two_week_low != null && market.fifty_two_week_high != null && (
            <div className="bg-bg border border-[#1e2d45] rounded-lg p-3">
              <div className="flex justify-between text-xs mb-2">
                <span className="text-[#64748b]">52-Week Range</span>
                <span className="font-mono text-[#64748b]">{formatINR(market.fifty_two_week_low, 0)} — {formatINR(market.fifty_two_week_high, 0)}</span>
              </div>
              <div className="h-1.5 bg-[#1e2d45] rounded relative">
                <div className="h-1.5 rounded" style={{ width: "100%", background: "linear-gradient(to right,#ef444433,#22c55e33)" }} />
                <div className="absolute top-[-2px] h-2.5 w-0.5 bg-[#ff9933] rounded"
                  style={{ left: `${(market.current_price - market.fifty_two_week_low) / (market.fifty_two_week_high - market.fifty_two_week_low) * 100}%`, boxShadow: "0 0 6px #ff9933" }} />
              </div>
              <div className="flex justify-between text-xs font-mono mt-1.5">
                <span className="text-red">{formatINR(market.fifty_two_week_low, 0)}</span>
                <span className="text-[#ff9933]">{formatINR(market.current_price, 2)} ({Math.round((market.current_price - market.fifty_two_week_low) / (market.fifty_two_week_high - market.fifty_two_week_low) * 100)}th pct)</span>
                <span className="text-green">{formatINR(market.fifty_two_week_high, 0)}</span>
              </div>
            </div>
          )}

          {/* Summary */}
          <p className="mt-4 text-xs text-[#94a3b8] leading-relaxed border-t border-[#1e2d45] pt-4">{market.summary}</p>
        </div>
      )}

      {/* ── Sentiment ── */}
      {tab === "Sentiment" && (
        <div className="p-5">
          <div className="flex items-center gap-4 mb-4">
            <div className="text-4xl font-bold font-mono" style={{ color: sentiment.overall_score >= 0 ? "#22c55e" : "#ef4444" }}>
              {sentiment.overall_score >= 0 ? "+" : ""}{sentiment.overall_score.toFixed(2)}
            </div>
            <div>
              <div className="text-sm font-medium text-[#e2e8f0]">Overall Sentiment</div>
              <div className="text-xs text-[#64748b] mt-0.5">{sentiment.data_source}</div>
            </div>
          </div>
          <div className="h-2 bg-[#1e2d45] rounded mb-4">
            <div className="h-2 rounded" style={{ width: `${(sentiment.overall_score + 1) / 2 * 100}%`, background: sentiment.overall_score >= 0 ? "#22c55e" : "#ef4444" }} />
          </div>
          <div className="grid grid-cols-2 gap-3 mb-4">
            {[
              { label: "Twitter / X",   val: sentiment.twitter_score },
              { label: "Reddit",         val: sentiment.reddit_score  },
            ].map(({ label, val }) => (
              <div key={label} className="bg-bg border border-[#1e2d45] rounded-lg p-3">
                <div className="text-xs text-[#64748b] mb-1">{label}</div>
                <div className={cn("text-xl font-bold font-mono", val != null && val >= 0 ? "text-green" : "text-red")}>
                  {val != null ? (val >= 0 ? "+" : "") + val.toFixed(2) : "—"}
                </div>
              </div>
            ))}
          </div>
          {sentiment.sample_posts.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-[#64748b] mb-2 tracking-wide">SAMPLE POSTS</div>
              <div className="flex flex-col gap-2">
                {sentiment.sample_posts.slice(0, 4).map((p, i) => (
                  <div key={i} className="text-xs text-[#94a3b8] bg-bg border border-[#1e2d45] rounded p-2.5 leading-relaxed">"{p}"</div>
                ))}
              </div>
            </div>
          )}
          <p className="mt-4 text-xs text-[#94a3b8] leading-relaxed border-t border-[#1e2d45] pt-4">{sentiment.summary}</p>
        </div>
      )}

      {/* ── News ── */}
      {tab === "News" && (
        <div className="p-5">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs text-[#64748b]">Overall Impact:</span>
            <span className={cn("text-xs font-semibold px-2 py-0.5 rounded", impactColor(news.overall_impact))}>
              {news.overall_impact.replace("_", " ").toUpperCase()}
            </span>
          </div>
          <div className="flex flex-col gap-2 mb-4">
            {news.articles.map((a, i) => (
              <div key={i} className="bg-bg border border-[#1e2d45] rounded-lg p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs text-[#e2e8f0] leading-relaxed flex-1">{a.headline}</div>
                  <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0", impactColor(a.impact))}>
                    {a.impact.replace("_", " ").toUpperCase()}
                  </span>
                </div>
                <div className="flex justify-between mt-1.5">
                  <span className="text-[10px] text-[#64748b]">{a.source}</span>
                  <span className="text-[10px] text-[#64748b]">Relevance: {Math.round(a.relevance_score * 100)}%</span>
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-[#94a3b8] leading-relaxed border-t border-[#1e2d45] pt-4">{news.summary}</p>
        </div>
      )}

      {/* ── Fundamentals ── */}
      {tab === "Fundamentals" && (
        <div className="p-5">
          <div className="grid grid-cols-2 gap-3 mb-4">
            {[
              { label: "Market Cap",     val: formatINRShort(fundamentals.market_cap) },
              { label: "P/E Ratio",      val: fundamentals.pe_ratio?.toFixed(1) ?? "—" },
              { label: "Forward P/E",    val: fundamentals.forward_pe?.toFixed(1) ?? "—" },
              { label: "EPS",            val: formatINR(fundamentals.eps) },
              { label: "Revenue Growth", val: formatPct(fundamentals.revenue_growth ? fundamentals.revenue_growth * 100 : null) },
              { label: "Profit Margin",  val: formatPct(fundamentals.profit_margin  ? fundamentals.profit_margin  * 100 : null) },
              { label: "Debt / Equity",  val: fundamentals.debt_to_equity?.toFixed(2) ?? "—" },
              { label: "Insider Buys",   val: formatPct(fundamentals.insider_buy_pct) },
            ].map(({ label, val }) => (
              <div key={label} className="bg-bg border border-[#1e2d45] rounded-lg p-3 flex justify-between items-center">
                <span className="text-xs text-[#64748b]">{label}</span>
                <span className="text-xs font-mono font-semibold text-[#e2e8f0]">{val}</span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs text-[#64748b]">Health Score:</span>
            <span className={cn("text-xs font-bold px-2 py-0.5 rounded uppercase",
              fundamentals.health_score === "strong"   ? "bg-[#22c55e22] text-green" :
              fundamentals.health_score === "moderate" ? "bg-[#f59e0b22] text-yellow" : "bg-[#ef444422] text-red"
            )}>{fundamentals.health_score}</span>
            {fundamentals.sector && <span className="text-xs text-[#64748b]">· {fundamentals.sector}</span>}
          </div>
          {fundamentals.business_summary && (
            <p className="text-xs text-[#94a3b8] leading-relaxed">{fundamentals.business_summary.slice(0, 300)}…</p>
          )}
          <p className="mt-4 text-xs text-[#94a3b8] leading-relaxed border-t border-[#1e2d45] pt-4">{fundamentals.summary}</p>
        </div>
      )}
    </div>
  );
}
