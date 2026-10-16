import type { User } from "@/types/auth";

/** "Amit Shinde", falling back to the username. */
export function displayName(u: Pick<User, "username" | "full_name"> | null | undefined): string {
  return u?.full_name?.trim() || u?.username || "";
}

/** "AS" for Amit Shinde, "A" for a username-only account. */
export function initials(u: Pick<User, "username" | "full_name"> | null | undefined): string {
  const name = u?.full_name?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
  }
  return (u?.username?.[0] ?? "?").toUpperCase();
}

/** A username suggestion from a full name: "Amit Shinde" → "amit". */
export function suggestUsername(fullName: string): string {
  return (fullName.trim().split(/\s+/)[0] ?? "").toLowerCase().replace(/[^a-z0-9_.-]/g, "");
}

export const ROLE_LABEL: Record<string, string> = { admin: "Admin", viewer: "Viewer" };
export const ROLE_HELP: Record<string, string> = {
  admin: "Everything, including keys, settings and other accounts",
  viewer: "Sees every page; can't change settings, keys or accounts",
};
