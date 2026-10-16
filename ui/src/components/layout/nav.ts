import { BarChart3, Bot, Coins, FlaskConical, History, PlugZap, Radio, UserRound, Wallet, type LucideIcon } from "lucide-react";

export type Role = "admin" | "viewer";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: Role[];
  primary?: boolean;            // gets its own tab in the mobile bottom bar
}

// One list for the desktop bar, the mobile bottom bar and the "More" sheet.
// Viewers get the signal pages; everything that costs money or changes settings is admin-only
// (the API enforces the same split: see api/main.py and require_admin).
export const NAV: NavItem[] = [
  { href: "/signals",     label: "Signals",     icon: Radio,        roles: ["admin", "viewer"], primary: true },
  { href: "/paper",       label: "Paper",       icon: Wallet,       roles: ["admin", "viewer"], primary: true },
  { href: "/performance", label: "Performance", icon: BarChart3,    roles: ["admin", "viewer"], primary: true },
  { href: "/agents",      label: "Agents",      icon: Bot,          roles: ["admin"],           primary: true },
  { href: "/",            label: "Research",    icon: FlaskConical, roles: ["admin"] },
  { href: "/history",     label: "History",     icon: History,      roles: ["admin"] },
  { href: "/usage",       label: "Usage",       icon: Coins,        roles: ["admin"] },
  { href: "/connectors",  label: "Connectors",  icon: PlugZap,      roles: ["admin"] },
];

export const ACCOUNT_ITEM: NavItem = { href: "/account", label: "Your account", icon: UserRound, roles: ["admin", "viewer"] };

const VIEWER_PATHS = ["/signals", "/paper", "/performance", "/account"];

export function roleOf(role: string | undefined): Role {
  return role === "admin" ? "admin" : "viewer";
}

export function navFor(role: string | undefined): NavItem[] {
  const r = roleOf(role);
  return NAV.filter(i => i.roles.includes(r));
}

export function canView(path: string, role: string | undefined): boolean {
  if (roleOf(role) === "admin") return true;
  return VIEWER_PATHS.some(p => path === p || path.startsWith(`${p}/`));
}

export function isActive(path: string, href: string): boolean {
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}
