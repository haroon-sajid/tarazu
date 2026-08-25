"use client";

/** Trust & data → Environment: what this deployment is connected to. */

import { FIXTURE_MODE } from "@/lib/api";
import { SectionHeader, SettingRow, SettingsSection } from "../_components/shared";

export default function EnvironmentSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Environment"
        description="The data source this application is connected to."
      />

      <SettingsSection title="Connection">
        <SettingRow
          name="Data source"
          description="Where screens read and write data"
          value={FIXTURE_MODE ? "Fixture data (offline demo)" : "Live backend"}
        />
        <SettingRow
          name="Backend URL"
          description="The API this application talks to"
          value={
            <span className="font-mono text-xs">
              {process.env.NEXT_PUBLIC_TARAZU_API_URL || "Not set"}
            </span>
          }
        />
      </SettingsSection>

      {FIXTURE_MODE && (
        <p className="text-xs text-ink-400">
          Set <span className="font-mono">NEXT_PUBLIC_TARAZU_API_URL</span> in{" "}
          <span className="font-mono">.env.local</span> and restart the dev server
          to switch every screen to the live API.
        </p>
      )}
    </div>
  );
}
