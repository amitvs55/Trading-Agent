import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <main className="max-w-screen-sm mx-auto px-4 py-16 text-center fade-in">
      <div className="w-12 h-12 mx-auto rounded-xl grid place-items-center bg-[#ff993314] border border-[#ff993333] mb-4">
        <Compass size={20} className="text-[#ff9933]" aria-hidden />
      </div>
      <p className="text-[11px] font-mono tracking-widest text-[#8391a7]">404</p>
      <h1 className="text-lg font-bold text-[#e2e8f0] mt-1">This page doesn&apos;t exist</h1>
      <p className="text-sm text-[#94a3b8] mt-2 leading-relaxed">
        The link may be old, or the address mistyped. Everything is still running.
      </p>
      <div className="mt-6 flex items-center justify-center gap-2 flex-wrap">
        <Link href="/signals" className="inline-flex items-center justify-center h-11 px-5 rounded-lg bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0b0f1a]">
          Go to Signals
        </Link>
        <Link href="/performance" className="inline-flex items-center justify-center h-11 px-5 rounded-lg bg-card border border-[#1e2d45] text-[#e2e8f0] hover:border-[#2d3e58] text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff9933]">
          Track record
        </Link>
      </div>
    </main>
  );
}
