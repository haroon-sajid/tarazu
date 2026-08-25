"use client";

/** Workspace → General: the organization's identity. */

import { Button } from "@/components/ui/button";
import { FIXTURE_MODE } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  CopyButton,
  PlannedBadge,
  SectionHeader,
  SettingRow,
  SettingsSection,
} from "../_components/shared";

export default function GeneralSettingsPage() {
  const { session } = useAuth();
  const organizationName =
    session?.organizationName ?? (FIXTURE_MODE ? "Demo Audit Firm" : "-");
  const orgId = session?.orgId ?? (FIXTURE_MODE ? "ORG-FIXTURE-0001" : null);

  return (
    <div>
      <SectionHeader
        title="General"
        description="Your organization's identity. Every case, document, and audit record belongs to this workspace."
      />

      <SettingsSection title="Organization">
        <SettingRow
          name="Organization name"
          description="The display name of your firm"
          value={organizationName}
          action={
            <span title="Renaming is under development">
              <Button size="sm" variant="outline" disabled>
                Edit
              </Button>
            </span>
          }
        />
        <SettingRow
          name="Organization id"
          description="Unique identifier for this workspace"
          value={<span className="font-mono text-xs">{orgId ?? "-"}</span>}
          action={orgId ? <CopyButton value={orgId} label="organization id" /> : undefined}
        />
      </SettingsSection>

      <SettingsSection title="Preferences">
        <SettingRow
          name="Default currency"
          description="Used to format amounts across the product"
          value="PKR"
          action={<PlannedBadge />}
        />
      </SettingsSection>
    </div>
  );
}
