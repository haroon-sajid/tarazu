"use client";

/**
 * The three states every screen must have (hackathon plan: "Every screen needs
 * a decent loading state and error state"). Empty lives here too.
 */

import { AlertTriangle, Inbox, RotateCw } from "lucide-react";
import { Button } from "./button";

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-rose-200 bg-rose-50/60 px-6 py-12 text-center">
      <AlertTriangle className="h-8 w-8 text-rose-500" aria-hidden />
      <div>
        <p className="text-sm font-semibold text-rose-800">{title}</p>
        <p className="mt-1 max-w-md text-sm text-rose-700">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw className="h-3.5 w-3.5" aria-hidden />
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <Inbox className="h-8 w-8 text-ink-400" aria-hidden />
      <div>
        <p className="text-sm font-semibold text-ink-900">{title}</p>
        <p className="mt-1 max-w-md text-sm text-ink-600">{message}</p>
      </div>
      {action}
    </div>
  );
}
