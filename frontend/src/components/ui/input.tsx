import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
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

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
}

/** A native select styled identically to Input, label and hint included. */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, hint, id, children, ...props }, ref) => {
    const generatedId = React.useId();
    const selectId = id ?? generatedId;
    return (
      <div>
        {label && (
          <label
            htmlFor={selectId}
            className="mb-1 block text-xs font-medium text-ink-600"
          >
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={cn(
            "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900",
            "focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600",
            "disabled:cursor-not-allowed disabled:bg-slate-50",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        {hint && <p className="mt-1 text-[11px] text-ink-400">{hint}</p>}
      </div>
    );
  },
);
Select.displayName = "Select";

/** A password field with a show/hide toggle. Same props as Input, minus type. */
export const PasswordInput = React.forwardRef<
  HTMLInputElement,
  Omit<InputProps, "type">
>(({ className, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false);
  return (
    <div className="relative">
      <Input
        ref={ref}
        type={visible ? "text" : "password"}
        className={cn("pr-10", className)}
        {...props}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "Hide password" : "Show password"}
        className={cn(
          "absolute right-2 text-ink-400 hover:text-ink-600",
          // Sits over the input row, below any label above it.
          props.label ? "top-[30px]" : "top-2.5",
        )}
      >
        {visible ? (
          <EyeOff className="h-4 w-4" aria-hidden />
        ) : (
          <Eye className="h-4 w-4" aria-hidden />
        )}
      </button>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";
