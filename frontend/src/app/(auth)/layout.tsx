import Link from "next/link";
import { Scale } from "lucide-react";

/**
 * The signed-out layout: a brand panel beside the form on desktop, a branded
 * header with an overlapping form card on mobile and tablet. No sidebar, no
 * header — there is no case to show until someone signs in.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* Desktop brand panel */}
      <div className="hidden w-[44%] flex-col justify-between bg-brand-950 p-10 lg:flex">
        <Link
          href="/"
          title="Back to the Tarazu home page"
          className="flex w-fit items-center gap-3 transition-opacity hover:opacity-80"
        >
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 text-white">
            <Scale className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="text-lg font-bold tracking-tight text-white">Tarazu</p>
            <p className="text-xs text-brand-200/70">AI Audit Assistant</p>
          </div>
        </Link>

        <div>
          <h1 className="max-w-md text-3xl font-bold leading-tight text-white">
            The AI weighs the evidence.
            <br />
            The auditor delivers the verdict.
          </h1>
          <ul className="mt-8 space-y-3 text-sm text-brand-100/80">
            <li>• Every number traces to its source document, page, and location.</li>
            <li>• All matching and math is deterministic code, never AI.</li>
            <li>• Every decision is a human&apos;s, logged to an immutable audit trail.</li>
          </ul>
        </div>

        <p className="text-xs text-brand-200/50">
          ترازو: &ldquo;the scales&rdquo;
        </p>
      </div>

      {/* Form panel: mobile green backdrop + white sheet, desktop centered form */}
      <div className="flex min-h-screen flex-1 flex-col bg-linear-to-b from-brand-900 to-brand-950 lg:min-h-0 lg:items-center lg:justify-center lg:bg-none lg:bg-surface lg:px-6">
        {/* Mobile / tablet branded header */}
        <div className="flex flex-col px-6 pb-10 pt-10 lg:hidden">
          <Link
            href="/"
            title="Back to the Tarazu home page"
            className="w-fit transition-opacity hover:opacity-80"
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-100 text-brand-900 shadow-sm">
              <Scale className="h-7 w-7" aria-hidden />
            </span>
            <p className="mt-4 text-3xl font-bold tracking-tight text-white">
              Tarazu <span className="text-amber-300">ترازو</span>
            </p>
            <p className="mt-1 text-sm text-brand-100/80">AI Audit Assistant</p>
          </Link>
        </div>

        {/* Form sheet: rises from the bottom on mobile, plain panel on desktop */}
        <div className="flex flex-1 flex-col rounded-t-[2rem] bg-white px-6 pb-8 pt-8 shadow-lg lg:flex-initial lg:rounded-none lg:bg-transparent lg:p-0 lg:shadow-none">
          <div className="mx-auto w-full max-w-sm flex-1">{children}</div>

          <div className="mx-auto mt-10 w-full max-w-sm text-center lg:hidden">
            <p className="text-lg font-bold text-brand-800">Tarazu</p>
            <p className="text-xs text-ink-400">AI Audit Assistant</p>
          </div>
        </div>
      </div>
    </div>
  );
}
