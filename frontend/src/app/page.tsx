"use client";

/**
 * The public landing page. Signed-in visitors go straight to the dashboard;
 * everyone else gets a human, authentic pitch about how Tarazu saves auditors
 * countless hours and gives them back control. Built on real stories, not AI copy.
 *
 * The page flows like a conversation: problem (the pain), solution (Tarazu),
 * proof (live demo), platform details, real use cases, and a simple CTA.
 *
 * Responsive notes. The page is built mobile-first with three tiers — phones
 * (<640px), tablets / small laptops (640–1023px) and desktops (≥1024px). Two
 * things in `globals.css` are written for the signed-in app shell but match
 * bare element selectors, so they reach this page too on viewports ≤768px:
 * `main` and `header` get `!important` padding, and the root font size drops to
 * 14px. The `p-0!` / `px-6!` utilities below cancel the padding, and the copy
 * uses pixel sizes so the rem change cannot skew the typography.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { IBM_Plex_Sans, Sora } from "next/font/google";
import {
  ArrowLeftRight,
  ArrowRight,
  Bot,
  Building2,
  Check,
  CheckCircle2,
  CirclePlay,
  Clock,
  CloudUpload,
  Code2,
  Database,
  Eye,
  FileText,
  Flag,
  Gauge,
  Landmark,
  LoaderCircle,
  Lock,
  Menu,
  Pause,
  Play,
  Receipt,
  Rocket,
  RotateCw,
  Scale,
  Table,
  TriangleAlert,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

const sora = Sora({ subsets: ["latin"], weight: ["600", "700"] });
const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"] });

const BTN_PRIMARY =
  "inline-flex items-center justify-center gap-2 rounded-[10px] bg-[#0E7C66] px-6 py-3 text-center text-[15px] font-semibold text-white transition-colors hover:bg-[#0A5F4F] sm:px-8 sm:py-3.5 md:text-base";
const BTN_GHOST =
  "inline-flex items-center justify-center gap-2 rounded-[10px] border-[1.5px] border-[#E1E7E4] bg-white px-6 py-3 text-center text-[15px] font-semibold text-[#10243A] transition-colors hover:border-[#10243A] hover:bg-[#F8FAF9] sm:px-8 sm:py-3.5 md:text-base";

const NAV_LINKS: { label: string; href: string }[] = [
  { label: "Platform", href: "#how" },
  { label: "Solutions", href: "#features" },
  { label: "Live demo", href: "#demo" },
  { label: "Company", href: "#faq" },
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-3 inline-block text-[12px] font-semibold uppercase tracking-[0.12em] text-[#0E7C66] md:mb-3.5 md:text-[13px]">
      {children}
    </span>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      className="relative text-sm font-medium text-[#3D4C5E] transition-colors after:absolute after:-bottom-1 after:left-0 after:h-0.5 after:w-0 after:bg-[#0E7C66] after:transition-[width] after:duration-200 hover:text-[#10243A] hover:after:w-full"
    >
      {children}
    </a>
  );
}

/* Sticky header with the desktop nav and a side-drawer mobile menu. */
function SiteHeader() {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const closeMenu = () => setMenuOpen(false);

  // Escape closes the panel; crossing the `md` breakpoint discards it so the
  // desktop nav never coexists with a stale open panel after a rotation.
  React.useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    const desktop = window.matchMedia("(min-width: 768px)");
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    desktop.addEventListener("change", onChange);
    return () => {
      window.removeEventListener("keydown", onKey);
      desktop.removeEventListener("change", onChange);
    };
  }, [menuOpen]);

  // Prevent background scrolling while the mobile drawer is open.
  React.useEffect(() => {
    if (!menuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [menuOpen]);

  return (
    <>
      <header className="sticky top-0 z-50 border-b border-[#E1E7E4] bg-white/95 px-6! py-0! backdrop-blur lg:px-10!">
        <div className="mx-auto flex h-16 max-w-[1200px] flex-nowrap! items-center justify-between gap-4">
          <a
            href="#hero"
            className={`${sora.className} flex shrink-0 items-center gap-1.5 text-[20px] font-bold tracking-tight text-[#10243A] md:text-[22px]`}
          >
            <Scale className="h-5 w-5 text-[#0E7C66] md:h-6 md:w-6" aria-hidden />
            <span>
              Tara<span className="text-[#0E7C66]">zu</span>
            </span>
          </a>
          <nav className="hidden items-center gap-8 md:flex" aria-label="Primary">
            {NAV_LINKS.map(({ label, href }) => (
              <NavLink key={href} href={href}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2 sm:gap-4 md:gap-5">
            <Link
              href="/login"
              className="hidden text-sm font-medium text-[#3D4C5E] transition-colors hover:text-[#10243A] md:block"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="hidden whitespace-nowrap rounded-md bg-[#0E7C66] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[#0A5F4F] sm:px-6 md:inline-flex md:text-sm"
            >
              Get started
            </Link>
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-expanded={menuOpen}
              aria-controls="landing-mobile-nav"
              aria-label="Open menu"
              className="inline-flex h-10 w-10 items-center justify-center rounded-md text-[#10243A] transition-colors hover:bg-[#F2F6F4] md:hidden"
            >
              <Menu className="h-5 w-5" aria-hidden />
            </button>
          </div>
        </div>
      </header>

      {menuOpen && (
        <>
          <div
            onClick={closeMenu}
            aria-hidden
            className="fixed inset-0 z-40 bg-[#10243A]/50 transition-opacity duration-300 md:hidden"
          />
          <div
            id="landing-mobile-nav"
            className="fixed inset-y-0 left-0 z-50 flex w-[280px] max-w-[80vw] flex-col bg-white shadow-2xl motion-safe:animate-[slideInLeft_0.25s_ease-out] md:hidden"
          >
            <div className="flex h-16 items-center justify-between border-b border-[#E1E7E4] px-6">
              <a
                href="#hero"
                onClick={closeMenu}
                className={`${sora.className} flex items-center gap-1.5 text-[20px] font-bold tracking-tight text-[#10243A]`}
              >
                <Scale className="h-5 w-5 text-[#0E7C66]" aria-hidden />
                <span>
                  Tara<span className="text-[#0E7C66]">zu</span>
                </span>
              </a>
              <button
                type="button"
                onClick={closeMenu}
                aria-label="Close menu"
                className="inline-flex h-10 w-10 items-center justify-center rounded-md text-[#10243A] transition-colors hover:bg-[#F2F6F4]"
              >
                <X className="h-5 w-5" aria-hidden />
              </button>
            </div>
            <nav className="flex flex-1 flex-col px-6 py-6" aria-label="Mobile">
              {NAV_LINKS.map(({ label, href }) => (
                <a
                  key={href}
                  href={href}
                  onClick={closeMenu}
                  className="border-b border-[#E1E7E4] px-3 py-4 text-[17px] font-medium text-[#10243A] transition-colors last:border-b-0 hover:text-[#0E7C66]"
                >
                  {label}
                </a>
              ))}
            </nav>
            <div className="space-y-3 border-t border-[#E1E7E4] p-6">
              <Link
                href="/login"
                onClick={closeMenu}
                className={`${BTN_GHOST} w-full`}
              >
                Sign in
              </Link>
              <Link
                href="/signup"
                onClick={closeMenu}
                className={`${BTN_PRIMARY} w-full`}
              >
                Get started
              </Link>
            </div>
          </div>
        </>
      )}
    </>
  );
}

type LandingIcon = React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

const PILL_TONES = {
  done: "bg-[#E2F3EE] text-[#0A5F4F]",
  run: "bg-[#FFF4E0] text-[#8A5A00]",
  flag: "bg-[#FDE8E8] text-[#B33A3A]",
} as const;

function HeroCardRow({
  icon: Icon,
  label,
  pill,
  tone,
}: {
  icon: LandingIcon;
  label: string;
  pill: string;
  tone: keyof typeof PILL_TONES;
}) {
  return (
    <div className="mb-2.5 flex items-center justify-between gap-3 rounded-[10px] border border-[#E1E7E4] bg-[#F2F6F4] px-3.5 py-3 text-[14px] transition-colors duration-300 hover:border-[#0E7C66] sm:mb-3 sm:px-4.5 sm:py-3.5 sm:text-[15px]">
      <strong className="flex min-w-0 items-center gap-2 font-semibold text-[#10243A]">
        <Icon className="h-4 w-4 shrink-0 text-[#0E7C66]" aria-hidden />
        <span className="truncate">{label}</span>
      </strong>
      <span
        className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1 text-[11px] font-semibold sm:px-3.5 sm:text-[12px] ${PILL_TONES[tone]}`}
      >
        {tone === "done" ? (
          <span className="h-2 w-2 rounded-full bg-current motion-safe:animate-[pulse-dot_1.4s_infinite]" />
        ) : tone === "flag" ? (
          <TriangleAlert className="h-3 w-3" aria-hidden />
        ) : (
          <Clock className="h-3 w-3" aria-hidden />
        )}
        {pill}
      </span>
    </div>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  children,
}: {
  icon: LandingIcon;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-[10px] border border-[#E1E7E4] bg-white p-6 pt-7 transition-[border-color,box-shadow] duration-200 hover:border-[#0E7C66] hover:shadow-[0_8px_24px_-12px_rgba(0,0,0,0.10)] md:p-7 md:pt-8">
      <Icon className="mb-4 h-8 w-8 text-[#0E7C66] md:h-9 md:w-9" aria-hidden />
      <h3 className={`${sora.className} mb-2.5 text-[19px] font-bold text-[#10243A] md:text-xl`}>
        {title}
      </h3>
      <p className="mb-5 flex-1 text-[15px] text-[#3D4C5E] md:text-base">{children}</p>
      <Link
        href="/signup"
        className="inline-flex items-center gap-1.5 self-start border-b-[1.5px] border-transparent text-sm font-semibold text-[#0E7C66] transition-colors hover:border-[#0E7C66]"
      >
        Click to explore
        <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </div>
  );
}

function FaqCard({
  icon: Icon,
  question,
  children,
}: {
  icon: LandingIcon;
  question: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-[#E1E7E4] bg-white px-5 py-5 shadow-[0_2px_8px_rgba(0,0,0,0.02)] transition-[border-color,box-shadow] duration-200 hover:border-[#0E7C66] hover:shadow-[0_6px_20px_rgba(0,0,0,0.05)] sm:px-7 sm:py-6">
      <div className="mb-2.5 flex items-start gap-3 text-[16px] font-semibold text-[#10243A] md:gap-3.5 md:text-[17px]">
        <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[#0E7C66]" aria-hidden />
        {question}
      </div>
      <p className="text-[14px] leading-relaxed opacity-85 md:pl-[34px] md:text-[15px]">
        {children}
      </p>
    </div>
  );
}

/* ============================================================
   Live demo — animated audit pipeline
============================================================ */

const DEMO_STEPS: {
  icon: LandingIcon;
  title: string;
  sub: string;
  progress: number;
  status: string;
  docs: number;
  matches: number;
  flags: number;
}[] = [
  {
    icon: CloudUpload,
    title: "Uploading documents…",
    sub: "3 files received (PDF, PNG, CSV)",
    progress: 20,
    status: "Uploading",
    docs: 3,
    matches: 0,
    flags: 0,
  },
  {
    icon: Eye,
    title: "Extracting with Qwen VL…",
    sub: "Reading invoices & bank statements",
    progress: 45,
    status: "Extracting",
    docs: 3,
    matches: 18,
    flags: 0,
  },
  {
    icon: Code2,
    title: "Matching transactions…",
    sub: "Deterministic reconciliation in progress",
    progress: 70,
    status: "Matching",
    docs: 3,
    matches: 47,
    flags: 1,
  },
  {
    icon: UserCheck,
    title: "Review queue ready",
    sub: "2 items flagged for human decision",
    progress: 90,
    status: "Reviewing",
    docs: 3,
    matches: 62,
    flags: 2,
  },
  {
    icon: FileText,
    title: "✅ Audit complete!",
    sub: "Report ready for download",
    progress: 100,
    status: "Complete",
    docs: 3,
    matches: 72,
    flags: 2,
  },
];

const PIPELINE_NODES: { icon: LandingIcon; label: string; sub: string }[] = [
  { icon: CloudUpload, label: "Upload", sub: "PDF, Images, CSV" },
  { icon: Eye, label: "Extract", sub: "Qwen VL" },
  { icon: Code2, label: "Match", sub: "Deterministic" },
  { icon: UserCheck, label: "Review", sub: "Human decisions" },
  { icon: FileText, label: "Report", sub: "Audit trail" },
];

/* Expected Benford first-digit distribution (%), drawn as a mini chart that
   fills in while the pipeline runs. */
const BENFORD = [30.1, 17.6, 12.5, 9.7, 7.9, 6.7, 5.8, 5.1, 4.6];

/* Per-stage activity feed shown in the progress panel. */
const STEP_EVENTS: string[][] = [
  ["statement_q1.pdf received", "INV-1024.pdf received", "ledger.csv parsed"],
  ["PKR 49,500 · high confidence", "PKR 284,000 · high confidence", "provenance recorded"],
  ["INV-1024 ↔ TXN-8812", "INV-1025 ↔ TXN-8820", "1 discrepancy found"],
  ["Round number flagged", "Duplicate check passed", "Weekend entry flagged"],
  ["PDF report compiled", "Excel annexure ready", "Audit trail sealed"],
];

const SPEEDS = [1, 2, 3];
const SPEED_LABELS = ["1×", "2×", "3×"];
const BASE_DELAY = 2200;

const CTRL_BTN =
  "inline-flex items-center gap-1.5 rounded-full border border-[#E1E7E4] bg-white px-5 py-2 text-[13px] font-medium text-[#3D4C5E] shadow-[0_2px_6px_rgba(0,0,0,0.02)] transition-colors hover:border-[#0E7C66] hover:bg-[#0E7C66] hover:text-white sm:px-6 sm:py-2.5";

/* The pipeline track and its fill share these insets so the fill ends on the
   last node, not the card edge. Below `md` the five nodes are equal flex
   cells, so 10% is exactly the first and last node's centre. */
const TRACK_INSETS =
  "absolute left-[10%] right-[10%] top-[22px] h-[4px] sm:top-[26px] md:left-10 md:right-10 md:top-[34px]";

/* Pointer devices pause the demo on hover; on touch screens `mouseenter` fires
   on tap and `mouseleave` may never come, which would freeze the animation. */
const canHover = () =>
  typeof window !== "undefined" && window.matchMedia("(hover: hover)").matches;

function DemoSection() {
  const [step, setStep] = React.useState(-1);
  const [playing, setPlaying] = React.useState(false);
  const [finished, setFinished] = React.useState(false);
  const [speedIdx, setSpeedIdx] = React.useState(0);

  // Auto-start shortly after load, like the template.
  React.useEffect(() => {
    const t = window.setTimeout(() => {
      setStep((s) => (s < 0 ? 0 : s));
      setPlaying(true);
    }, 1600);
    return () => window.clearTimeout(t);
  }, []);

  // Advance the pipeline while playing; stop after the final step.
  React.useEffect(() => {
    if (!playing) return;
    const interval = window.setInterval(() => {
      setStep((prev) => {
        if (prev < DEMO_STEPS.length - 1) return prev + 1;
        setPlaying(false);
        setFinished(true);
        return prev;
      });
    }, BASE_DELAY / SPEEDS[speedIdx]);
    return () => window.clearInterval(interval);
  }, [playing, speedIdx]);

  const togglePlay = () => {
    if (playing) {
      setPlaying(false);
      return;
    }
    setFinished(false);
    setStep((s) => (s < 0 || s >= DEMO_STEPS.length - 1 ? 0 : s));
    setPlaying(true);
  };

  const reset = () => {
    setPlaying(false);
    setFinished(false);
    setStep(-1);
  };

  const current = step >= 0 ? DEMO_STEPS[step] : null;
  const PanelIcon = finished ? CheckCircle2 : (current?.icon ?? Play);
  const panelGreen = finished || step === DEMO_STEPS.length - 1;
  const fillPct = step < 0 ? 0 : ((step + 1) / DEMO_STEPS.length) * 100;
  const particleVisible = step >= 0 && step < DEMO_STEPS.length - 1;
  const particleLeft =
    step >= 0
      ? `${Math.min(40 + (step + 1) * (20 / DEMO_STEPS.length), 92)}%`
      : "40px";

  return (
    <section
      id="demo"
      className="relative flex scroll-mt-16 items-center overflow-hidden bg-[linear-gradient(165deg,#f6f9f8_0%,#eaf0ee_100%)] px-4 pb-10 pt-8 sm:px-6 md:pb-[60px] md:pt-[50px] lg:min-h-screen lg:px-10"
      onMouseEnter={() => {
        if (canHover() && playing) setPlaying(false);
      }}
      onMouseLeave={() => {
        if (canHover() && !playing && !finished && step < DEMO_STEPS.length - 1) {
          setStep((s) => (s < 0 ? 0 : s));
          setPlaying(true);
        }
      }}
    >
      {/* Soft radial glows over the gradient, as in the template. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_50%,rgba(14,124,102,0.04)_0%,transparent_50%),radial-gradient(circle_at_80%_50%,rgba(14,124,102,0.04)_0%,transparent_50%)]"
      />
      <div className="relative z-[1] mx-auto w-full max-w-[1200px]">
        <div className="mb-6 text-center md:mb-8">
          <span className="mb-3.5 inline-flex items-center gap-1.5 rounded-full bg-[#0E7C66]/10 px-4.5 py-1 text-[12px] font-semibold uppercase tracking-[0.1em] text-[#0E7C66]">
            <CirclePlay className="h-4 w-4" aria-hidden /> Live demo
          </span>
          <h2
            className={`${sora.className} mb-1.5 mt-1 text-[26px] font-bold leading-tight tracking-tight text-[#10243A] sm:text-[28px] md:text-[34px]`}
          >
            See the audit engine in motion
          </h2>
          <p className="mx-auto max-w-[600px] text-[15px] opacity-80 md:text-base">
            Watch how Tarazu processes documents, extracts data, matches transactions, flags
            risks, and generates reports, all in real time.
          </p>
        </div>

        <div className="rounded-2xl border border-white/70 bg-white/80 px-3 pb-4 pt-4 shadow-[0_20px_60px_rgba(0,0,0,0.06)] backdrop-blur-[16px] sm:rounded-3xl sm:px-5 sm:pb-[18px] sm:pt-5 md:px-10 md:pb-7 md:pt-8">
          {/* Pipeline steps — five equal cells on every viewport; the sub-labels
              appear from `sm` and the travelling particle from `md`. */}
          <div className="relative flex items-start justify-between pb-[4px] pt-[4px] md:pb-3 md:pt-2">
            <span aria-hidden className={`${TRACK_INSETS} z-0 rounded-sm bg-[#E1E7E4]`} />
            <span aria-hidden className={`${TRACK_INSETS} z-[1]`}>
              <span
                className="block h-full rounded-sm bg-gradient-to-r from-[#0E7C66] to-[#0A5F4F] shadow-[0_0_20px_rgba(14,124,102,0.25)] transition-[width] duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
                style={{ width: `${fillPct}%` }}
              />
            </span>
            <span
              aria-hidden
              className={`absolute top-[30px] z-[2] hidden h-3 w-3 rounded-full bg-[#0E7C66] shadow-[0_0_20px_rgba(14,124,102,0.25)] transition-[left,opacity] duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)] md:block ${
                particleVisible ? "opacity-100" : "opacity-0"
              }`}
              style={{ left: particleLeft }}
            />
            {PIPELINE_NODES.map(({ icon: Icon, label, sub }, i) => {
              const state = i < step ? "completed" : i === step ? "active" : "pending";
              return (
                <div
                  key={label}
                  className="z-[3] flex min-w-0 flex-1 flex-col items-center gap-1.5 md:gap-0"
                >
                  <div
                    className={`relative flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-full border-2 shadow-[0_4px_12px_rgba(0,0,0,0.04)] transition-all duration-[600ms] ease-[cubic-bezier(0.22,1,0.36,1)] sm:h-[48px] sm:w-[48px] sm:border-[3px] md:mb-2.5 md:h-14 md:w-14 ${
                      state === "active"
                        ? "border-[#0E7C66] bg-[#0E7C66] text-white shadow-[0_0_0_8px_rgba(14,124,102,0.12),0_8px_28px_rgba(14,124,102,0.18)]"
                        : state === "completed"
                          ? "border-[#0E7C66] bg-[#0A5F4F] text-white"
                          : "border-[#E1E7E4] bg-white text-[#3D4C5E]"
                    }`}
                  >
                    <Icon className="h-4 w-4 sm:h-5 sm:w-5 md:h-6 md:w-6" aria-hidden />
                    <span
                      className={`absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white text-white transition-all duration-500 md:-bottom-1 md:-right-1 md:h-5 md:w-5 ${
                        state === "completed"
                          ? "bg-emerald-500"
                          : state === "active"
                            ? "bg-[#0A5F4F] shadow-[0_0_0_4px_rgba(14,124,102,0.15)]"
                            : "bg-[#E1E7E4]"
                      }`}
                    >
                      {state === "completed" ? (
                        <Check className="h-2 w-2" aria-hidden />
                      ) : (
                        <LoaderCircle className="h-2 w-2 motion-safe:animate-spin" aria-hidden />
                      )}
                    </span>
                  </div>
                  <span className="flex flex-col items-center text-center">
                    <span className="text-[11px] font-semibold text-[#10243A] sm:text-[13px] md:text-sm">
                      {label}
                    </span>
                    <span className="hidden text-[10px] opacity-60 sm:block sm:max-w-20 md:text-[11px]">
                      {sub}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>

          {/* Stats bar */}
          <div className="mt-3 flex flex-col gap-3 rounded-xl border border-[#E1E7E4] bg-white/50 px-3 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:rounded-2xl sm:px-5 md:mt-4 md:gap-3.5 md:px-6 md:py-3.5">
            <div className="flex items-center justify-between gap-2 sm:justify-start sm:gap-5">
              {[
                { icon: Receipt, value: current?.docs ?? 0, label: "documents", red: false },
                { icon: ArrowLeftRight, value: current?.matches ?? 0, label: "matched", red: false },
                { icon: Flag, value: current?.flags ?? 0, label: "flagged", red: true },
              ].map(({ icon: Icon, value, label, red }) => (
                <div key={label} className="flex items-center gap-2">
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] text-white ${
                      red ? "bg-[#B33A3A]" : "bg-[#0E7C66]"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" aria-hidden />
                  </span>
                  <span>
                    <span
                      className={`${sora.className} block text-[16px] font-bold tracking-tight tabular-nums md:text-[17px] ${
                        red ? "text-[#B33A3A]" : "text-[#10243A]"
                      }`}
                    >
                      {value}
                    </span>
                    <span className="-mt-0.5 block text-[11px] opacity-70">{label}</span>
                  </span>
                </div>
              ))}
            </div>
            {/* Benford first-digit mini chart — bars rise as the audit advances. */}
            <div className="hidden items-end gap-3 xl:flex" aria-hidden>
              <div className="flex items-end gap-[3px]">
                {BENFORD.map((value, i) => (
                  <span
                    key={i}
                    className="w-[7px] rounded-t-sm bg-[#0E7C66] transition-all duration-700 ease-out"
                    style={{
                      height: `${
                        step < 0
                          ? 3
                          : Math.max(3, (value / BENFORD[0]) * 34 * Math.min(1, (step + 1) / 4))
                      }px`,
                      opacity: 0.35 + 0.65 * (1 - i / 10),
                      transitionDelay: `${i * 50}ms`,
                    }}
                  />
                ))}
              </div>
              <span className="pb-0.5 text-[10px] leading-tight opacity-60">
                Benford
                <br />
                digit check
              </span>
            </div>
            <div className="flex items-center gap-2 self-start rounded-full border border-[#0E7C66]/15 bg-[#0E7C66]/10 py-1 pl-3 pr-4 sm:self-auto">
              <span className="h-2 w-2 rounded-full bg-[#0E7C66] motion-safe:animate-[pulse-dot_1.2s_infinite]" />
              <span className="text-[13px] font-medium text-[#0A5F4F]">
                {current?.status ?? "Ready"}
              </span>
            </div>
          </div>

          {/* Progress panel */}
          <div className="mt-3 flex flex-col gap-3 rounded-[14px] border border-[#E1E7E4] bg-white px-3 py-3 shadow-[0_2px_8px_rgba(0,0,0,0.02)] sm:px-4 md:mt-4 md:flex-row md:flex-wrap md:items-center md:justify-between md:px-5 md:py-3.5">
            <div className="flex items-center gap-3">
              <span
                className={`flex h-[36px] w-[36px] shrink-0 items-center justify-center rounded-xl text-white transition-colors duration-[400ms] md:h-[38px] md:w-[38px] ${
                  panelGreen ? "bg-emerald-500" : "bg-[#0E7C66]"
                }`}
              >
                <PanelIcon className="h-4 w-4" aria-hidden />
              </span>
              <span className="text-[14px] font-medium text-[#10243A]">
                {current?.title ?? "Ready"}
                <small className="mt-px block text-[12px] font-normal text-[#3D4C5E]">
                  {current?.sub ?? "Press Play to start"}
                </small>
              </span>
            </div>
            {/* Live activity chips for the current stage. */}
            <div className="hidden flex-1 flex-wrap items-center justify-center gap-1.5 lg:flex">
              {current &&
                STEP_EVENTS[step].map((event, i) => (
                  <span
                    key={`${step}-${event}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[#E1E7E4] bg-[#F2F6F4] px-2.5 py-1 text-[11px] font-medium text-[#3D4C5E] motion-safe:animate-[fade-slide_0.4s_ease_both]"
                    style={{ animationDelay: `${i * 150}ms` }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-[#0E7C66]" />
                    {event}
                  </span>
                ))}
            </div>
            {/* The bar yields room to the chips on laptops and takes it back
                once the viewport is wide enough for both. */}
            <div className="flex w-full flex-1 items-center gap-3.5 md:max-w-80 lg:max-w-56 xl:max-w-80">
              <span className="h-[5px] flex-1 overflow-hidden rounded-[3px] bg-[#E1E7E4]">
                <span
                  className="block h-full rounded-[3px] bg-gradient-to-r from-[#0E7C66] to-[#0A5F4F] transition-[width] duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
                  style={{ width: `${current?.progress ?? 0}%` }}
                />
              </span>
              <span
                className={`${sora.className} min-w-11 text-right text-[15px] font-bold text-[#0E7C66] tabular-nums`}
              >
                {current?.progress ?? 0}%
              </span>
            </div>
          </div>

          {/* Controls */}
          <div className="mt-4 flex flex-wrap justify-center gap-2 md:mt-[18px] md:gap-3">
            <button type="button" onClick={togglePlay} className={CTRL_BTN}>
              {playing ? (
                <Pause className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Play className="h-3.5 w-3.5" aria-hidden />
              )}
              {playing ? "Pause" : "Play"}
            </button>
            <button type="button" onClick={reset} className={CTRL_BTN}>
              <RotateCw className="h-3.5 w-3.5" aria-hidden /> Reset
            </button>
            <button
              type="button"
              onClick={() => setSpeedIdx((i) => (i + 1) % SPEEDS.length)}
              className={`${CTRL_BTN} px-4 py-2 text-xs sm:px-4 sm:py-2`}
            >
              <Gauge className="h-3.5 w-3.5" aria-hidden /> {SPEED_LABELS[speedIdx]}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================================
   Static section content
============================================================ */

const PROBLEMS: {
  icon: LandingIcon;
  iconClass: string;
  cardClass: string;
  title: string;
  body: string;
}[] = [
  {
    icon: TriangleAlert,
    iconClass: "text-[#B33A3A]",
    cardClass: "border-[#FDE8E8] bg-[#FFF5F5]",
    title: "3 weeks gone",
    body: "Matching one bank statement to invoices? Junior auditors spend days on it. Manually. Prone to error.",
  },
  {
    icon: Flag,
    iconClass: "text-[#8A5A00]",
    cardClass: "border-[#FFF4E0] bg-[#FFFBF0]",
    title: "Blind spots",
    body: "Manual review means you catch round numbers by luck. Duplicates hide. Weekend entries slip through.",
  },
  {
    icon: Lock,
    iconClass: "text-[#0E7C66]",
    cardClass: "border-[#E8F0F8] bg-[#F5F9FF]",
    title: "No trail",
    body: "Who matched what? When? Why? Spreadsheets and chat logs aren't defensible audit evidence.",
  },
];

const SOLUTION_STEPS: { icon: LandingIcon; title: string; body: string }[] = [
  {
    icon: CloudUpload,
    title: "1. You upload",
    body: "Drop in your statements (PDF), invoices (PDF or image), and ledger (Excel or CSV). That's it.",
  },
  {
    icon: Eye,
    title: "2. We read",
    body: "Qwen VL (the vision model) reads PDFs and images. Every extracted number carries provenance and confidence.",
  },
  {
    icon: Code2,
    title: "3. We match",
    body: "Deterministic Python code (not AI) reconciles rows, runs your audit rules, flags anomalies. Every number is traceable.",
  },
  {
    icon: Flag,
    title: "4. We flag",
    body: "Built-in rules catch duplicates, round numbers, weekend entries, and split payments. Each flag links straight to evidence.",
  },
  {
    icon: UserCheck,
    title: "5. You decide",
    body: "Review queue shows matches, flags, and risks. You approve or reject each one. Every decision is logged.",
  },
  {
    icon: Lock,
    title: "6. You sign off",
    body: "Export-ready reports and an immutable audit trail back every judgment. Defend your work in the room or in court.",
  },
];

const WORKFLOW_STEPS: { num: string; title: string; body: string }[] = [
  {
    num: "01",
    title: "Upload & ingest",
    body: "Drop in bank statements (PDF), invoices (PDF/images), and ledgers (Excel/CSV). Tarazu classifies and indexes everything.",
  },
  {
    num: "02",
    title: "Extract & match",
    body: "Qwen VL reads documents; deterministic Python runs reconciliation and math. No black boxes.",
  },
  {
    num: "03",
    title: "Review & approve",
    body: "Every item is presented for approval or rejection. Each action is written to an immutable audit trail.",
  },
];

const FOOTER_GROUPS: { heading: string; links: [string, string][] }[] = [
  {
    heading: "Product",
    links: [
      ["How it works", "#how"],
      ["Platform", "#features"],
      ["Agents", "#agents"],
    ],
  },
  {
    heading: "Company",
    links: [
      ["About", "#"],
      ["Careers", "#"],
      ["Contact", "#"],
    ],
  },
  {
    heading: "Resources",
    links: [
      ["Blog", "#"],
      ["Guides", "#"],
      ["FAQ", "#faq"],
    ],
  },
  {
    heading: "Legal",
    links: [
      ["Privacy", "#"],
      ["Terms", "#"],
      ["Cookies", "#"],
    ],
  },
];

const H2 = `${sora.className} text-[26px] font-bold leading-tight tracking-tight text-[#10243A] sm:text-[30px] md:text-4xl`;

const AGENTS: { phase: string; title: string; body: string }[] = [
  {
    phase: "Prepare",
    title: "Ingestion",
    body: "Client acceptance, document intake, and mapping.",
  },
  {
    phase: "Plan",
    title: "Risk assessment",
    body: "Materiality, risk scoring, and strategy suggestions.",
  },
  {
    phase: "Evaluate",
    title: "Testing & sampling",
    body: "Automated workpapers and evidence collection.",
  },
  {
    phase: "Report",
    title: "Review & sign-off",
    body: "Final report with full audit trail export.",
  },
];

const STATS: { value: string; label: string }[] = [
  { value: "100%", label: "deterministic math" },
  { value: "+40%", label: "faster reviews" },
  { value: "🔒", label: "SOC2 ready" },
];

export default function LandingPage() {
  const { session } = useAuth();
  const router = useRouter();

  // A signed-in auditor came here to work, not to read the pitch.
  React.useEffect(() => {
    if (session) router.replace("/dashboard");
  }, [session, router]);

  return (
    <div
      className={`${plexSans.className} min-h-screen overflow-x-clip bg-white text-[15px] leading-[1.6] text-[#3D4C5E] md:text-[16px] lg:text-[17px] lg:leading-[1.65]`}
    >
      <SiteHeader />

      {/* `p-0!` cancels the app shell's mobile `main` padding (globals.css) so
          the full-bleed section backgrounds reach the viewport edges. */}
      <main className="p-0!">
        <style>{`
          @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(24px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes slideInLeft {
            from { opacity: 0; transform: translateX(-100%); }
            to { opacity: 1; transform: translateX(0); }
          }
        `}</style>
        {/* ===== Hero ===== */}
        <section
          id="hero"
          className="relative flex scroll-mt-16 items-center overflow-hidden bg-[#F8FAF9] px-6 py-12 sm:py-16 lg:min-h-[calc(100vh-140px)] lg:px-10"
        >
          <div className="relative z-[1] mx-auto grid w-full max-w-[1200px] items-center gap-10 lg:grid-cols-2 lg:gap-12">
            <div className="max-w-[640px] lg:max-w-none">
              <Eyebrow>
                <Bot className="mr-1.5 inline h-4 w-4 align-[-2px]" aria-hidden />
                AI SUGGESTS · HUMAN DECIDES
              </Eyebrow>
              <h1
                className={`${sora.className} mb-5 text-[32px] font-bold leading-[1.15] tracking-tight text-[#10243A] sm:text-[40px] md:mb-6 md:text-5xl`}
              >
                Audit intelligence{" "}
                <span className="text-[#0E7C66] underline decoration-[#0E7C66] decoration-4 underline-offset-8">
                  that scales
                </span>{" "}
                with your firm
              </h1>
              <p className="mb-7 max-w-[55ch] text-[17px] text-[#3D4C5E] md:mb-8 md:text-lg">
                Tarazu (تارازو) ingests bank statements, invoices, and ledgers. It matches, flags,
                and presents a clean review queue with an immutable audit trail.
              </p>
              <div className="mb-7 flex flex-col gap-3 sm:flex-row sm:gap-4 md:mb-8">
                <Link href="/signup" className={BTN_PRIMARY}>
                  Book a demo
                </Link>
                <a href="#demo" className={BTN_GHOST}>
                  See how it works
                </a>
              </div>
              <p className="text-[13px] text-[#6B7A8A] md:text-sm">
                SOC 2 ready · Deterministic math · Multi-tenant
              </p>
            </div>
            <div
              role="group"
              aria-label="Product preview"
              className="w-full max-w-[600px] rounded-2xl border border-[#E1E7E4] bg-white p-5 shadow-md sm:p-8 lg:max-w-none"
            >
              <HeroCardRow icon={FileText} label="Invoice #INV-1024" pill="Extracted" tone="done" />
              <HeroCardRow icon={Landmark} label="Bank statement Q1" pill="Matched" tone="done" />
              <HeroCardRow icon={Table} label="Ledger (CSV)" pill="Flagged risk" tone="flag" />
              <HeroCardRow icon={Users} label="Human review queue" pill="2 pending" tone="run" />
            </div>
          </div>
        </section>

        {/* ===== Problem Section ===== */}
        <section className="border-t border-[#E1E7E4] px-6 py-14 md:py-20 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <h2 className={`${H2} mb-8 text-center md:mb-12`}>
              The audit bottleneck nobody talks about
            </h2>
            <div className="grid gap-5 md:grid-cols-3 md:gap-6 lg:gap-8">
              {PROBLEMS.map(({ icon: Icon, iconClass, cardClass, title, body }) => (
                <div key={title} className={`rounded-2xl border p-6 lg:p-8 ${cardClass}`}>
                  <Icon className={`mb-4 h-8 w-8 ${iconClass}`} aria-hidden />
                  <h3
                    className={`${sora.className} mb-2 text-[19px] font-bold text-[#10243A] md:text-xl`}
                  >
                    {title}
                  </h3>
                  <p className="text-[#3D4C5E]">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== Solution Section ===== */}
        <section className="bg-[#f8fafc] px-6 py-14 md:py-20 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <h2 className={`${H2} mb-8 text-center md:mb-12`}>What we actually do</h2>
            <div className="grid gap-8 sm:grid-cols-2 md:grid-cols-3 sm:gap-x-8 sm:gap-y-10 lg:gap-10">
              {SOLUTION_STEPS.map(({ icon: Icon, title, body }, index) => (
                <div
                  key={title}
                  className="group rounded-2xl p-5 opacity-0 transition-all duration-300 hover:-translate-y-1 hover:bg-white hover:shadow-lg motion-safe:animate-[fadeInUp_0.6s_ease-out_forwards]"
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-[#0E7C66] text-white transition-transform duration-300 group-hover:scale-110">
                    <Icon className="h-6 w-6" aria-hidden />
                  </div>
                  <h3
                    className={`${sora.className} mb-2 text-[21px] font-bold text-[#10243A] md:text-2xl`}
                  >
                    {title}
                  </h3>
                  <p className="text-[#3D4C5E]">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== Trust bar ===== */}
        <div className="border-y border-[#E1E7E4] px-6 py-8 md:py-10 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <p className="mb-5 text-center text-[12px] uppercase tracking-[0.1em] text-[#7B8794] md:mb-6 md:text-[13px]">
              Trusted by audit and assurance teams at
            </p>
            <div
              className={`${sora.className} flex flex-wrap justify-center gap-x-8 gap-y-3 text-[16px] font-semibold text-[#9AA7B2] sm:gap-x-10 md:gap-x-14 md:gap-y-4 md:text-[19px]`}
            >
              <span>Meridian LLP</span>
              <span>Northgate</span>
              <span>Calder &amp; Co</span>
              <span>BlueRock</span>
              <span>Averys</span>
            </div>
          </div>
        </div>

        {/* ===== How it works ===== */}
        <section id="how" className="scroll-mt-16 px-6 py-16 md:py-24 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <Eyebrow>Workflow</Eyebrow>
            <h2 className={H2}>AI suggests, human decides. End to end.</h2>
            <div className="mt-10 grid gap-8 md:mt-14 md:grid-cols-3 md:gap-6 lg:gap-10">
              {WORKFLOW_STEPS.map(({ num, title, body }) => (
                <div key={num} className="border-l-[3px] border-[#0E7C66] pl-5 md:pl-6">
                  <span className={`${sora.className} text-[15px] font-bold text-[#0E7C66]`}>
                    {num}
                  </span>
                  <h3
                    className={`${sora.className} my-2.5 text-[19px] font-bold text-[#10243A] md:text-[21px]`}
                  >
                    {title}
                  </h3>
                  <p>{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== Features ===== */}
        <section id="features" className="scroll-mt-16 bg-white px-6 py-16 md:py-24 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <div className="mb-10 text-center md:mb-16">
              <Eyebrow>What makes it different</Eyebrow>
              <h2 className={`${H2} mx-auto max-w-2xl`}>Built by auditors, for auditors</h2>
            </div>
            <div className="grid gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-3 lg:gap-8">
              <FeatureCard icon={Eye} title="AI vision, not guesses">
                Qwen reads documents and admits when it&apos;s uncertain. Every extracted number
                carries a confidence score and source location.
              </FeatureCard>
              <FeatureCard icon={Code2} title="Deterministic matching">
                No black boxes. Reconciliation logic is pure Python. You can audit the audit logic.
                Every match is traceable.
              </FeatureCard>
              <FeatureCard icon={Flag} title="Rules that flag what needs attention">
                Duplicates, round numbers, weekend entries, near-limit amounts, and split
                payments, each linked to its evidence. Tarazu flags; you decide.
              </FeatureCard>
              <FeatureCard icon={UserCheck} title="You stay in the loop">
                The system never decides alone. Every flagged or matched item lands in your review
                queue. You approve or reject it.
              </FeatureCard>
              <FeatureCard icon={Database} title="Immutable audit trail">
                Every decision, every timestamp, every override. Written once, tamper-proof. Defend
                your audit in the room, in court.
              </FeatureCard>
              <FeatureCard icon={Building2} title="Built for teams">
                Organizations, members, role-based access, API keys. Invite partners and junior
                staff. Everyone sees what they need to.
              </FeatureCard>
            </div>
          </div>
        </section>

        {/* ===== Live demo pipeline ===== */}
        <DemoSection />

        {/* ===== Agent suites ===== */}
        <section id="agents" className="scroll-mt-16 bg-white px-6 py-14 md:py-20 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <Eyebrow>Agent suites</Eyebrow>
            <h2 className={`${H2} mb-8 md:mb-12`}>Purpose-built agents for every phase</h2>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {AGENTS.map(({ phase, title, body }) => (
                <div
                  key={title}
                  className="rounded-[10px] border border-[#E1E7E4] bg-white p-6 text-center transition-all duration-200 hover:-translate-y-1 hover:border-[#0E7C66] hover:shadow-md"
                >
                  <span className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.08em] text-[#0E7C66]">
                    {phase}
                  </span>
                  <h3 className={`${sora.className} mb-1 text-[20px] font-bold text-[#10243A]`}>
                    {title}
                  </h3>
                  <p className="text-[14px] text-[#6B7A8A]">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== Stats ===== */}
        <section className="bg-[#10243A] px-6 py-14 md:py-20 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <div className="grid gap-10 text-center sm:grid-cols-3 md:gap-12">
              {STATS.map(({ value, label }) => (
                <div key={label}>
                  <b
                    className={`${sora.className} block text-[46px] leading-none tracking-tight text-[#7ED9C3]`}
                  >
                    {value}
                  </b>
                  <span className="mt-2 block text-[15px] text-[#B9C6D2]">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== FAQ ===== */}
        <section id="faq" className="scroll-mt-16 px-6 py-14 md:py-20 lg:px-10">
          <div className="mx-auto max-w-[1020px]">
            <div className="mb-8 text-center md:mb-12">
              <Eyebrow>FAQ</Eyebrow>
              <h2 className={`${H2} mt-1`}>Questions we actually get asked</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2 md:gap-6">
              <FaqCard icon={Rocket} question="How long before we see ROI?">
                Most firms save 15–20 hours per engagement in the first month. At a junior
                auditor&apos;s cost, that&apos;s 3–5K per case. Onboarding is usually two weeks.
              </FaqCard>
              <FaqCard icon={Eye} question="Does Tarazu read scanned invoices?">
                Yes. Qwen handles PDFs, JPGs, and PNGs. Handwritten notes are harder, but we keep
                improving. Every extraction shows its confidence score.
              </FaqCard>
              <FaqCard icon={Lock} question="Is our client data safe?">
                Encrypted at rest and in transit. SOC 2 Type II ready. Role-based access, audit
                logs, and we never use client data for training.
              </FaqCard>
              <FaqCard icon={CheckCircle2} question="Can we customize the rules?">
                Absolutely. Define your own flags (round numbers, duplicates, weekend entries,
                near-limit amounts). Rules are code you can review.
              </FaqCard>
              <FaqCard icon={Code2} question="How does this fit into our audit process?">
                It replaces the grunt work (reconciliation, matching). You still own the judgment
                calls, risk assessment, and sign-off. The trail backs you up.
              </FaqCard>
              <FaqCard icon={Users} question="What if we have legacy systems?">
                If you can export to CSV or PDF, Tarazu can read it. We also offer an API if you
                want to pipe data in programmatically.
              </FaqCard>
            </div>
          </div>
        </section>

        {/* ===== CTA ===== */}
        <section
          id="cta"
          className="scroll-mt-16 bg-white px-6 py-16 md:py-24 lg:px-10"
        >
          <div className="mx-auto max-w-[800px] text-center">
            <h2
              className={`${sora.className} mb-4 text-[28px] font-bold leading-tight tracking-tight text-[#10243A] sm:text-[32px] md:text-[42px]`}
            >
              See your own engagement in Tarazu
            </h2>
            <p className="mb-8 text-[16px] text-[#3D4C5E] md:text-lg">
              Bring one real (anonymised) engagement to the demo, and we&apos;ll show you exactly what
              it automates.
            </p>
            <Link href="/signup" className={BTN_PRIMARY}>
              Book a demo
            </Link>
          </div>
        </section>
      </main>

      {/* ===== Footer ===== */}
      <footer className="bg-[#10243A] px-6 pb-8 pt-12 text-[14px] text-[#B9C6D2] md:pt-16 md:text-[15px] lg:px-10">
        <div className="mx-auto max-w-[1200px]">
          <div className="mb-10 flex flex-col gap-10 md:mb-12 lg:grid lg:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
            <div>
              <a
                href="#hero"
                className={`${sora.className} flex items-center gap-1.5 text-[22px] font-bold tracking-tight text-white`}
              >
                <Scale className="h-6 w-6 text-[#0E7C66]" aria-hidden />
                <span>
                  Tara<span className="text-[#0E7C66]">zu</span>
                </span>
              </a>
              <p className="mt-3.5 max-w-[32ch]">
                AI-powered audit automation for modern assurance teams.
              </p>
            </div>
            {/* Two link columns on phones, four from `sm`; at `lg` the wrapper
                dissolves (`contents`) so the groups sit in the outer grid. */}
            <div className="grid grid-cols-2 gap-8 sm:grid-cols-4 lg:contents">
              {FOOTER_GROUPS.map(({ heading, links }) => (
                <div key={heading}>
                  <h4 className="mb-4 text-[13px] font-semibold uppercase tracking-[0.08em] text-white md:text-sm">
                    {heading}
                  </h4>
                  <ul className="space-y-2.5">
                    {links.map(([label, href]) => (
                      <li key={label}>
                        <a href={href} className="transition-colors hover:text-white">
                          {label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
          <div className="flex flex-col items-center gap-2 border-t border-[#24374D] pt-6 text-center text-[13px] sm:flex-row sm:justify-between sm:text-left md:text-[13.5px]">
            <span>© 2026 Tarazu. All rights reserved.</span>
            <span>
              <a href="#" className="transition-colors hover:text-white">
                Privacy
              </a>{" "}
              ·{" "}
              <a href="#" className="transition-colors hover:text-white">
                Terms
              </a>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
