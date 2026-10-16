import type { ReactNode } from "react";

/** Re-mounted on every route change: the new page settles in over 200 ms instead of snapping. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
