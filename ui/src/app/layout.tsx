import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";
import { AuthGate } from "@/components/auth/AuthGate";
import { DataProvider } from "@/components/layout/DataProvider";

// Self-hosted at build time and preloaded; the fallback font is metric-matched, so text never reflows.
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "TradingAgents India",
  description: "Live NIFTY options signals and multi-agent research for NSE",
};

export const viewport: Viewport = {
  themeColor: "#0b0f1a",
  colorScheme: "dark",
};

// Runs before first paint: when this browser has no session, hide the app shell so a signed-out
// visitor never sees it flash before the sign-in screen.
const AUTH_HINT = `try{if(!localStorage.getItem("auth.session"))document.documentElement.classList.add("auth-out")}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: AUTH_HINT }} />
      </head>
      <body>
        <DataProvider>
          <AuthGate>
            <Navbar />
            {children}
            <footer className="border-t border-[#1e2d45] mt-10 py-4 px-6">
              <div className="india-stripe mb-3" />
              <div className="max-w-screen-2xl mx-auto flex flex-wrap items-center justify-between gap-2 text-xs text-[#475569]">
                <span>
                  TradingAgents India · NSE · Live options signals + research pipeline ·{" "}
                  <span className="text-[#ff993388]">For personal research and education. Not investment advice.</span>
                </span>
                <span className="font-mono">All times IST (UTC+5:30)</span>
              </div>
            </footer>
          </AuthGate>
        </DataProvider>
      </body>
    </html>
  );
}
