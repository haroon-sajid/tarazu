"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A minimal accessible modal — enough for the reject-reason prompt without
 * pulling in a dependency. Closes on Escape and on backdrop click.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className={cn(
          "w-full max-w-md rounded-lg border border-slate-200 bg-white p-4 shadow-xl md:p-5",
          // Below md only: a dialog taller than a short phone screen scrolls
          // inside its panel instead of running off the fixed backdrop.
          "max-md:max-h-[calc(100dvh-2rem)] max-md:overflow-y-auto",
          className,
        )}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-ink-400 hover:bg-slate-100 hover:text-ink-600"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
