"use client";

/** Trust & data → Environment: what this deployment is connected to. */

import * as React from "react";
import { FIXTURE_MODE } from "@/lib/api";
import { SectionHeader, SettingRow, SettingsSection } from "../_components/shared";

const API_URL = (process.env.NEXT_PUBLIC_TARAZU_API_URL || "").replace(/\/+$/, "");
const IS_LOCAL_URL = /^https?:\/\/(localhost|127\.0\.0\.1)([:/]|$)/.test(API_URL);

type HealthState =
  | { state: "checking" }
  | { state: "ok"; version: string }
  | { state: "down" };

/** Live liveness check against the backend's unauthenticated `GET /health`. */
function useBackendHealth(): HealthState {
  const [health, setHealth] = React.useState<HealthState>({ state: "checking" });

  React.useEffect(() => {
    if (FIXTURE_MODE) return;
    let cancelled = false;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 6000);
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        const body = (await response.json()) as { version?: string };
        if (!cancelled) setHealth({ state: "ok", version: body.version ?? "unknown" });
      })
      .catch(() => {
        if (!cancelled) setHealth({ state: "down" });
      })
      .finally(() => window.clearTimeout(timer));
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, []);

  return health;
}

function StatusDot({ tone }: { tone: "ok" | "down" | "checking" }) {
  return (
    <span
      className={
        tone === "ok"
          ? "h-2 w-2 shrink-0 rounded-full bg-emerald-500"
          : tone === "down"
            ? "h-2 w-2 shrink-0 rounded-full bg-rose-500"
            : "h-2 w-2 shrink-0 rounded-full bg-slate-300 motion-safe:animate-pulse"
      }
      aria-hidden
    />
  );
}

export default function EnvironmentSettingsPage() {
  const health = useBackendHealth();

  const environmentLabel = FIXTURE_MODE
    ? "Offline demo"
    : IS_LOCAL_URL
      ? "Local development"
      : "Production";

  return (
    <div>
      <SectionHeader
        title="Environment"
        description="What this deployment is connected to. Read straight from this build's configuration and a live check against the backend — nothing here is editable."
      />

      <SettingsSection title="Connection">
        <SettingRow
          name="Environment"
          description="How this build is configured to run"
          value={environmentLabel}
        />
        <SettingRow
          name="Data source"
          description="Where screens read and write data"
          value={FIXTURE_MODE ? "Fixture data (offline demo)" : "Live backend"}
        />
        <SettingRow
          name="Backend URL"
          description="The API this application talks to"
          value={
            FIXTURE_MODE ? (
              "None — screens read bundled fixture data"
            ) : (
              <span className="break-all font-mono text-xs">{API_URL}</span>
            )
          }
        />
        {!FIXTURE_MODE && (
          <SettingRow
            name="Backend status"
            description="A live check against the API's /health endpoint"
            value={
              <span className="inline-flex items-center gap-1.5">
                <StatusDot tone={health.state === "ok" ? "ok" : health.state === "down" ? "down" : "checking"} />
                {health.state === "ok"
                  ? "Connected"
                  : health.state === "down"
                    ? "Unreachable"
                    : "Checking…"}
              </span>
            }
          />
        )}
        {!FIXTURE_MODE && health.state === "ok" && (
          <SettingRow
            name="Backend version"
            description="Reported by the backend itself"
            value={<span className="font-mono text-xs">{health.version}</span>}
          />
        )}
      </SettingsSection>

      <SettingsSection title="How the pieces fit">
        <SettingRow
          name="Documents and decisions"
          description="Uploads, review decisions, and the audit trail live in the backend's own store; the browser holds no case data beyond the screen it is showing"
        />
        <SettingRow
          name="Numbers on screen"
          description="Every figure is computed by the backend's deterministic code and delivered ready to display; the interface never sums, averages, or derives"
        />
        <SettingRow
          name="Active case"
          description="Which case the screens show is a selection kept in this browser only; the case itself stays in the backend"
        />
      </SettingsSection>

      {FIXTURE_MODE && (
        <p className="text-xs text-ink-400">
          Set <span className="font-mono">NEXT_PUBLIC_TARAZU_API_URL</span> in{" "}
          <span className="font-mono">.env.local</span> and restart the dev server
          to switch every screen to the live API.
        </p>
      )}
      {!FIXTURE_MODE && IS_LOCAL_URL && (
        <p className="text-xs text-ink-400">
          This URL points at a backend on this machine. For a public deployment,
          set <span className="font-mono">NEXT_PUBLIC_TARAZU_API_URL</span> to the
          live API URL before building; this page will then report it here.
        </p>
      )}
    </div>
  );
}
