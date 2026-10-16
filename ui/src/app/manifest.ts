import type { MetadataRoute } from "next";

// "Add to Home Screen": opens full-screen on the Signals page, like an app.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TradingAgents India",
    short_name: "TradingAgents",
    description: "Live NIFTY options signals, paper trading and the track record",
    start_url: "/signals",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0b0f1a",
    theme_color: "#0b0f1a",
    // Drawn by ui/scripts/make_icons.py (the mark sits in the central 70%, safe for maskable crops)
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
