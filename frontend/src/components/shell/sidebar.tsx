"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/brand/logo";
import { NAV } from "./nav-items";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-line px-4 py-5 lg:flex">
      <Link href="/app" className="px-2" aria-label="MoneyWealth AI home">
        <Logo />
      </Link>

      <nav className="mt-8 flex flex-1 flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon, enabled }) => {
          const active = pathname === href;
          if (!enabled) {
            return (
              <span
                key={href}
                className="flex cursor-default items-center justify-between rounded-[12px] px-3 py-2.5 text-sm text-fg-subtle/60"
              >
                <span className="flex items-center gap-3">
                  <Icon className="size-[18px]" /> {label}
                </span>
                <span className="rounded-full bg-hover px-1.5 py-0.5 text-[10px] text-fg-subtle">
                  soon
                </span>
              </span>
            );
          }
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-[12px] px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-brand/12 text-brand ring-1 ring-brand/20"
                  : "text-fg-muted hover:bg-hover hover:text-fg",
              )}
            >
              <Icon className="size-[18px]" /> {label}
            </Link>
          );
        })}
      </nav>

      <div className="rounded-[14px] border border-line bg-surface/40 p-3 text-xs text-fg-subtle">
        <span className="font-medium text-fg">Financial tools via MCP</span> — review the data
        behind your decisions.
      </div>
    </aside>
  );
}
