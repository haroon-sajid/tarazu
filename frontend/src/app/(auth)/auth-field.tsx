"use client";

import * as React from "react";
import { Eye, EyeOff, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AuthFieldProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  icon: LucideIcon;
  hint?: string;
}

/**
 * Outlined field for the signed-out screens: the label sits on the border,
 * a leading icon inside the field. Only the (auth) pages use this; app
 * screens keep the standard Input.
 */
export const AuthField = React.forwardRef<HTMLInputElement, AuthFieldProps>(
  ({ className, label, icon: Icon, hint, id, ...props }, ref) => {
    const generatedId = React.useId();
    const inputId = id ?? generatedId;
    return (
      <div>
        <div className="relative">
          <label
            htmlFor={inputId}
            className="absolute -top-2 left-3 z-10 bg-white px-1 text-xs font-medium text-ink-600 lg:bg-surface"
          >
            {label}
          </label>
          <Icon
            className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-400"
            aria-hidden
          />
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "h-12 w-full rounded-xl border border-slate-300 bg-transparent pl-10 pr-3 text-sm text-ink-900",
              "placeholder:text-ink-400",
              "focus:border-brand-700 focus:outline-none focus:ring-1 focus:ring-brand-700",
              "disabled:cursor-not-allowed disabled:bg-slate-50",
              className,
            )}
            {...props}
          />
        </div>
        {hint && <p className="mt-1 text-[11px] text-ink-400">{hint}</p>}
      </div>
    );
  },
);
AuthField.displayName = "AuthField";

/** AuthField as a password with a show/hide toggle. */
export const AuthPasswordField = React.forwardRef<
  HTMLInputElement,
  Omit<AuthFieldProps, "type">
>(({ className, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false);
  return (
    <div className="relative">
      <AuthField
        ref={ref}
        type={visible ? "text" : "password"}
        className={cn("pr-11", className)}
        {...props}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "Hide password" : "Show password"}
        className="absolute right-3 top-6 -translate-y-1/2 text-ink-400 hover:text-ink-600"
      >
        {visible ? (
          <EyeOff className="h-5 w-5" aria-hidden />
        ) : (
          <Eye className="h-5 w-5" aria-hidden />
        )}
      </button>
    </div>
  );
});
AuthPasswordField.displayName = "AuthPasswordField";
