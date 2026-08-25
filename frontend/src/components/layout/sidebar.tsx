"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  FileText,
  LogOut,
  Scale,
  Settings,
  TableProperties,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/review", label: "Review", icon: TableProperties },
  { href: "/report", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

const COLLAPSED_KEY = "tarazu.sidebar";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { signOut } = useAuth();
  const [collapsed, setCollapsed] = React.useState(false);

  // Restore the saved state after mount so server and first client render agree.
  React.useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSED_KEY) === "collapsed");
    } catch {
      // Storage can be unavailable; stay expanded.
    }
  }, []);

  const toggle = () =>
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(COLLAPSED_KEY, next ? "collapsed" : "expanded");
      } catch {
        // Not persisted, still toggles for this visit.
      }
      return next;
    });

  return (
    <aside
      className={cn(
        "relative flex shrink-0 flex-col border-r border-slate-200 bg-white transition-[width] duration-200",
        collapsed ? "w-16" : "w-56",
      )}
    >
      {/* Collapse toggle: a floating button riding the sidebar's edge, always
          visible in both states. */}
      <button
        onClick={toggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className={cn(
          "absolute -right-3 top-7 z-20 flex h-6 w-6 items-center justify-center rounded-full",
          "border border-slate-300 bg-white text-ink-600 shadow-sm transition-colors",
          "hover:border-brand-700 hover:bg-brand-50 hover:text-brand-800",
        )}
      >
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        ) : (
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
        )}
      </button>

      {/* Brand */}
      <div className={cn("flex items-center py-5", collapsed ? "justify-center px-0" : "px-4")}>
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5"
          title="Tarazu — AI Audit Assistant"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-800 text-white">
            <Scale className="h-4.5 w-4.5" aria-hidden />
          </span>
          {!collapsed && (
            <span>
              <span className="block text-base font-bold leading-tight tracking-tight text-brand-950">
                Tarazu
              </span>
              <span className="block text-[10px] leading-tight text-ink-400">
                AI Audit Assistant
              </span>
            </span>
          )}
        </Link>
      </div>

      <nav className={cn("mt-1 flex flex-col gap-1", collapsed ? "px-2" : "px-3")}>
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md py-2 text-sm font-medium transition-colors",
                collapsed ? "justify-center px-0" : "px-3",
                active
                  ? "bg-brand-800 text-white"
                  : "text-ink-600 hover:bg-slate-100 hover:text-ink-900",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {!collapsed && label}
            </Link>
          );
        })}
      </nav>

      <div className={cn("mt-auto pb-4", collapsed ? "px-2" : "px-3")}>
        <button
          onClick={() => {
            signOut();
            router.replace("/login");
          }}
          title={collapsed ? "Sign out" : undefined}
          className={cn(
            "flex w-full items-center gap-2.5 rounded-md py-2 text-sm font-medium text-ink-600 transition-colors hover:bg-slate-100 hover:text-rose-600",
            collapsed ? "justify-center px-0" : "px-3",
          )}
        >
          <LogOut className="h-4 w-4 shrink-0" aria-hidden />
          {!collapsed && "Sign out"}
        </button>
        {!collapsed && (
          <p className="mt-3 px-3 text-[10px] leading-relaxed text-ink-400">
            The AI suggests, the human decides. Every number traces to its source.
          </p>
        )}
      </div>
    </aside>
  );
}
