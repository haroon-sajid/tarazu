"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart2,
  BarChart3,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Dices,
  Files,
  FileText,
  MessageSquare,
  Scale,
  Settings,
  ShieldCheck,
  TableProperties,
  TrendingUp,
  Upload,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ProfileMenu } from "@/components/layout/profile-menu";

/**
 * The rail, in the order the work actually happens: who you audit, the
 * engagement, the documents, the decisions, then what comes out of it. The
 * firm-wide screens (Insights, Compare) sit at the end because they are read
 * between engagements rather than during one.
 */
const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/review", label: "Review", icon: TableProperties },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/clients", label: "Clients", icon: Users },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/sampling", label: "Sampling", icon: Dices },
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
  { href: "/audit-trail", label: "Audit trail", icon: ShieldCheck },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/insights", label: "Insights", icon: TrendingUp },
  { href: "/analytics", label: "Analytics", icon: BarChart2 },
  { href: "/settings", label: "Settings", icon: Settings },
];

const COLLAPSED_KEY = "tarazu.sidebar";
/** Matches Tailwind's `md` breakpoint, which every rule below is keyed to. */
const MOBILE_QUERY = "(max-width: 767.98px)";

function readCollapsed() {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "collapsed";
  } catch {
    return false;
  }
}

/**
 * One rail, two shapes, decided by the viewport rather than by a measurement
 * taken in JavaScript: below `md` it is an off-canvas drawer at full label
 * width, at `md` and up it is a column in the page flow that the auditor can
 * collapse to icons. Collapsing is therefore a desktop affordance only — every
 * collapsed rule is `md:`-scoped, so the drawer can never open half-collapsed.
 *
 * The saved choice is read during the first render, not in an effect, so the
 * rail paints at its final width instead of snapping a frame later.
 */
export function Sidebar({
  mobileOpen,
  onMobileOpenChange,
}: {
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(readCollapsed);
  // Width and transform animate on a real interaction, never on first paint.
  const [animate, setAnimate] = React.useState(false);

  React.useEffect(() => {
    const frame = window.requestAnimationFrame(() => setAnimate(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  // The drawer belongs to the small viewport alone: growing past the
  // breakpoint closes it, so a resize can never strand a locked page scroll
  // or a backdrop behind the desktop rail.
  React.useEffect(() => {
    const query = window.matchMedia(MOBILE_QUERY);
    const sync = () => {
      if (!query.matches) onMobileOpenChange(false);
    };
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, [onMobileOpenChange]);

  // Navigating is what the drawer is for; it closes once it has done its job.
  React.useEffect(() => {
    onMobileOpenChange(false);
  }, [pathname, onMobileOpenChange]);

  React.useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [mobileOpen]);

  const toggleCollapsed = () =>
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
    <>
      {/* Drawer backdrop — mobile only, and only while the drawer is open. */}
      <div
        onClick={() => onMobileOpenChange(false)}
        aria-hidden
        className={cn(
          "fixed inset-0 z-40 bg-ink-900/50 transition-opacity duration-300 md:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      <aside
        className={cn(
          // Mobile: an off-canvas drawer at full label width.
          "fixed inset-y-0 left-0 z-50 flex w-64 max-w-[80vw] shrink-0 flex-col",
          "border-r border-slate-200 bg-white",
          mobileOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full",
          // Desktop: a column in the page flow. `relative` (not `static`) so
          // the collapse handle keeps this element as its containing block.
          "md:relative md:inset-auto md:z-50 md:max-w-none md:translate-x-0 md:shadow-none",
          collapsed ? "md:w-16" : "md:w-56",
          animate && "transition-[width,transform] duration-300",
        )}
      >
        {/* Collapse handle: desktop only — there is nothing to collapse into
            on a phone, where the rail is a drawer that closes outright. */}
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "absolute -right-3 top-7 z-50 hidden h-6 w-6 items-center justify-center rounded-full md:flex",
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
        <div
          className={cn(
            "flex shrink-0 items-center px-4 py-5",
            collapsed && "md:justify-center md:px-0",
          )}
        >
          <Link
            href="/dashboard"
            className="flex items-center gap-2.5"
            title="Tarazu — AI Audit Assistant"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-brand-700 to-brand-900 text-white shadow-md">
              <Scale className="h-4.5 w-4.5" aria-hidden />
            </span>
            <span className={cn("min-w-0", collapsed && "md:hidden")}>
              <span className="block text-base font-bold leading-tight tracking-tight text-brand-950">
                Tarazu
              </span>
              <span className="block text-[10px] leading-tight text-ink-400">
                AI Audit Assistant
              </span>
            </span>
          </Link>
        </div>

        {/* Navigation. It scrolls on its own so a short window never squeezes
            the rows or pushes the account menu out of reach. */}
        <nav
          className={cn(
            "flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3 pb-2",
            collapsed && "md:px-2",
          )}
        >
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                title={collapsed ? label : undefined}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150",
                  collapsed && "md:justify-center md:gap-0 md:px-0",
                  active
                    ? "bg-gradient-to-r from-brand-700 to-brand-800 text-white shadow-md"
                    : "text-ink-600 hover:bg-slate-100 hover:text-brand-700",
                )}
              >
                <Icon className="h-5 w-5 shrink-0" aria-hidden />
                <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:hidden")}>
                  {label}
                </span>
              </Link>
            );
          })}
        </nav>

        {/* Account */}
        <div
          className={cn(
            "shrink-0 border-t border-slate-100 px-3 pb-3 pt-2",
            collapsed && "md:px-2",
          )}
        >
          <ProfileMenu collapsed={collapsed} />
        </div>
      </aside>

    </>
  );
}
