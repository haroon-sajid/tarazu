"use client";

/** Workspace → General: the organization's identity. */

import * as React from "react";
import { Loader2 } from "lucide-react";
import { ApiError, FIXTURE_MODE, updateOrganization } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  CopyButton,
  PlannedBadge,
  SectionHeader,
  SettingRow,
  SettingsSection,
} from "../_components/shared";

export default function GeneralSettingsPage() {
  const { session, updateOrganizationName } = useAuth();
  const organizationName =
    session?.organizationName ?? (FIXTURE_MODE ? "Demo Audit Firm" : "-");
  const orgId = session?.orgId ?? (FIXTURE_MODE ? "ORG-FIXTURE-0001" : null);
  const isOwner = session?.role === "owner";

  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(organizationName);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (editing) setDraft(organizationName);
  }, [editing, organizationName]);

  const submit = async () => {
    const name = draft.trim();
    if (!name || busy || name === organizationName) {
      if (name === organizationName) setEditing(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await updateOrganization({ name });
      updateOrganizationName(name);
      setEditing(false);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not save the organization name.",
      );
    } finally {
      setBusy(false);
    }
  };

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
            isOwner ? (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                Edit
              </Button>
            ) : (
              <span title="Only an owner can rename the organization">
                <Button size="sm" variant="outline" disabled>
                  Edit
                </Button>
              </span>
            )
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

      <Dialog
        open={editing}
        onClose={() => !busy && setEditing(false)}
        title="Edit organization name"
      >
        <div className="space-y-4">
          <Input
            label="Organization name"
            autoFocus
            maxLength={200}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Demo Audit Firm"
            hint="The name appears in the sidebar, header, and on reports."
          />
          {error && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {error}
            </p>
          )}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              className="w-full sm:w-auto"
              variant="outline"
              size="sm"
              onClick={() => setEditing(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              className="w-full sm:w-auto"
              size="sm"
              onClick={submit}
              disabled={busy || !draft.trim() || draft.trim() === organizationName}
            >
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Save
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
