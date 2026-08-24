"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * A lightweight hover tooltip for truncated reason strings. CSS-only
 * positioning; desktop-only app, so hover is a safe assumption.
 */
export function Tooltip({
  content,
  children,
  className,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("group/tooltip relative inline-block", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 z-40 mb-1.5 w-max max-w-sm -translate-x-1/2",
          "rounded-md bg-ink-900 px-3 py-2 text-xs leading-relaxed text-white shadow-lg",
          "opacity-0 transition-opacity duration-100 group-hover/tooltip:opacity-100",
        )}
      >
        {content}
      </span>
    </span>
  );
}
