import { BarChart3, Bot, Coins, Crosshair, FlaskConical, History, PlugZap, Radio, ShieldCheck, UserRound, Wallet, type LucideIcon } from "lucide-react";

export type Role = "admin" | "viewer";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: Role[];
  primary?: boolean;            // gets its own tab in the mobile bottom bar
  tier: 1 | 2 | 3;              // desktop bar: 1 from lg, 2 from xl, 3 from 2xl; narrower bars list it under "More"
}

// One list for the desktop bar, the mobile bottom bar and the "More" sheet.
// Viewers get the signal pages; everything that costs money or changes settings is admin-only
// (the API enforces the same split: see api/main.py and require_admin).
export const NAV: NavItem[] = [
  { href: "/signals",     label: "Signals",     icon: Radio,        roles: ["admin", "viewer"], primary: true, tier: 1 },
  { href: "/check",       label: "Check",       icon: Crosshair,    roles: ["admin", "viewer"], primary: true, tier: 1 },
  { href: "/paper",       label: "Paper",       icon: Wallet,       roles: ["admin", "viewer"], primary: true, tier: 1 },
  { href: "/performance", label: "Performance", icon: BarChart3,    roles: ["admin", "viewer"], primary: true, tier: 1 },
  { href: "/agents",      label: "Agents",      icon: Bot,          roles: ["admin"],           tier: 1 },   // phones: in More
  { href: "/",            label: "Research",    icon: FlaskConical, roles: ["admin"], tier: 2 },
  { href: "/history",     label: "History",     icon: History,      roles: ["admin"], tier: 3 },
  { href: "/usage",       label: "Usage",       icon: Coins,        roles: ["admin"], tier: 3 },
  { href: "/operations",  label: "Operations",  icon: ShieldCheck,  roles: ["admin"], tier: 2 },
  { href: "/connectors",  label: "Connectors",  icon: PlugZap,      roles: ["admin"], tier: 3 },
];

export const ACCOUNT_ITEM: NavItem = { href: "/account", label: "Your account", icon: UserRound, roles: ["admin", "viewer"], tier: 1 };

// Tailwind needs the class names spelled out in full
export const BAR_CLASS: Record<NavItem["tier"], string> = { 1: "inline-flex", 2: "hidden xl:inline-flex", 3: "hidden 2xl:inline-flex" };
export const MORE_CLASS: Record<NavItem["tier"], string> = { 1: "hidden", 2: "flex xl:hidden", 3: "flex 2xl:hidden" };

// Pages only admins may open; anything else (including an unknown URL, which gets the 404 page) is open
const ADMIN_PATHS = NAV.filter(i => !i.roles.includes("viewer")).map(i => i.href);

export function roleOf(role: string | undefined): Role {
  return role === "admin" ? "admin" : "viewer";
}

export function navFor(role: string | undefined): NavItem[] {
  const r = roleOf(role);
  return NAV.filter(i => i.roles.includes(r));
}

export function isAdminPath(path: string): boolean {
  return ADMIN_PATHS.some(p => (p === "/" ? path === "/" : path === p || path.startsWith(`${p}/`)));
}

export function canView(path: string, role: string | undefined): boolean {
  return roleOf(role) === "admin" || !isAdminPath(path);
}

export function isActive(path: string, href: string): boolean {
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}
