/** @type {import('tailwindcss').Config} */
const config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg:      "#0b0f1a",
        surface: "#111827",
        card:    "#1a2233",
        border:  "#1e2d45",
        accent:  "#ff9933",
        green:   "#22c55e",
        red:     "#ef4444",
        yellow:  "#f59e0b",
        muted:   "#64748b",
      },
      fontFamily: {
        // Self-hosted by next/font (layout.tsx), with metric-matched fallbacks: no flash, no reflow
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(255,153,51,0)" },
          "50%":       { boxShadow: "0 0 0 6px rgba(255,153,51,0.2)" },
        },
        shimmer: {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "stage-pulse": {
          "0%, 100%": { borderColor: "rgba(255,153,51,0.3)", boxShadow: "0 0 0 0 rgba(255,153,51,0)" },
          "50%":       { borderColor: "rgba(255,153,51,0.9)", boxShadow: "0 0 10px 4px rgba(255,153,51,0.2)" },
        },
      },
      animation: {
        "pulse-glow":  "pulse-glow 1.5s ease-in-out infinite",
        shimmer:       "shimmer 1.5s infinite",
        "stage-pulse": "stage-pulse 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

module.exports = config;
