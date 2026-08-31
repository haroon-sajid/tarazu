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
  Menu,
  MessageSquare,
  Scale,
  Settings,
  ShieldCheck,
  TableProperties,
  TrendingUp,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ProfileMenu } from "@/components/layout/profile-menu";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/analytics", label: "Analytics", icon: TrendingUp },
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
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [isMobile, setIsMobile] = React.useState(false);

  // Restore the saved state after mount and keep the rail in sync with viewport changes
  React.useEffect(() => {
    const syncToViewport = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      
      if (mobile) {
        setCollapsed(false);
        setMobileOpen(false);
      } else {
        try {
          setCollapsed(window.localStorage.getItem(COLLAPSED_KEY) === "collapsed");
        } catch {
          setCollapsed(false);
        }
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

  const toggleMobile = () => setMobileOpen(!mobileOpen);
  const closeMobileMenu = () => setMobileOpen(false);

  // Close mobile menu when route changes
  React.useEffect(() => {
    closeMobileMenu();
  }, [pathname]);

  // Prevent body scroll when mobile menu is open
  React.useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  return (
    <>
      {/* Mobile Menu Toggle */}
      {isMobile && (
        <button
          onClick={toggleMobile}
          aria-label="Toggle menu"
          className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-brand-800 text-white shadow-lg transition-all hover-lift md:hidden"
        >
          {mobileOpen ? (
            <X className="h-6 w-6" aria-hidden />
          ) : (
            <Menu className="h-6 w-6" aria-hidden />
          )}
        </button>
      )}

      {/* Backdrop for mobile */}
      {isMobile && mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm transition-opacity duration-300 md:hidden"
          onClick={closeMobileMenu}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "sidebar-animated relative flex shrink-0 flex-col border-r border-slate-200 bg-white transition-all duration-300",
          isMobile
            ? cn(
                "fixed top-0 left-0 h-screen z-40 shadow-2xl",
                mobileOpen ? "w-64 translate-x-0" : "w-64 -translate-x-full"
              )
            : collapsed
              ? "w-16"
              : "w-56",
        )}
      >
        {/* Desktop Collapse toggle */}
        {!isMobile && (
          <button
            onClick={toggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "absolute -right-3 top-7 z-20 flex h-6 w-6 items-center justify-center rounded-full",
              "border border-slate-300 bg-white text-ink-600 shadow-sm transition-all hover-lift",
              "hover:border-brand-700 hover:bg-brand-50 hover:text-brand-800",
            )}
          >
            {collapsed ? (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
            )}
          </button>
        )}

        {/* Brand */}
        <div className={cn("flex items-center py-5 transition-all duration-300", collapsed ? "justify-center px-0" : "px-4")}>
          <Link
            href="/dashboard"
            className="flex items-center gap-2.5 transition-transform hover:scale-105"
            title="Tarazu — AI Audit Assistant"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-brand-700 to-brand-900 text-white shadow-md transition-all hover:shadow-lg hover:scale-110">
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

        {/* Navigation */}
        <nav className={cn("mt-1 flex flex-col gap-1 transition-all duration-300", collapsed ? "px-2" : "px-3")}>
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                title={collapsed ? label : undefined}
                className={cn(
                  "group flex items-center gap-2.5 rounded-lg py-2.5 text-sm font-medium transition-all duration-200",
                  collapsed ? "justify-center px-0" : "px-3",
                  active
                    ? "bg-gradient-to-r from-brand-700 to-brand-800 text-white shadow-md"
                    : "text-ink-600 hover:bg-slate-100 hover:text-brand-700",
                  "hover-lift"
                )}
              >
                <Icon className={cn(
                  "h-5 w-5 shrink-0 transition-all",
                  active ? "scale-110" : "group-hover:scale-110"
                )} aria-hidden />
                {!collapsed && (
                  <span className="flex-1">{label}</span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Profile Menu */}
        <div className={cn(
          "mt-auto border-t border-slate-100 pb-3 pt-2 transition-all duration-300",
          collapsed ? "px-2" : "px-3"
        )}>
          <ProfileMenu collapsed={collapsed} />
        </div>
      </aside>
    </>
  );
}
