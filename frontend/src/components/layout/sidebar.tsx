"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
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
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/review", label: "Review", icon: TableProperties },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/report", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { signOut } = useAuth();

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-800 text-white">
          <Scale className="h-4.5 w-4.5" aria-hidden />
        </span>
        <div>
          <p className="text-base font-bold tracking-tight text-brand-950">Tarazu</p>
          <p className="text-[10px] leading-tight text-ink-400">AI Audit Assistant</p>
        </div>
      </div>

      <nav className="mt-2 flex flex-col gap-1 px-3">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-brand-800 text-white"
                  : "text-ink-600 hover:bg-slate-100 hover:text-ink-900",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto px-3 pb-4">
        <button
          onClick={() => {
            signOut();
            router.replace("/login");
          }}
          className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-ink-600 transition-colors hover:bg-slate-100 hover:text-rose-600"
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Sign out
        </button>
        <p className="mt-3 px-3 text-[10px] leading-relaxed text-ink-400">
          The AI suggests, the human decides. Every number traces to its source.
        </p>
      </div>
    </aside>
  );
}
