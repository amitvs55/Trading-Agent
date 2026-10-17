"use client";
import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCcw } from "lucide-react";

/** A page crashed while rendering. The navbar and the rest of the app keep working. */
export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("Page error", error);
  }, [error]);

  return (
    <main className="max-w-screen-sm mx-auto px-4 py-16 text-center fade-in">
      <div className="w-12 h-12 mx-auto rounded-xl grid place-items-center bg-[#ef444414] border border-[#ef444433] mb-4">
        <AlertTriangle size={20} className="text-red" aria-hidden />
      </div>
      <h1 className="text-lg font-bold text-[#e2e8f0]">This page hit an error</h1>
      <p className="text-sm text-[#94a3b8] mt-2 leading-relaxed">
        Only this page is affected: signals, alerts and recording carry on in the background.
        Try again, or open another page.
      </p>
      {error.digest && <p className="text-[11px] font-mono text-[#8391a7] mt-3">Reference {error.digest}</p>}
      <div className="mt-6 flex items-center justify-center gap-2 flex-wrap">
        <button type="button" onClick={reset}
                className="inline-flex items-center justify-center gap-2 h-11 px-5 rounded-lg bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0b0f1a]">
          <RotateCcw size={15} aria-hidden /> Try again
        </button>
        <Link href="/signals" className="inline-flex items-center justify-center h-11 px-5 rounded-lg bg-card border border-[#1e2d45] text-[#e2e8f0] hover:border-[#2d3e58] text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]">
          Go to Signals
        </Link>
      </div>
    </main>
  );
}
