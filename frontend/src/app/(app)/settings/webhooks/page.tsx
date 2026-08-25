"use client";

/** Developers → Webhooks. Under development; shown honestly, never faked. */

import Link from "next/link";
import { Plus, Webhook } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlannedBadge, SectionHeader } from "../_components/shared";

export default function WebhooksSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Webhooks"
        description="Receive event notifications for case activity, such as completed extractions, raised flags, and recorded decisions."
        action={
          <span title="Webhook delivery is under development">
            <Button size="sm" disabled>
              <Plus className="h-3.5 w-3.5" aria-hidden />
              Add webhook
            </Button>
          </span>
        }
      />

      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-slate-300 py-12 text-center">
        <Webhook className="h-8 w-8 text-ink-400" aria-hidden />
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-semibold text-ink-900">
            Webhooks are under development <PlannedBadge />
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink-600">
            Until delivery ships, scheduled polling of the review items endpoint
            provides the same information. See{" "}
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
