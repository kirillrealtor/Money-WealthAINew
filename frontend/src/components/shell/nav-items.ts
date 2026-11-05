import {
  LayoutDashboard,
  Landmark,
  Wallet,
  Target,
  TrendingDown,
  PieChart,
  Sparkles,
  Bell,
  Settings,
  Receipt,
  ShoppingBag,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; enabled: boolean };

/** Single source of truth for the app navigation (sidebar + mobile drawer). */
export const NAV: NavItem[] = [
  { href: "/app", label: "Dashboard", icon: LayoutDashboard, enabled: true },
  { href: "/app/accounts", label: "Accounts", icon: Landmark, enabled: true },
  { href: "/app/transactions", label: "Transactions", icon: Receipt, enabled: true },
  { href: "/app/budgets", label: "Budgets", icon: Wallet, enabled: true },
  { href: "/app/goals", label: "Goals", icon: Target, enabled: true },
  { href: "/app/debt", label: "Debt", icon: TrendingDown, enabled: true },
  { href: "/app/portfolio", label: "Portfolio", icon: PieChart, enabled: true },
  { href: "/app/advisor", label: "Advisor", icon: Sparkles, enabled: true },
  { href: "/app/purchases", label: "Purchase planner", icon: ShoppingBag, enabled: true },
  { href: "/app/notifications", label: "Alerts", icon: Bell, enabled: true },
  { href: "/app/settings", label: "Settings", icon: Settings, enabled: true },
];
