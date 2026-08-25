"use client";

/**
 * The account menu: who is signed in, which organization scopes every
 * request, and the doors to the places that manage both. It lives in one
 * place — the sidebar foot — and its panel opens beside the sidebar at the
 * sidebar's own width, so it reads as an extension of the rail rather than
 * a floating window.
 *
 * The avatar and display name come from GET /v1/profile and refresh when the
 * settings page broadcasts a save ("tarazu:profile-updated").
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Building2,
  ChevronsUpDown,
  KeyRound,
  LogOut,
  ScrollText,
  SquarePen,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { FIXTURE_MODE, getProfile } from "@/lib/api";
import type { UserProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

const PROFILE_UPDATED_EVENT = "tarazu:profile-updated";

function Avatar({
  avatar,
  initial,
  className,
}: {
  avatar: string | null;
  initial: string;
  className: string;
}) {
  return avatar ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={avatar}
      alt=""
      aria-hidden
      className={cn(className, "rounded-full object-cover ring-1 ring-slate-200")}
    />
  ) : (
    <span
      className={cn(
        className,
        "flex items-center justify-center rounded-full bg-brand-800 font-semibold text-white",
      )}
    >
      {initial}
    </span>
  );
}

function MenuLink({
  href,
  icon: Icon,
  label,
  onNavigate,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink-900 transition-colors hover:bg-slate-100"
    >
      <Icon className="h-4 w-4 text-ink-400" aria-hidden />
      {label}
    </Link>
  );
}

export function ProfileMenu({ collapsed = false }: { collapsed?: boolean }) {
  const { session, signOut } = useAuth();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [profile, setProfile] = React.useState<UserProfile | null>(null);
  const rootRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let cancelled = false;
    const load = () =>
      getProfile()
        .then((loaded) => !cancelled && setProfile(loaded))
        .catch(() => {
          // No profile is a normal state; the initial letter stands in.
        });
    load();
    window.addEventListener(PROFILE_UPDATED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(PROFILE_UPDATED_EVENT, load);
    };
  }, []);

  React.useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!session) return null;

  const organizationName =
    session.organizationName ?? (FIXTURE_MODE ? "Demo Audit Firm" : "Your firm");
  const initial = (session.email[0] ?? "A").toUpperCase();
  const displayName =
    profile?.full_name ??
    (session.email.split("@")[0] ?? "auditor").replace(/^./, (c) => c.toUpperCase());
  const close = () => setOpen(false);

  const panel = (
    // Beside the rail, bottom-aligned with the trigger, at the sidebar's
    // expanded width — an extension of the sidebar, not a floating window.
    <div
      role="menu"
      className="absolute bottom-0 left-full z-50 ml-3 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-xl"
    >
      {/* One rich row is the whole identity block: it IS the "Your profile"
          entry, so nothing above it repeats what the trigger already shows. */}
      <Link
        href="/profile"
        onClick={close}
        title={`Your profile (${organizationName})`}
        className="flex items-center gap-2.5 rounded-md px-3 py-2 transition-colors hover:bg-slate-100"
      >
        <Avatar avatar={profile?.avatar ?? null} initial={initial} className="h-9 w-9 text-sm" />
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-ink-900">
            {displayName}
          </span>
          <span className="block truncate text-[11px] text-ink-400">
            Your profile{session.role ? ` · ${session.role}` : ""}
          </span>
        </span>
      </Link>

      <div className="my-2 border-t border-slate-100" />

      <MenuLink
        href="/settings/profile"
        icon={SquarePen}
        label="Profile settings"
        onNavigate={close}
      />
      <MenuLink
        href="/settings/general"
        icon={Building2}
        label="Organization settings"
        onNavigate={close}
      />
      <MenuLink href="/settings/api-keys" icon={KeyRound} label="API keys" onNavigate={close} />
      <MenuLink
        href="/settings/compliance"
        icon={ScrollText}
        label="Terms & compliance"
        onNavigate={close}
      />

      <div className="my-2 border-t border-slate-100" />

      <button
        role="menuitem"
        onClick={() => {
          close();
          signOut();
          router.replace("/login");
        }}
        className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink-900 transition-colors hover:bg-rose-50 hover:text-rose-600"
      >
        <LogOut className="h-4 w-4 text-ink-400" aria-hidden />
        Log out
      </button>
    </div>
  );

  return (
    <div ref={rootRef} className="relative">
      {open && panel}
      <button
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? displayName : undefined}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-md py-2 transition-colors hover:bg-slate-100",
          collapsed ? "justify-center px-0" : "px-2",
          open && "bg-slate-100",
        )}
      >
        <Avatar
          avatar={profile?.avatar ?? null}
          initial={initial}
          className="h-8 w-8 shrink-0 text-sm"
        />
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 text-left">
              <span className="block truncate text-sm font-medium text-ink-900">
                {displayName}
              </span>
              <span className="block truncate text-[10px] text-ink-400">
                {session.email}
              </span>
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-ink-400" aria-hidden />
          </>
        )}
      </button>
    </div>
  );
}
