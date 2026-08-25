"use client";

/**
 * Account → Account & security: identity, password, and session.
 *
 * The password change is live against POST /v1/auth/change-password. It always
 * asks for the current password — a walked-away-from browser must not be
 * enough to lock the owner out of their account.
 */

import * as React from "react";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { PasswordInput } from "@/components/ui/input";
import { ApiError, changePassword } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatTimestamp } from "@/lib/format";
import {
  CopyButton,
  PlannedBadge,
  SectionHeader,
  SettingRow,
  SettingsSection,
} from "../_components/shared";

export default function AccountSettingsPage() {
  const { session } = useAuth();

  const [changing, setChanging] = React.useState(false);
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [changedMessage, setChangedMessage] = React.useState<string | null>(null);

  const openChange = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError(null);
    setChangedMessage(null);
    setChanging(true);
  };

  const canSubmit =
    !busy &&
    currentPassword.length > 0 &&
    newPassword.length >= 8 &&
    confirmPassword === newPassword;

  const submitChange = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const response = await changePassword(currentPassword, newPassword);
      setChangedMessage(response.message);
      setChanging(false);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not change the password.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <SectionHeader
        title="Account & security"
        description="Your sign-in identity. Every decision you record is attributed to this account in the audit trail."
      />

      <SettingsSection title="Profile">
        <SettingRow
          name="Email address"
          description="Used to sign in and to attribute your decisions"
          value={session?.email ?? "-"}
        />
        <SettingRow
          name="User id"
          description="Your identifier in audit records"
          value={<span className="font-mono text-xs">{session?.userId ?? "-"}</span>}
          action={
            session?.userId ? (
              <CopyButton value={session.userId} label="user id" />
            ) : undefined
          }
        />
      </SettingsSection>

      <SettingsSection title="Security">
        <SettingRow
          name="Password"
          description="Changing it requires your current password"
          value="••••••••"
          action={
            <Button size="sm" variant="outline" onClick={openChange}>
              Change password
            </Button>
          }
        />
        {changedMessage && (
          <p className="flex items-start gap-1.5 py-3 text-xs text-emerald-700">
            <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            {changedMessage}
          </p>
        )}
        <SettingRow
          name="Two-factor authentication"
          description="A second factor at sign-in, in addition to the password"
          value="Off"
          action={<PlannedBadge />}
        />
      </SettingsSection>

      <SettingsSection title="Session">
        <SettingRow
          name="Current session"
          description="Signing in again renews the session"
          value={
            session
              ? `Expires ${formatTimestamp(new Date(session.expiresAt).toISOString())}`
              : "-"
          }
        />
      </SettingsSection>

      <Dialog
        open={changing}
        onClose={() => !busy && setChanging(false)}
        title="Change password"
      >
        <div className="space-y-4">
          <PasswordInput
            label="Current password"
            autoFocus
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
          <PasswordInput
            label="New password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            hint="At least 8 characters."
          />
          <PasswordInput
            label="Confirm new password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            hint={
              confirmPassword && confirmPassword !== newPassword
                ? "Does not match the new password."
                : undefined
            }
          />

          {error && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setChanging(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={submitChange} disabled={!canSubmit}>
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Change password
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
