"use client";

/**
 * The settings shell: a persistent left sub-navigation over nested routes.
 * Each concern is its own route under /settings/*, so new panels are added by
 * dropping in a folder — the pattern a production settings area grows on.
 *
 * The rail lists groups with an icon-led header and plain items beneath, and
 * the content area renders flat sections (no boxed cards) with right-aligned
 * controls. On narrow screens the rail collapses into a scrollable tab bar.
 */

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Blocks,
  Building2,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV: {
  group: string;
  icon: LucideIcon;
  items: { href: string; label: string }[];
}[] = [
  {
    group: "Workspace",
    icon: Building2,
    items: [
      { href: "/settings/general", label: "General" },
      { href: "/settings/branding", label: "Report branding" },
      { href: "/settings/members", label: "Members" },
    ],
  },
  {
    group: "Account",
    icon: UserRound,
    items: [
      { href: "/settings/profile", label: "Profile" },
      { href: "/settings/account", label: "Account & security" },
      { href: "/settings/notifications", label: "Notifications" },
    ],
  },
  {
    group: "Developers",
    icon: Blocks,
    items: [
      { href: "/settings/api-keys", label: "API keys" },
      { href: "/settings/webhooks", label: "Webhooks" },
      { href: "/settings/integrations", label: "Integrations" },
    ],
  },
  {
    group: "Trust & data",
    icon: ShieldCheck,
    items: [
      { href: "/settings/compliance", label: "Compliance" },
      { href: "/settings/environment", label: "Environment" },
    ],
  },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="flex gap-10">
      {/* Desktop rail */}
      <div className="hidden w-56 shrink-0 border-r border-slate-200 pr-6 md:block">
        <nav className="sticky top-0">
          <h1 className="mb-5 px-2 text-lg font-bold tracking-tight text-ink-900">
            Settings
          </h1>
          <div className="space-y-6">
            {NAV.map(({ group, icon: Icon, items }) => (
              <div key={group}>
                <p className="mb-1 flex items-center gap-2 px-2 py-1 text-sm font-semibold text-ink-900">
                  <Icon className="h-4 w-4 text-ink-400" aria-hidden />
                  {group}
                </p>
                <ul className="space-y-0.5">
                  {items.map(({ href, label }) => {
                    const active = pathname.startsWith(href);
                    return (
                      <li key={href}>
                        <Link
                          href={href}
                          className={cn(
                            "block rounded-md py-1.5 pl-8 pr-2 text-sm transition-colors",
                            active
                              ? "bg-brand-50 font-medium text-brand-900"
                              : "text-ink-600 hover:bg-slate-100 hover:text-ink-900",
                          )}
                        >
                          {label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </nav>
      </div>

      {/* Narrow screens: heading + scrollable tab bar */}
      <div className="min-w-0 flex-1 pb-10">
        <div className="md:hidden">
          <h1 className="mb-3 text-lg font-bold tracking-tight text-ink-900">
            Settings
          </h1>
          <nav className="-mx-1 mb-6 flex gap-1 overflow-x-auto px-1 pb-2">
            {NAV.flatMap(({ items }) => items).map(({ href, label }) => {
              const active = pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-brand-800 text-white"
                      : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>

        {children}
      </div>
    </div>
  );
}
