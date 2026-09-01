"use client";

/**
 * The settings shell: a persistent left sub-navigation over nested routes.
 * Each concern is its own route under /settings/*, so new panels are added by
 * dropping in a folder — the pattern a production settings area grows on.
 *
 * The rail lists quiet, icon-led group labels with plain items beneath; the
 * active item is a soft grey pill. The content area opens with an eyebrow
 * naming the group, then the panel's own title and boxed cards. On narrow
 * screens the rail collapses into a scrollable tab bar.
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
    group: "My account",
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
  const currentGroup =
    NAV.find(({ items }) => items.some(({ href }) => pathname.startsWith(href)))
      ?.group ?? "Settings";

  return (
    <div className="-m-4 flex min-h-full md:-m-6">
      {/* Desktop rail */}
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-slate-50/70 px-4 py-6 md:block">
        <nav className="sticky top-6">
          <h1 className="mb-6 px-2 text-base font-semibold tracking-tight text-ink-900">
            Settings
          </h1>
          <div className="space-y-6">
            {NAV.map(({ group, icon: Icon, items }) => (
              <div key={group}>
                <p className="mb-1.5 flex items-center gap-2 px-2 text-xs font-medium text-ink-400">
                  <Icon className="h-3.5 w-3.5" aria-hidden />
                  {group}
                </p>
                <ul className="space-y-0.5">
                  {items.map(({ href, label }) => {
                    const active = pathname.startsWith(href);
                    return (
                      <li key={href}>
                        <Link
                          href={href}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "block rounded-md px-3 py-1.5 text-sm transition-colors",
                            active
                              ? "bg-slate-200/70 font-medium text-ink-900"
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
      </aside>

      {/* Content column */}
      <div className="min-w-0 flex-1">
        {/* Narrow screens: heading + scrollable tab bar */}
        <div className="border-b border-slate-200 bg-white px-4 pt-4 md:hidden">
          <h1 className="mb-3 text-base font-semibold tracking-tight text-ink-900">
            Settings
          </h1>
          <nav className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-3">
            {NAV.flatMap(({ items }) => items).map(({ href, label }) => {
              const active = pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-ink-900 text-white"
                      : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="px-4 py-6 sm:px-8 sm:py-8">
          <p className="mb-1 text-xs font-medium text-ink-400">{currentGroup}</p>
          <div className="max-w-3xl pb-10">{children}</div>
        </div>
      </div>
    </div>
  );
}
