"use client";
import { TradeHistoryTable } from "@/components/history/TradeHistoryTable";

export default function HistoryPage() {
  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#e2e8f0]">Trade History</h1>
        <p className="text-sm text-[#8391a7] mt-1">Every research run and its simulated NSE/BSE decision, kept in the database</p>
      </div>
      <TradeHistoryTable limit={20} />
    </main>
  );
}
