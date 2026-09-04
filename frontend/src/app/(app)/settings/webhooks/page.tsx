"use client";

/** Developers → Webhooks. On the roadmap; shown honestly, never faked. */

import Link from "next/link";
import { BellRing, FileCheck2, Flag, Plus, Sparkles, Webhook } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlannedBadge, SectionHeader, SettingsSection } from "../_components/shared";

const PLANNED_EVENTS = [
  {
    icon: Flag,
    name: "Flags raised",
    description: "An item is flagged by the rules engine and enters the review queue.",
  },
  {
    icon: FileCheck2,
    name: "Decisions recorded",
    description: "A reviewer approves or rejects an item, or a case is signed off.",
  },
  {
    icon: BellRing,
    name: "Pipeline milestones",
    description: "Extraction, matching, and report generation complete for a period.",
  },
];

export default function WebhooksSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Webhooks"
        description="Receive event notifications for case activity, such as completed extractions, raised flags, and recorded decisions."
        action={
          <span title="Coming soon">
            <Button size="sm" disabled>
              <Plus className="h-3.5 w-3.5" aria-hidden />
              Add webhook
            </Button>
          </span>
        }
      />

      <div className="mb-5 flex items-start gap-2.5 rounded-lg bg-brand-50 px-4 py-3 ring-1 ring-brand-200/70">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
        <div>
          <p className="text-sm font-semibold text-brand-900">Coming soon</p>
          <p className="mt-0.5 text-xs leading-relaxed text-brand-800">
            Webhook delivery is on the Tarazu roadmap. When it ships, endpoints
            you register here will receive signed event notifications in real
            time, authenticated with the API keys that are live today.
          </p>
        </div>
      </div>

      <SettingsSection
        title="Planned events"
        description="The activity a registered endpoint will be notified about."
      >
        {PLANNED_EVENTS.map(({ icon: Icon, name, description }) => (
          <div key={name} className="flex items-start gap-3 py-4">
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-400" aria-hidden />
            <div>
              <p className="inline-flex items-center gap-2 text-sm font-medium text-ink-900">
                {name} <PlannedBadge />
              </p>
              <p className="mt-0.5 max-w-xl text-xs leading-relaxed text-ink-600">
                {description}
              </p>
            </div>
          </div>
        ))}
      </SettingsSection>

      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-slate-300 py-10 text-center">
        <Webhook className="h-8 w-8 text-ink-400" aria-hidden />
        <div>
          <p className="text-sm font-semibold text-ink-900">
            Need this today?
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink-600">
            Scheduled polling of the review items endpoint provides the same
            information right now. See{" "}
            <Link
              href="/settings/integrations"
              className="font-medium text-brand-700 hover:underline"
            >
              Integrations
            </Link>{" "}
            for the pattern.
          </p>
        </div>
      </div>
    </div>
  );
}
