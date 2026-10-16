"use client";
import { useState } from "react";
import { useTradeHistory } from "@/hooks/useTradeHistory";
import { TradeHistoryTable } from "@/components/history/TradeHistoryTable";

const LIMIT = 20;

export default function HistoryPage() {
  const [page, setPage] = useState(0);
  const { records, total, isLoading, refresh } = useTradeHistory({
    limit: LIMIT, offset: page * LIMIT,
  });

  return (
    <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#e2e8f0]">Trade History</h1>
        <p className="text-sm text-[#64748b] mt-1">All simulated NSE/BSE paper trades logged by the pipeline</p>
      </div>
      <TradeHistoryTable
        records={records}
        total={total}
        isLoading={isLoading}
        onRefresh={refresh}
        page={page}
        setPage={setPage}
        limit={LIMIT}
      />
    </main>
  );
}
