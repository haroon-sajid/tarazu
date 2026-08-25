"use client";

/**
 * Account → Notifications. Delivery is not built yet, so every control is
 * shown disabled and the panel says so — nothing here pretends to save.
 */

import {
  DeadToggle,
  PlannedBadge,
  SectionHeader,
  SettingRow,
  SettingsSection,
} from "../_components/shared";

const NOTIFICATION_EVENTS = [
  {
    name: "Case ready for review",
    description: "Extraction and matching finished and the review queue is populated",
  },
  {
    name: "High-severity flag raised",
    description: "A rule flagged an item with high severity",
  },
  {
    name: "Decision recorded by an API key",
    description: "An automation approved or rejected an item on your behalf",
  },
  {
    name: "Weekly summary",
    description: "Open items, decisions made, and outstanding flags for the week",
  },
];

export default function NotificationsSettingsPage() {
  return (
    <div>
      <SectionHeader
        title="Notifications"
        description="Choose which events reach your inbox. Email delivery is under development; these preferences will activate when it ships."
        action={<PlannedBadge />}
      />

      <SettingsSection title="Email">
        {NOTIFICATION_EVENTS.map(({ name, description }) => (
          <SettingRow
            key={name}
            name={name}
            description={description}
            action={<DeadToggle title="Email delivery is under development" />}
          />
        ))}
      </SettingsSection>
    </div>
  );
}
