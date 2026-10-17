"use client";
import { UserRound } from "lucide-react";
import type { UsersResponse } from "@/types/auth";
import { useOptionsApi } from "@/lib/optionsApi";
import { useAuth } from "@/components/auth/AuthGate";
import { PasswordCard, ProfileCard, UsersCard } from "@/components/account/AccountCards";

export default function AccountPage() {
  const auth = useAuth();
  const me = auth?.user ?? null;
  const isAdmin = me?.role === "admin";
  const users = useOptionsApi<UsersResponse>(isAdmin ? "/api/admin/users" : null, 60_000);

  return (
    <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#e2e8f0] flex items-center gap-2.5"><UserRound size={20} className="text-[#ff9933]" /> Your account</h1>
        <p className="text-sm text-[#8391a7] mt-1">
          {isAdmin ? "Your name and password, and everyone who can sign in to this dashboard." : "Your name and password."}
        </p>
      </div>
      {!me ? (
        <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
          <div className="skeleton h-80 rounded-xl" /><div className="skeleton h-80 rounded-xl" />
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)] items-start">
          <div className="flex flex-col gap-5 min-w-0">
            <ProfileCard key={me.id} user={me} />
            <PasswordCard />
          </div>
          {isAdmin && <div className="min-w-0"><UsersCard me={me} data={users.data} refresh={() => users.refresh()} /></div>}
        </div>
      )}
    </main>
  );
}
