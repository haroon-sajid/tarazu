"use client";

/** Developers → Integrations: how external tools authenticate and connect. */

import Link from "next/link";
import { SectionHeader, SettingsSection } from "../_components/shared";

export default function IntegrationsSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Integrations"
        description="Tarazu integrates with any automation platform or internal tool that supports custom request headers."
      />

      <SettingsSection title="Connecting a tool">
        <div className="py-4">
          <p className="text-sm text-ink-600">
            Authenticate by sending an API key in the{" "}
            <span className="font-mono text-xs">X-API-Key</span> header. Keys are
            created under{" "}
            <Link
              href="/settings/api-keys"
              className="font-medium text-brand-700 hover:underline"
            >
              API keys
            </Link>
            .
          </p>
          <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-ink-600">
            <li>
              Store the key in your platform&apos;s credential manager as a
              header credential named{" "}
              <span className="font-mono text-xs">X-API-Key</span>.
            </li>
            <li>
              Schedule requests to the endpoints you need, for example{" "}
              <span className="font-mono text-xs">
                GET /v1/review-items?decision=pending&amp;flagged=true
              </span>{" "}
              to retrieve items awaiting review.
            </li>
            <li>
              Route the results into your team&apos;s notification or task
              workflow.
            </li>
          </ol>
          <p className="mt-4 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
            Send keys only in the request header. Keys placed in URLs or query
            parameters can be exposed through access logs.
          </p>
        </div>
      </SettingsSection>
    </div>
  );
}
