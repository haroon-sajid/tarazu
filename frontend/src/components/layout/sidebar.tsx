"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Files,
  FileText,
  MessageSquare,
  Scale,
  Settings,
  ShieldCheck,
  TableProperties,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ProfileMenu } from "@/components/layout/profile-menu";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/review", label: "Review", icon: TableProperties },
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
  { href: "/audit-trail", label: "Audit trail", icon: ShieldCheck },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

const COLLAPSED_KEY = "tarazu.sidebar";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);

  // Restore the saved state after mount and keep the rail in sync with
  // viewport changes, including resizing an already-open desktop window.
  React.useEffect(() => {
    const syncToViewport = () => {
      if (window.innerWidth < 768) {
        setCollapsed(true);
        return;
      }

      try {
        setCollapsed(window.localStorage.getItem(COLLAPSED_KEY) === "collapsed");
      } catch {
        setCollapsed(false);
      }
    };

    syncToViewport();
    window.addEventListener("resize", syncToViewport);
    return () => window.removeEventListener("resize", syncToViewport);
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

      <div className={cn("mt-auto border-t border-slate-100 pb-3 pt-2", collapsed ? "px-2" : "px-3")}>
        <ProfileMenu collapsed={collapsed} />
      </div>
    </aside>
  );
}
