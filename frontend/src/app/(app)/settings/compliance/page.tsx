"use client";

/** Trust & data → Compliance: the guarantees the product is built on. */

import { Lock, Scale, ShieldCheck } from "lucide-react";
import { SectionHeader, SettingsSection } from "../_components/shared";

const GUARANTEES = [
  {
    icon: Lock,
    name: "Immutable audit trail",
    description:
      "Every action is recorded in an append-only log. Records cannot be updated or deleted, and this is enforced at the database level.",
  },
  {
    icon: ShieldCheck,
    name: "Client data is never used for model training",
    description:
      "Documents are sent to the extraction model only to be read. No client data is used for training, telemetry, or feedback loops.",
  },
  {
    icon: Scale,
    name: "Every decision is made by a person",
    description:
      "The system has no automatic approval path. Each review item is approved or rejected by a named user, with the time of the decision recorded.",
  },
];

export default function ComplianceSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Compliance"
        description="These guarantees are structural. They are not configurable and cannot be disabled."
      />

      <SettingsSection title="Guarantees">
        {GUARANTEES.map(({ icon: Icon, name, description }) => (
          <div key={name} className="flex items-start gap-3 py-4">
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden />
            <div>
              <p className="text-sm font-medium text-ink-900">{name}</p>
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
