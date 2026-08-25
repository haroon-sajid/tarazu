"use client";

/**
 * The public landing page. Signed-in visitors go straight to the dashboard;
 * everyone else gets the pitch, following the marketing template in
 * <repo>/landing.html: gradient hero with a live status card, trust bar,
 * workflow, feature grid, animated "Live demo" pipeline, agent suites,
 * stats, testimonial, FAQ card grid, and CTA.
 *
 * Everything here is static copy and CSS. The "product" visuals are built
 * from divs, not screenshots, so they never go stale. Every demo CTA from
 * the template is a "Get started" link into /signup here.
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
  Pause,
  Play,
  Plug,
  Receipt,
  Rocket,
  RotateCw,
  Scale,
  ShieldCheck,
  Table,
  TriangleAlert,
  UserCheck,
  Users,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

const sora = Sora({ subsets: ["latin"], weight: ["600", "700"] });
const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"] });

const BTN_PRIMARY =
  "inline-block rounded-[10px] bg-[#0E7C66] px-8 py-3.5 text-base font-semibold text-white transition hover:-translate-y-0.5 hover:bg-[#0A5F4F] hover:shadow-[0_8px_20px_rgba(14,124,102,0.25)]";
const BTN_GHOST =
  "inline-block rounded-[10px] border-[1.5px] border-[#E1E7E4] bg-white px-8 py-3.5 text-base font-semibold text-[#10243A] transition hover:-translate-y-0.5 hover:border-[#10243A] hover:shadow-[0_8px_20px_rgba(0,0,0,0.04)]";

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-3.5 inline-block text-[13px] font-semibold uppercase tracking-[0.12em] text-[#0E7C66]">
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
    <div className="mb-3 flex items-center justify-between rounded-[10px] border border-[#E1E7E4] bg-[#F2F6F4] px-4.5 py-3.5 text-[15px] transition-colors duration-300 hover:border-[#0E7C66]">
      <strong className="flex items-center gap-2 font-semibold text-[#10243A]">
        <Icon className="h-4 w-4 text-[#0E7C66]" aria-hidden />
        {label}
      </strong>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1 text-xs font-semibold ${PILL_TONES[tone]}`}
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
    <div className="group flex flex-col rounded-[10px] border border-[#E1E7E4] bg-white p-7 pt-8 transition-all duration-300 hover:-translate-y-1.5 hover:border-[#0E7C66] hover:shadow-[0_16px_32px_-12px_rgba(0,0,0,0.12)]">
      <Icon
        className="mb-4 h-9 w-9 text-[#0E7C66] transition-transform duration-300 group-hover:scale-105"
        aria-hidden
      />
      <h3 className={`${sora.className} mb-2.5 text-xl font-bold text-[#10243A]`}>{title}</h3>
      <p className="mb-5 flex-1 text-base text-[#3D4C5E]">{children}</p>
      <Link
        href="/signup"
        className="group/link inline-flex items-center gap-1.5 self-start border-b-[1.5px] border-transparent text-sm font-semibold text-[#0E7C66] transition-colors hover:border-[#0E7C66]"
      >
        Click to explore
        <ArrowRight
          className="h-3.5 w-3.5 transition-transform group-hover/link:translate-x-1"
          aria-hidden
        />
      </Link>
    </div>
  );
}

function AgentCard({
  phase,
  title,
  children,
}: {
  phase: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[10px] border border-[#E1E7E4] bg-white p-6 text-center transition-all hover:-translate-y-1 hover:border-[#0E7C66] hover:shadow-[0_6px_24px_rgba(16,36,58,0.08)]">
      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[#0E7C66]">
        {phase}
      </span>
      <h4 className={`${sora.className} mb-1 mt-2 text-xl font-semibold text-[#10243A]`}>{title}</h4>
      <p className="text-sm text-[#6B7A8A]">{children}</p>
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
    <div className="rounded-2xl border border-[#E1E7E4] bg-white px-7 py-6 shadow-[0_2px_8px_rgba(0,0,0,0.02)] transition-all hover:-translate-y-[3px] hover:border-[#0E7C66] hover:shadow-[0_8px_28px_rgba(0,0,0,0.06)]">
      <div className="mb-2.5 flex items-start gap-3.5 text-[17px] font-semibold text-[#10243A]">
        <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[#0E7C66]" aria-hidden />
        {question}
      </div>
      <p className="text-[15px] leading-relaxed opacity-85 md:pl-[34px]">{children}</p>
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
  "inline-flex items-center gap-1.5 rounded-full border border-[#E1E7E4] bg-white px-6 py-2.5 text-[13px] font-medium text-[#3D4C5E] shadow-[0_2px_6px_rgba(0,0,0,0.02)] transition-all hover:-translate-y-0.5 hover:border-[#0E7C66] hover:bg-[#0E7C66] hover:text-white hover:shadow-[0_8px_24px_rgba(14,124,102,0.20)] active:translate-y-0";

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
      className="relative flex scroll-mt-16 items-center overflow-hidden bg-[linear-gradient(165deg,#f6f9f8_0%,#eaf0ee_100%)] px-6 pb-10 pt-[30px] md:min-h-screen md:pb-[60px] md:pt-[50px] lg:px-10"
      onMouseEnter={() => {
        if (playing) setPlaying(false);
      }}
      onMouseLeave={() => {
        if (!playing && !finished && step < DEMO_STEPS.length - 1) {
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
        <div className="mb-8 text-center">
          <span className="mb-3.5 inline-flex items-center gap-1.5 rounded-full bg-[#0E7C66]/10 px-4.5 py-1 text-xs font-semibold uppercase tracking-[0.1em] text-[#0E7C66]">
            <CirclePlay className="h-4 w-4" aria-hidden /> Live demo
          </span>
          <h2
            className={`${sora.className} mb-1.5 mt-1 text-[28px] font-bold leading-tight tracking-tight text-[#10243A] md:text-[34px]`}
          >
            See the audit engine in motion
          </h2>
          <p className="mx-auto max-w-[600px] text-base opacity-80">
            Watch how Tarazu processes documents, extracts data, matches transactions, flags
            risks, and generates reports — all in real time.
          </p>
        </div>

        <div className="rounded-3xl border border-white/70 bg-white/80 px-4 pb-[18px] pt-5 shadow-[0_20px_60px_rgba(0,0,0,0.06)] backdrop-blur-[16px] transition-shadow duration-[400ms] hover:shadow-[0_28px_72px_rgba(0,0,0,0.08)] md:px-10 md:pb-7 md:pt-8">
          {/* Pipeline steps */}
          <div className="relative flex flex-col items-start gap-3 py-1 md:flex-row md:items-start md:justify-between md:gap-0 md:pb-3 md:pt-2">
            <span
              aria-hidden
              className="absolute left-10 right-10 top-11 z-0 hidden h-1 rounded-sm bg-[#E1E7E4] md:block"
            />
            {/* The fill lives inside the same 40px insets as the track, so at
                100% it stops at the track's end instead of the card edge. */}
            <span aria-hidden className="absolute left-10 right-10 top-11 z-[1] hidden h-1 md:block">
              <span
                className="block h-full rounded-sm bg-gradient-to-r from-[#0E7C66] to-[#0A5F4F] shadow-[0_0_20px_rgba(14,124,102,0.25)] transition-[width] duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
                style={{ width: `${fillPct}%` }}
              />
            </span>
            <span
              aria-hidden
              className={`absolute top-10 z-[2] hidden h-3 w-3 rounded-full bg-[#0E7C66] shadow-[0_0_20px_rgba(14,124,102,0.25)] transition-[left,opacity] duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)] md:block ${
                particleVisible ? "opacity-100" : "opacity-0"
              }`}
              style={{ left: particleLeft }}
            />
            {PIPELINE_NODES.map(({ icon: Icon, label, sub }, i) => {
              const state = i < step ? "completed" : i === step ? "active" : "pending";
              return (
                <div
                  key={label}
                  className="z-[3] flex w-full flex-row items-center gap-3.5 transition-transform duration-300 hover:-translate-y-[3px] md:w-auto md:flex-1 md:flex-col md:gap-0"
                >
                  <div
                    className={`relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-[3px] shadow-[0_4px_12px_rgba(0,0,0,0.04)] transition-all duration-[600ms] ease-[cubic-bezier(0.22,1,0.36,1)] md:mb-2.5 md:h-14 md:w-14 ${
                      state === "active"
                        ? "scale-[1.04] border-[#0E7C66] bg-[#0E7C66] text-white shadow-[0_0_0_8px_rgba(14,124,102,0.12),0_8px_28px_rgba(14,124,102,0.18)]"
                        : state === "completed"
                          ? "border-[#0E7C66] bg-[#0A5F4F] text-white"
                          : "border-[#E1E7E4] bg-white text-[#3D4C5E]"
                    }`}
                  >
                    <Icon className="h-[18px] w-[18px] md:h-6 md:w-6" aria-hidden />
                    <span
                      className={`absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full border-2 border-white text-white transition-all duration-500 ${
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
                  <span className="flex flex-col md:items-center">
                    <span className="text-[13px] font-semibold text-[#10243A] md:text-sm">
                      {label}
                    </span>
                    <span className="text-[11px] opacity-60 md:max-w-20 md:text-center">{sub}</span>
                  </span>
                </div>
              );
            })}
          </div>

          {/* Stats bar */}
          <div className="mt-4 flex flex-col gap-2.5 rounded-2xl border border-[#E1E7E4] bg-white/50 px-4 py-3 md:flex-row md:flex-wrap md:items-center md:justify-between md:gap-3.5 md:px-6 md:py-3.5">
            <div className="flex flex-wrap items-center gap-3 md:gap-5">
              {[
                { icon: Receipt, value: current?.docs ?? 0, label: "documents", red: false },
                { icon: ArrowLeftRight, value: current?.matches ?? 0, label: "matched", red: false },
                { icon: Flag, value: current?.flags ?? 0, label: "flagged", red: true },
              ].map(({ icon: Icon, value, label, red }) => (
                <div key={label} className="flex items-center gap-2">
                  <span
                    className={`flex h-8 w-8 items-center justify-center rounded-[10px] text-white ${
                      red ? "bg-[#B33A3A]" : "bg-[#0E7C66]"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" aria-hidden />
                  </span>
                  <span>
                    <span
                      className={`${sora.className} block text-[17px] font-bold tracking-tight tabular-nums ${
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
            <div className="flex items-center gap-2 self-start rounded-full border border-[#0E7C66]/15 bg-[#0E7C66]/10 py-1 pl-3 pr-4 md:self-auto">
              <span className="h-2 w-2 rounded-full bg-[#0E7C66] motion-safe:animate-[pulse-dot_1.2s_infinite]" />
              <span className="text-[13px] font-medium text-[#0A5F4F]">
                {current?.status ?? "Ready"}
              </span>
            </div>
          </div>

          {/* Progress panel */}
          <div className="mt-4 flex flex-col gap-2.5 rounded-[14px] border border-[#E1E7E4] bg-white px-4 py-3 shadow-[0_2px_8px_rgba(0,0,0,0.02)] md:flex-row md:flex-wrap md:items-center md:justify-between md:gap-3 md:px-5 md:py-3.5">
            <div className="flex items-center gap-3">
              <span
                className={`flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl text-white transition-colors duration-[400ms] ${
                  panelGreen ? "bg-emerald-500" : "bg-[#0E7C66]"
                }`}
              >
                <PanelIcon className="h-4 w-4" aria-hidden />
              </span>
              <span className="text-sm font-medium text-[#10243A]">
                {current?.title ?? "Ready"}
                <small className="mt-px block text-xs font-normal text-[#3D4C5E]">
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
            <div className="flex w-full flex-1 items-center gap-3.5 md:max-w-80">
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
          <div className="mt-[18px] flex flex-wrap justify-center gap-2 md:gap-3">
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
              className={`${CTRL_BTN} px-4 py-2 text-xs`}
            >
              <Gauge className="h-3.5 w-3.5" aria-hidden /> {SPEED_LABELS[speedIdx]}
            </button>
          </div>
        </div>
      </div>
    </section>
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
    <div
      className={`${plexSans.className} min-h-screen bg-white text-[17px] leading-[1.65] text-[#3D4C5E]`}
    >
      {/* ===== Header ===== */}
      <header className="sticky top-0 z-50 border-b border-[#E1E7E4] bg-white/95 px-6 backdrop-blur lg:px-10">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between">
          <a
            href="#hero"
            className={`${sora.className} flex items-center gap-1.5 text-[22px] font-bold tracking-tight text-[#10243A]`}
          >
            <Scale className="h-6 w-6 text-[#0E7C66]" aria-hidden />
            <span>
              Tara<span className="text-[#0E7C66]">zu</span>
            </span>
          </a>
          <nav className="hidden items-center gap-8 md:flex">
            <NavLink href="#how">Platform</NavLink>
            <NavLink href="#features">Solutions</NavLink>
            <NavLink href="#demo">Live demo</NavLink>
            <NavLink href="#faq">Company</NavLink>
          </nav>
          <div className="flex items-center gap-5">
            <Link
              href="/login"
              className="hidden text-sm font-medium text-[#3D4C5E] transition-colors hover:text-[#10243A] sm:block"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-[#0E7C66] px-6 py-2 text-sm font-semibold text-white transition hover:-translate-y-px hover:bg-[#0A5F4F]"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main>
        {/* ===== Hero ===== */}
        <section
          id="hero"
          className="relative flex scroll-mt-16 items-center overflow-hidden bg-[linear-gradient(165deg,#f9fbfa_0%,#f0f5f3_100%)] px-6 pb-[70px] pt-20 md:min-h-[calc(100vh-140px)] lg:px-10"
        >
          <div className="relative z-[1] mx-auto grid w-full max-w-[1200px] items-center gap-16 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <Eyebrow>
                <Bot className="mr-1.5 inline h-4 w-4 align-[-2px]" aria-hidden />
                AI suggests · human decides
              </Eyebrow>
              <h1
                className={`${sora.className} mb-5 text-[30px] font-bold leading-[1.12] tracking-tight text-[#10243A] sm:text-4xl md:text-[52px]`}
              >
                Audit intelligence{" "}
                <em className="border-b-4 border-[#0E7C66] not-italic text-[#0E7C66]">
                  that scales
                </em>{" "}
                with your firm
              </h1>
              <p className="mb-8 max-w-[52ch] text-[19px]">
                Tarazu (ترازو) ingests bank statements, invoices, and ledgers — matches, flags,
                and presents a clean review queue with an immutable audit trail.
              </p>
              <div className="mb-4 flex flex-wrap gap-3.5">
                <Link href="/signup" className={BTN_PRIMARY}>
                  Get started
                </Link>
                <a href="#demo" className={BTN_GHOST}>
                  See how it works
                </a>
              </div>
              <p className="text-sm text-[#6B7A8A]">
                SOC 2 ready · Deterministic math · Multi-tenant
              </p>
            </div>
            <div
              aria-label="Product preview"
              className="rounded-2xl border border-[#E1E7E4] bg-white p-7 shadow-[0_6px_24px_rgba(16,36,58,0.08)] transition-[box-shadow,transform] duration-300 hover:-translate-y-1 hover:shadow-[0_20px_48px_-12px_rgba(0,0,0,0.16)]"
            >
              <HeroCardRow icon={FileText} label="Invoice #INV-1024" pill="Extracted" tone="done" />
              <HeroCardRow icon={Landmark} label="Bank statement Q1" pill="Matched" tone="done" />
              <HeroCardRow icon={Table} label="Ledger (CSV)" pill="Flagged risk" tone="flag" />
              <HeroCardRow icon={Users} label="Human review queue" pill="2 pending" tone="run" />
            </div>
          </div>
        </section>

        {/* ===== Trust bar ===== */}
        <div className="border-y border-[#E1E7E4] px-6 py-10 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <p className="mb-6 text-center text-[13px] uppercase tracking-[0.1em] text-[#7B8794]">
              Trusted by audit and assurance teams at
            </p>
            <div
              className={`${sora.className} flex flex-wrap justify-center gap-x-14 gap-y-4 text-[19px] font-semibold text-[#9AA7B2]`}
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
        <section id="how" className="scroll-mt-16 px-6 py-24 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <Eyebrow>Workflow</Eyebrow>
            <h2
              className={`${sora.className} text-3xl font-bold leading-tight tracking-tight text-[#10243A] md:text-4xl`}
            >
              AI suggests, human decides — end to end
            </h2>
            <div className="mt-14 grid gap-10 md:grid-cols-3">
              {[
                {
                  num: "01",
                  title: "Upload & ingest",
                  body: "Drop in bank statements (PDF), invoices (PDF/images), and ledgers (Excel/CSV). Tarazu classifies and indexes everything.",
                },
                {
                  num: "02",
                  title: "Extract & match",
                  body: "Qwen VL reads documents, deterministic Python runs reconciliation and math — no black boxes.",
                },
                {
                  num: "03",
                  title: "Review & approve",
                  body: "Every item is presented for approval or rejection. Each action is written to an immutable audit trail.",
                },
              ].map(({ num, title, body }) => (
                <div key={num} className="border-l-[3px] border-[#0E7C66] pl-6">
                  <span className={`${sora.className} text-[15px] font-bold text-[#0E7C66]`}>
                    {num}
                  </span>
                  <h3 className={`${sora.className} my-2.5 text-[21px] font-bold text-[#10243A]`}>
                    {title}
                  </h3>
                  <p>{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== Features ===== */}
        <section id="features" className="scroll-mt-16 px-6 py-24 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <div className="mb-12 flex flex-wrap items-end justify-between gap-3">
              <div>
                <Eyebrow>Platform</Eyebrow>
                <h2
                  className={`${sora.className} max-w-[24ch] text-3xl font-bold leading-tight tracking-tight text-[#10243A] md:text-4xl`}
                >
                  Built for audit firms, from intake to report
                </h2>
              </div>
              <span className="whitespace-nowrap rounded-full bg-[#F2F6F4] px-4 py-1 text-sm font-semibold tracking-wide text-[#0E7C66]">
                3 × 2
              </span>
            </div>
            <div className="grid gap-7 md:grid-cols-2 lg:grid-cols-3">
              <FeatureCard icon={Eye} title="AI vision extraction">
                Qwen VL reads PDFs, images, and invoices. Extracted data includes provenance and
                confidence scores.
              </FeatureCard>
              <FeatureCard icon={Code2} title="Deterministic matching">
                All reconciliation and math run in Python — every number traceable to source rows
                and audit rules.
              </FeatureCard>
              <FeatureCard icon={Flag} title="Risk rules engine">
                Flag fraud, duplicates, and anomalies with custom rules. Each flag links to
                evidence and supports override.
              </FeatureCard>
              <FeatureCard icon={UserCheck} title="Human-in-the-loop">
                Approve or reject every item. The system never decides alone — you stay in
                control.
              </FeatureCard>
              <FeatureCard icon={Database} title="Immutable audit trail">
                Every decision, note, and change is written once — tamper-proof, timestamped, and
                searchable.
              </FeatureCard>
              <FeatureCard icon={Building2} title="Multi-tenant &amp; API">
                Organizations, members, and scoped API keys. Integrate with n8n, Zapier, or your
                own automation.
              </FeatureCard>
            </div>
          </div>
        </section>

        {/* ===== Live demo pipeline ===== */}
        <DemoSection />

        {/* ===== Agent suites ===== */}
        <section id="agents" className="scroll-mt-16 bg-white px-6 py-24 lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <Eyebrow>Agent suites</Eyebrow>
            <h2
              className={`${sora.className} text-3xl font-bold leading-tight tracking-tight text-[#10243A] md:text-4xl`}
            >
              Purpose-built agents for every phase
            </h2>
            <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <AgentCard phase="Prepare" title="Ingestion">
                Client acceptance, document intake, and mapping.
              </AgentCard>
              <AgentCard phase="Plan" title="Risk assessment">
                Materiality, risk scoring, and strategy suggestions.
              </AgentCard>
              <AgentCard phase="Evaluate" title="Testing &amp; sampling">
                Automated workpapers and evidence collection.
              </AgentCard>
              <AgentCard phase="Report" title="Review &amp; sign-off">
                Final report with full audit trail export.
              </AgentCard>
            </div>
          </div>
        </section>

        {/* ===== Stats ===== */}
        <section className="bg-[#10243A] px-6 py-24 text-white lg:px-10">
          <div className="mx-auto grid max-w-[1200px] gap-10 text-center md:grid-cols-3">
            {[
              ["100%", "deterministic math"],
              ["+40%", "faster reviews"],
              ["🔒", "SOC2 ready"],
            ].map(([value, label]) => (
              <div key={label}>
                <b
                  className={`${sora.className} block text-[46px] font-bold tracking-tight text-[#7ED9C3]`}
                >
                  {value}
                </b>
                <span className="text-[15px] text-[#B9C6D2]">{label}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ===== Testimonial ===== */}
        <section className="px-6 py-24 lg:px-10">
          <div className="mx-auto max-w-3xl text-center">
            <blockquote
              className={`${sora.className} mb-6 text-[26px] font-semibold leading-[1.4] text-[#10243A]`}
            >
              &ldquo;Tarazu turned our chaotic document review into a streamlined, defensible
              process. Our partners trust the trail.&rdquo;
            </blockquote>
            <cite className="text-[15px] not-italic text-[#6B7A8A]">
              <b className="font-semibold text-[#10243A]">Placeholder Name</b> — Audit Partner,
              Example Firm
            </cite>
          </div>
        </section>

        {/* ===== FAQ ===== */}
        <section id="faq" className="scroll-mt-16 bg-white px-6 py-20 lg:px-10">
          <div className="mx-auto max-w-[1020px]">
            <div className="mb-12 text-center">
              <Eyebrow>FAQ</Eyebrow>
              <h2
                className={`${sora.className} mt-1 text-3xl font-bold leading-tight tracking-tight text-[#10243A] md:text-4xl`}
              >
                Frequently asked questions
              </h2>
              <p className="mx-auto mt-2 max-w-[560px] text-[17px] opacity-80">
                Everything you need to know about Tarazu and how it transforms your audit
                workflow.
              </p>
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              <FaqCard icon={CheckCircle2} question="Does Tarazu replace our audit methodology?">
                No — it executes your existing methodology faster. Templates and materiality
                thresholds are configured to your firm&rsquo;s standards.
              </FaqCard>
              <FaqCard icon={Lock} question="Where is client data stored?">
                Encrypted at rest and in transit, in your chosen region, with role-based access
                and full activity logs.
              </FaqCard>
              <FaqCard icon={Rocket} question="How long does onboarding take?">
                Most firms run their first live engagement within two weeks, with a dedicated
                implementation lead.
              </FaqCard>
              <FaqCard icon={Plug} question="Does it integrate with our existing tools?">
                Yes — Tarazu offers a robust API and native integrations with n8n, Zapier, and
                popular ERPs.
              </FaqCard>
              <FaqCard icon={Users} question="Is it suitable for small firms?">
                Absolutely. The platform scales from sole practitioners to large global firms,
                with flexible pricing.
              </FaqCard>
              <FaqCard icon={ShieldCheck} question="Is it SOC 2 compliant?">
                Yes, Tarazu is SOC 2 Type II ready, with regular third-party audits and
                continuous monitoring.
              </FaqCard>
            </div>
          </div>
        </section>

        {/* ===== CTA ===== */}
        <section id="cta" className="scroll-mt-16 px-6 py-20 text-center lg:px-10">
          <div className="mx-auto max-w-[1200px]">
            <h2
              className={`${sora.className} mb-4 text-3xl font-bold leading-tight tracking-tight text-[#10243A] md:text-[38px]`}
            >
              See your own engagement in Tarazu
            </h2>
            <p className="mx-auto mb-8 max-w-[56ch]">
              Create your firm&apos;s workspace in a minute, upload one real (anonymised)
              engagement, and see exactly what it automates.
            </p>
            <Link href="/signup" className={BTN_PRIMARY}>
              Get started
            </Link>
          </div>
        </section>
      </main>

      {/* ===== Footer ===== */}
      <footer className="bg-[#10243A] px-6 pb-8 pt-16 text-[15px] text-[#B9C6D2] lg:px-10">
        <div className="mx-auto max-w-[1200px]">
          <div className="mb-12 grid gap-10 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr]">
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
            {[
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
            ].map(({ heading, links }) => (
              <div key={heading}>
                <h4 className="mb-4 text-sm font-semibold uppercase tracking-[0.08em] text-white">
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
          <div className="flex flex-wrap justify-between gap-3 border-t border-[#24374D] pt-6 text-[13.5px]">
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
