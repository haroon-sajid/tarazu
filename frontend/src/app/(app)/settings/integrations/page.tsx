"use client";

/** Developers → Integrations: what connects today, and what is on the roadmap. */

import Link from "next/link";
import { CalendarClock, Sparkles, Webhook, Workflow } from "lucide-react";
import { PlannedBadge, SectionHeader, SettingsSection } from "../_components/shared";

const ROADMAP = [
  {
    icon: Webhook,
    name: "Webhook delivery",
    description: "Push notifications for case activity instead of polling.",
    href: "/settings/webhooks",
  },
  {
    icon: Workflow,
    name: "Workflow templates",
    description:
      "Ready-made recipes for automation platforms, built on the same API keys.",
  },
  {
    icon: CalendarClock,
    name: "Scheduled report delivery",
    description: "Finished reports sent to your team on a schedule you set.",
  },
];

export default function IntegrationsSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Integrations"
        description="Tarazu integrates with any automation platform or internal tool that supports custom request headers."
      />

      <div className="mb-5 flex items-start gap-2.5 rounded-lg bg-brand-50 px-4 py-3 ring-1 ring-brand-200/70">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
        <div>
          <p className="text-sm font-semibold text-brand-900">
            Native connectors coming soon
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-brand-800">
            Pre-built connectors and workflow templates are on the roadmap. The
            API key pattern below works today and connects any tool that can
            send a custom header.
          </p>
        </div>
      </div>

      <SettingsSection
        title="Available now: connect with an API key"
        description="Live today, on the same endpoints the product itself uses."
      >
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
              <span className="font-mono text-xs max-md:break-all">
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

      <SettingsSection
        title="On the roadmap"
        description="Planned additions. Each one builds on the API keys and scopes that are already live."
      >
        {ROADMAP.map(({ icon: Icon, name, description, href }) => (
          <div key={name} className="flex items-start gap-3 py-4">
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" aria-hidden />
            <div>
              <p className="inline-flex items-center gap-2 text-sm font-medium text-ink-900">
                {href ? (
                  <Link href={href} className="hover:underline">
                    {name}
                  </Link>
                ) : (
                  name
                )}{" "}
                <PlannedBadge />
              </p>
              <p className="mt-0.5 max-w-xl text-xs leading-relaxed text-ink-600">
                {description}
              </p>
            </div>
          </div>
        ))}
      </SettingsSection>
    </div>
  );
}
