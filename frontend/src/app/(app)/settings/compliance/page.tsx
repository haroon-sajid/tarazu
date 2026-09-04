"use client";

/** Trust & data → Compliance: the seven reliability rules the product is built on. */

import {
  Calculator,
  FileSearch,
  Gauge,
  Lock,
  MessagesSquare,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { SectionHeader, SettingsSection } from "../_components/shared";

/** The seven reliability rules, in their canonical order. */
const GUARANTEES = [
  {
    icon: UserCheck,
    name: "The AI suggests, the human decides",
    description:
      "The system has no automatic approval path. Each review item is approved or rejected by a named user, with the time of the decision recorded.",
  },
  {
    icon: Calculator,
    name: "All math and matching is deterministic code, never AI",
    description:
      "Sums, comparisons, reconciliation, and matching run in pure Python. The AI reads documents; it never produces or influences a numeric result.",
  },
  {
    icon: FileSearch,
    name: "Every extracted number is traceable to its source",
    description:
      "Each value records the document, page, and location it was read from, and the evidence viewer opens that exact spot on the real page.",
  },
  {
    icon: Gauge,
    name: "Every AI output carries a confidence level",
    description:
      "Readings are marked high, medium, or low confidence so reviewers know where to look hardest. Extraction output without a confidence level is rejected.",
  },
  {
    icon: Lock,
    name: "Immutable audit trail",
    description:
      "Every action, by AI or human, is recorded in an append-only log. Records cannot be updated or deleted, and this is enforced at the database level.",
  },
  {
    icon: ShieldCheck,
    name: "Client data is never used for model training",
    description:
      "Documents are sent to the extraction model only to be read. No client data is used for training, telemetry, or feedback loops.",
  },
  {
    icon: MessagesSquare,
    name: "The assistant answers only from your documents",
    description:
      "Ask Tarazu computes answers from the case's own results and cites them. Questions it cannot ground in the uploaded files are declined, never guessed.",
  },
];

export default function ComplianceSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Compliance"
        description="The seven reliability rules this product is built on. They are structural: not configurable, and cannot be disabled."
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

      <p className="text-xs text-ink-400">
        Tarazu reconciles your books, flags what needs attention, and explains it
        in plain language. The AI assists, the human decides.
      </p>
    </div>
  );
}
