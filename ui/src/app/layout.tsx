import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";
import { AuthGate } from "@/components/auth/AuthGate";
import { DataProvider } from "@/components/layout/DataProvider";
import { MobileNav } from "@/components/layout/MobileNav";
import { RouteGuard } from "@/components/layout/RouteGuard";

// Self-hosted at build time and preloaded; the fallback font is metric-matched, so text never reflows.
const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "TradingAgents India",
  description: "Live NIFTY options signals and multi-agent research for NSE",
  applicationName: "TradingAgents India",
  icons: {
    icon: [{ url: "/favicon-32.png", sizes: "32x32", type: "image/png" }, { url: "/icon-192.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  appleWebApp: { capable: true, title: "TradingAgents", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },          // prices and IDs must not turn into phone-number links
};

export const viewport: Viewport = {
  themeColor: "#0b0f1a",
  colorScheme: "dark",
  viewportFit: "cover",            // lets the bottom bar sit above the iPhone home indicator (safe-area insets)
};

// Runs before first paint: when this browser has no session, hide the app shell so a signed-out
// visitor never sees it flash before the sign-in screen. It also marks the cached role (role-admin /
// role-viewer), so role-only placeholders can hold their space from the server-rendered first paint.
const AUTH_HINT = `try{var d=document.documentElement;if(!localStorage.getItem("auth.session"))d.classList.add("auth-out");`
  + `var u=JSON.parse(localStorage.getItem("auth.user")||"null");if(u&&/^[a-z]+$/.test(u.role))d.classList.add("role-"+u.role)}catch(e){}`;

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
            {/* On phones the fixed bottom bar covers the last 56 px (+ home indicator): leave room for it */}
            <div className="pb-[calc(64px+env(safe-area-inset-bottom))] lg:pb-0">
            <div className="min-h-[calc(100svh-3.5rem)]"><RouteGuard>{children}</RouteGuard></div>
            <footer className="border-t border-[#1e2d45] mt-10 py-4 px-4 sm:px-6">
              <div className="india-stripe mb-3" />
              <div className="max-w-screen-2xl mx-auto flex flex-wrap items-center justify-between gap-2 text-xs text-[#8391a7]">
                <span>
                  TradingAgents India · NSE · Live options signals + research pipeline ·{" "}
                  <span className="text-[#d98a4a]">For personal research and education. Not investment advice.</span>
                </span>
                <span className="font-mono">All times IST (UTC+5:30)</span>
              </div>
            </footer>
            </div>
            <MobileNav />
          </AuthGate>
        </DataProvider>
      </body>
    </html>
  );
}
