import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "outline" | "ghost" | "success" | "danger";
type Size = "sm" | "md" | "lg";

const variantClasses: Record<Variant, string> = {
  default:
    "bg-linear-to-b from-brand-700 to-brand-800 text-white hover:from-brand-800 hover:to-brand-900 focus-visible:ring-brand-600 shadow-md hover:shadow-lg",
  outline:
    "border border-slate-300 bg-white text-ink-900 hover:bg-slate-50 hover:border-brand-600 focus-visible:ring-brand-600 transition-all",
  ghost: "text-ink-600 hover:bg-slate-100 hover:text-brand-700 focus-visible:ring-brand-600",
  success:
    "bg-linear-to-b from-emerald-500 to-emerald-600 text-white hover:from-emerald-600 hover:to-emerald-700 focus-visible:ring-emerald-500 shadow-md hover:shadow-lg",
  danger: "bg-linear-to-b from-rose-500 to-rose-600 text-white hover:from-rose-600 hover:to-rose-700 focus-visible:ring-rose-500 shadow-md hover:shadow-lg",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-6 text-sm",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "btn-interactive inline-flex items-center justify-center gap-1.5 rounded-lg font-medium",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1",
        "disabled:pointer-events-none disabled:opacity-50",
        "transition-all duration-200 ease-out",
        "hover:scale-105 active:scale-95",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
