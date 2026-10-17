"use client";

/** The app shell itself failed (layout error). Rendered without the layout, so styles are inline. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#0b0f1a",
                     color: "#e2e8f0", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif" }}>
        <main style={{ maxWidth: 420, margin: 16, padding: 32, borderRadius: 16, background: "#111827",
                       border: "1px solid #1e2d45", textAlign: "center" }}>
          <h1 style={{ fontSize: 18, margin: "0 0 8px" }}>TradingAgents couldn&apos;t load</h1>
          <p style={{ fontSize: 14, color: "#94a3b8", lineHeight: 1.5, margin: 0 }}>
            The dashboard hit an error starting up. Signals, alerts and recording run on the server and are not
            affected.
          </p>
          <button type="button" onClick={reset}
                  style={{ marginTop: 20, height: 44, padding: "0 20px", borderRadius: 8, border: 0, cursor: "pointer",
                           background: "#ff9933", color: "#0b0f1a", fontWeight: 600, fontSize: 14 }}>
            Reload
          </button>
        </main>
      </body>
    </html>
  );
}
