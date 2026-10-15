import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";

export const metadata: Metadata = {
  title: "TradingAgents India",
  description: "Multi-agent LLM trading analysis — NSE/BSE",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Navbar />
        {children}
        <footer className="border-t border-[#1e2d45] mt-10 py-4 px-6">
          <div className="india-stripe mb-3" />
          <div className="max-w-screen-2xl mx-auto flex items-center justify-between text-xs text-[#475569]">
            <span>
              TradingAgents India · NSE/BSE · Multi-Agent LLM Pipeline · GPT-4o-mini ·{" "}
              <span className="text-[#ff993388]">For educational/simulation purposes only. Not financial advice.</span>
            </span>
            <span className="font-mono">v1.0.0 · 13 agents · 6 stages · IST (UTC+5:30)</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
