"use client";

/**
 * The public landing page. Signed-in visitors go straight to the dashboard;
 * everyone else gets the pitch: what Tarazu does, the reliability principles
 * it refuses to break, and the door to signup.
 *
 * Everything here is static copy and CSS in the app's own design tokens. The
 * "product" visual in the hero is built from divs, not screenshots, so it
 * never goes stale.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  FileSearch,
  FlaskConical,
  GitCompareArrows,
  KeyRound,
  MessageSquare,
  Scale,
  ScanText,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

function Feature({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <span className="inline-flex rounded-lg bg-brand-50 p-2.5 text-brand-700">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <h3 className="mt-4 text-sm font-bold text-ink-900">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{children}</p>
    </div>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-800 text-sm font-bold text-white">
        {number}
      </span>
      <h3 className="mt-4 text-sm font-bold text-ink-900">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{children}</p>
    </div>
  );
}

/** A schematic of the review screen, drawn in CSS so it never goes stale. */
function ProductMock() {
  const rows = [
    { party: "Karachi Packaging Co.", amount: "PKR 49,500", tone: "flag", label: "Flagged" },
    { party: "Sialkot Metal Works", amount: "PKR 284,000", tone: "ok", label: "Matched" },
    { party: "Multan Fabrics Ltd", amount: "PKR 45,900", tone: "warn", label: "Partial" },
  ];
  const bars = [62, 38, 30, 58, 22, 18, 14, 12, 26];
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
      <div className="flex items-center gap-1.5 border-b border-slate-100 bg-slate-50 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-slate-300" />
        <span className="ml-3 text-[10px] font-medium text-ink-400">
          Haroon Textiles · CASE-2026-06
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 px-4 pt-4">
        {[
          ["Review items", "10"],
          ["Matched", "80%"],
          ["Flags", "8"],
          ["Readiness", "60"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-slate-50 px-3 py-2">
            <p className="text-base font-bold text-ink-900 tabular-nums">{value}</p>
            <p className="text-[9px] text-ink-400">{label}</p>
          </div>
        ))}
      </div>
      <div className="px-4 py-3">
        {rows.map((row) => (
          <div
            key={row.party}
            className="flex items-center justify-between border-b border-slate-100 py-2 last:border-0"
          >
            <span className="text-xs font-medium text-ink-900">{row.party}</span>
            <span className="flex items-center gap-3">
              <span className="text-xs text-ink-600 tabular-nums">{row.amount}</span>
              <span
                className={
                  row.tone === "ok"
                    ? "rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-semibold text-emerald-700 ring-1 ring-emerald-200"
                    : row.tone === "warn"
                      ? "rounded-full bg-amber-50 px-2 py-0.5 text-[9px] font-semibold text-amber-800 ring-1 ring-amber-200"
                      : "rounded-full bg-purple-50 px-2 py-0.5 text-[9px] font-semibold text-purple-700 ring-1 ring-purple-200"
                }
              >
                {row.label}
              </span>
            </span>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-100 px-4 py-3">
        <p className="mb-2 text-[9px] font-semibold uppercase tracking-wide text-ink-400">
          Benford first-digit distribution
        </p>
        <div className="flex h-12 items-end gap-1.5">
          {bars.map((height, index) => (
            <span
              key={index}
              className={index % 2 === 0 ? "flex-1 rounded-t bg-brand-700" : "flex-1 rounded-t bg-brand-200"}
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const { session } = useAuth();
  const router = useRouter();

  // A signed-in auditor came here to work, not to read the pitch.
  React.useEffect(() => {
    if (session) router.replace("/dashboard");
  }, [session, router]);

  return (
    <div className="min-h-screen bg-white text-ink-900">
      {/* Nav */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-800 text-white">
              <Scale className="h-4.5 w-4.5" aria-hidden />
            </span>
            <span>
              <span className="block text-base font-bold leading-tight tracking-tight text-brand-950">
                Tarazu
              </span>
              <span className="block text-[10px] leading-tight text-ink-400">
                AI Audit Assistant
              </span>
            </span>
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-medium text-ink-600 md:flex">
            <a href="#features" className="hover:text-ink-900">Features</a>
            <a href="#how-it-works" className="hover:text-ink-900">How it works</a>
            <a href="#trust" className="hover:text-ink-900">Trust</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="rounded-md px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-brand-800 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-900"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto grid max-w-6xl items-center gap-14 px-6 py-20 lg:grid-cols-2">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 ring-1 ring-brand-200">
            ترازو · the scales
          </p>
          <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-ink-900 md:text-5xl">
            The AI weighs the evidence.
            <br />
            <span className="text-brand-800">You deliver the verdict.</span>
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-600">
            Upload a bank statement, invoices, and a ledger. Tarazu reads them
            with vision AI, reconciles every entry with deterministic code,
            flags the fraud risks, and records each of your decisions in an
            immutable audit trail.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 rounded-md bg-brand-800 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-900"
            >
              Start your first case
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-6 py-3 text-sm font-semibold text-ink-900 transition-colors hover:border-brand-700 hover:text-brand-800"
            >
              See how it works
            </a>
          </div>
          <ul className="mt-8 space-y-2 text-sm text-ink-600">
            {[
              "No AI ever touches a number: all math is deterministic code",
              "Every extracted value traces to its document, page, and position",
              "Client data is never used to train models",
            ].map((point) => (
              <li key={point} className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
                {point}
              </li>
            ))}
          </ul>
        </div>
        <ProductMock />
      </section>

      {/* Principles strip */}
      <section id="trust" className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-8 px-6 py-14 md:grid-cols-3">
          {[
            {
              title: "The AI suggests, the human decides",
              body: "Every item requires your explicit approve or reject. There is no auto-approval path anywhere in the product.",
            },
            {
              title: "All math is deterministic code",
              body: "Sums, matching, and red-flag rules run in pure Python and pandas. A model never produces or influences a number.",
            },
            {
              title: "Every action is on the record",
              body: "Human or AI, every step lands in an append-only audit trail. Nothing can edit or delete a record, by design.",
            },
          ].map(({ title, body }) => (
            <div key={title}>
              <ShieldCheck className="h-5 w-5 text-brand-700" aria-hidden />
              <h3 className="mt-3 text-sm font-bold text-ink-900">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-ink-900">
            Everything a reconciliation needs, nothing you cannot defend
          </h2>
          <p className="mt-3 text-ink-600">
            Built for audit firms: every feature keeps the evidence, the math,
            and the decision separate and inspectable.
          </p>
        </div>
        <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          <Feature icon={ScanText} title="Vision extraction with provenance">
            Qwen VL reads statements, invoices, and photos. Every value carries
            a confidence level and its exact page and position, so you can see
            where each number came from.
          </Feature>
          <Feature icon={GitCompareArrows} title="Deterministic matching">
            Three tiers of reconciliation in pure pandas: exact, date-window,
            and tolerance. Each match ships a plain-language reason an auditor
            can quote.
          </Feature>
          <Feature icon={FileSearch} title="Red-flag rules">
            Round numbers, duplicates, weekend entries, near-limit amounts,
            structuring, and sequence gaps, each with severity and explanation.
          </Feature>
          <Feature icon={FlaskConical} title="Benford analysis">
            First-digit distribution against the expected curve with a
            chi-square statistic. Indicative, clearly labelled, and never a
            verdict on its own.
          </Feature>
          <Feature icon={ShieldCheck} title="Immutable audit trail">
            A case-wide timeline of every upload, extraction, flag, and
            decision, filterable by actor and action. Append-only at the
            database level.
          </Feature>
          <Feature icon={MessageSquare} title="Assistant in English and Urdu">
            Ask about flags, matches, or any party by name, by typing or by
            voice. Answers cite their source documents and refuse what they
            cannot ground.
          </Feature>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-ink-900">
              From documents to defensible report
            </h2>
            <p className="mt-3 text-ink-600">
              One case takes three steps. The pipeline is visible while it
              runs, and each stage is inspectable afterwards.
            </p>
          </div>
          <div className="mt-12 grid gap-5 md:grid-cols-3">
            <Step number="1" title="Upload three documents">
              The client&apos;s ledger (Excel or CSV), the bank statement
              (PDF), and the invoices (PDFs or phone photos). That opens a
              case.
            </Step>
            <Step number="2" title="Tarazu reads and reconciles">
              Vision extraction with confidence and provenance, deterministic
              matching, six red-flag rules, and Benford analysis, all in one
              pass.
            </Step>
            <Step number="3" title="You decide, Tarazu records">
              Approve or reject each item with the evidence side by side. Ask
              the assistant anything about the case. Every action lands in the
              trail.
            </Step>
          </div>
        </div>
      </section>

      {/* Team + integrations */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-ink-900">
              Built for the whole firm
            </h2>
            <p className="mt-3 max-w-lg text-ink-600">
              Tarazu is multi-tenant from the first line of code: your cases,
              documents, and trail belong to your organization alone, and
              another firm&apos;s data does not exist from where you stand.
            </p>
            <ul className="mt-6 space-y-4">
              {[
                {
                  icon: Users,
                  title: "Members and invitations",
                  body: "Invite colleagues with single-use join codes and roles. Owners manage the workspace; members review and decide.",
                },
                {
                  icon: KeyRound,
                  title: "API keys for your tooling",
                  body: "Scoped read or write keys connect n8n, Zapier, or your own scripts. Every automated action still names the accountable person.",
                },
                {
                  icon: Upload,
                  title: "Cases at a glance",
                  body: "Every engagement with its pending items and flags in one list. Switch the whole workspace with one click.",
                },
              ].map(({ icon: Icon, title, body }) => (
                <li key={title} className="flex gap-3">
                  <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                    <Icon className="h-4.5 w-4.5" aria-hidden />
                  </span>
                  <span>
                    <span className="block text-sm font-bold text-ink-900">{title}</span>
                    <span className="block text-sm leading-relaxed text-ink-600">{body}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-8">
            <h3 className="text-sm font-bold text-ink-900">
              The seven reliability rules
            </h3>
            <p className="mt-1.5 text-sm text-ink-600">
              Tarazu is built on rules that no feature is allowed to break.
              Three of them above; the rest in the same spirit:
            </p>
            <ul className="mt-4 space-y-2.5 text-sm text-ink-600">
              {[
                "Every AI output carries a confidence level",
                "Every extracted number is traceable to its source",
                "Client data never trains models",
                "The assistant answers only from uploaded documents",
              ].map((rule) => (
                <li key={rule} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
                  {rule}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* CTA band */}
      <section className="border-t border-slate-200 bg-brand-950">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-6 py-16 text-center">
          <h2 className="max-w-2xl text-3xl font-bold tracking-tight text-white">
            Bring your next reconciliation. Keep your professional judgment.
          </h2>
          <p className="max-w-xl text-brand-100">
            Create your firm&apos;s workspace in a minute. Upload a case, review
            the flags, and see the audit trail write itself.
          </p>
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 rounded-md bg-white px-6 py-3 text-sm font-semibold text-brand-900 transition-colors hover:bg-brand-50"
          >
            Get started
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 text-sm text-ink-400 md:flex-row">
          <span className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-brand-800 text-white">
              <Scale className="h-3.5 w-3.5" aria-hidden />
            </span>
            Tarazu, the AI audit assistant
          </span>
          <span className="flex items-center gap-6">
            <Link href="/login" className="hover:text-ink-900">Sign in</Link>
            <Link href="/signup" className="hover:text-ink-900">Create a workspace</Link>
          </span>
          <span>The AI suggests, the human decides.</span>
        </div>
      </footer>
    </div>
  );
}
