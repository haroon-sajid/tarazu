import { Scale } from "lucide-react";

/**
 * The signed-out layout: a brand panel beside the form. No sidebar, no
 * header — there is no case to show until someone signs in.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="hidden w-[44%] flex-col justify-between bg-brand-950 p-10 lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 text-white">
            <Scale className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="text-lg font-bold tracking-tight text-white">Tarazu</p>
            <p className="text-xs text-brand-200/70">AI Audit Assistant</p>
          </div>
        </div>

        <div>
          <h1 className="max-w-md text-3xl font-bold leading-tight text-white">
            The AI weighs the evidence.
            <br />
            The auditor delivers the verdict.
          </h1>
          <ul className="mt-8 space-y-3 text-sm text-brand-100/80">
            <li>— Every number traces to its source document, page, and location.</li>
            <li>— All matching and math is deterministic code, never AI.</li>
            <li>— Every decision is a human&apos;s, logged to an immutable audit trail.</li>
          </ul>
        </div>

        <p className="text-xs text-brand-200/50">
          ترازو — &ldquo;the scales&rdquo;
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 items-center justify-center bg-surface px-6">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
