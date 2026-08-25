import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, hint, id, ...props }, ref) => {
    const generatedId = React.useId();
    const inputId = id ?? generatedId;
    return (
      <div>
        {label && (
          <label
            htmlFor={inputId}
            className="mb-1 block text-xs font-medium text-ink-600"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900",
            "placeholder:text-ink-400",
            "focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600",
            "disabled:cursor-not-allowed disabled:bg-slate-50",
            className,
          )}
          {...props}
        />
        {hint && <p className="mt-1 text-[11px] text-ink-400">{hint}</p>}
      </div>
    );
  },
);
Input.displayName = "Input";
