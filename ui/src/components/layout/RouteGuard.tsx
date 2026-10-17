"use client";
import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Lock } from "lucide-react";
import { useAuth } from "@/components/auth/AuthGate";
import { canView, isAdminPath } from "./nav";

/** Keeps viewers on the pages meant for them (the API refuses the rest anyway). An admin page
 *  waits until the role is known, so a viewer never sees it flash or trips a 403 loading it. */
export function RouteGuard({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const path = usePathname();
  const router = useRouter();
  const user = auth?.user;
  const waiting = !user && isAdminPath(path);              // role not known yet
  const allowed = !user ? !waiting : canView(path, user.role);
  const home = !!user && !allowed && path === "/";

  useEffect(() => {
    if (home) router.replace("/signals");                 // the research page is the admins' home; viewers start at signals
  }, [home, router]);

  if (waiting) return <main className="min-h-screen" aria-busy />;
  if (allowed) return <>{children}</>;
  if (home) return <main className="min-h-[60vh]" aria-busy />;
  return (
    <main className="max-w-screen-sm mx-auto px-4 py-16 text-center fade-in">
      <div className="w-12 h-12 mx-auto rounded-xl grid place-items-center bg-[#ff993314] border border-[#ff993333] mb-4">
        <Lock size={20} className="text-[#ff9933]" />
      </div>
      <h1 className="text-lg font-bold text-[#e2e8f0]">This page is for admins</h1>
      <p className="text-sm text-[#8391a7] mt-2 leading-relaxed">
        Your account can see the live signals, the paper account and the track record. Ask an admin if you need more.
      </p>
      <Link href="/signals" className="inline-flex items-center justify-center mt-6 h-11 px-5 rounded-lg bg-[#ff9933] hover:bg-[#ffa94d] text-[#0b0f1a] text-sm font-semibold">
        Go to Signals
      </Link>
    </main>
  );
}
