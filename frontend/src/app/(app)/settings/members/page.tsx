"use client";

/**
 * Workspace → Members. Live against /v1/members: the people list, and the
 * owner's invitation flow — cut a single-use join code, hand it over, and
 * the invitee joins at signup. No email is sent: the code in the owner's
 * hands is the invitation, which is honest about what the platform can
 * verify (possession of the code, not ownership of an inbox).
 */

import * as React from "react";
import {
  Ban,
  Check,
  Copy,
  Loader2,
  Plus,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import {
  ApiError,
  inviteMember,
  listInvitations,
  listMembers,
  revokeInvitation,
} from "@/lib/api";
import type { InvitationSummary, MemberSummary, OrgRole } from "@/lib/types";
import { formatTimestamp } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { SectionHeader, StatePill } from "../_components/shared";

export default function MembersSettingsPage() {
  const { session } = useAuth();
  const isOwner = (session?.role ?? "owner") === "owner";

  const [members, setMembers] = React.useState<MemberSummary[] | null>(null);
  const [invitations, setInvitations] = React.useState<InvitationSummary[] | null>(
    null,
  );
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [inviting, setInviting] = React.useState(false);
  const [inviteEmail, setInviteEmail] = React.useState("");
  const [inviteRole, setInviteRole] = React.useState<OrgRole>("member");
  const [inviteBusy, setInviteBusy] = React.useState(false);
  const [inviteError, setInviteError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<InvitationSummary | null>(null);
  const [copiedCode, setCopiedCode] = React.useState<string | null>(null);
  const [revokeBusy, setRevokeBusy] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setMembers(null);
    listMembers()
      .then((response) => setMembers(response.members))
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the members.",
        ),
      );
    // Invitations are owner-only; a member's 403 just means "no panel".
    listInvitations()
      .then((response) => setInvitations(response.invitations))
      .catch(() => setInvitations(null));
  }, []);

  React.useEffect(load, [load]);

  const submitInvite = async () => {
    if (inviteBusy || !inviteEmail.trim()) return;
    setInviteBusy(true);
    setInviteError(null);
    try {
      const invitation = await inviteMember(inviteEmail, inviteRole);
      setCreated(invitation);
      setInvitations((current) => (current ? [invitation, ...current] : [invitation]));
      setInviting(false);
      setInviteEmail("");
      setInviteRole("member");
    } catch (caught) {
      setInviteError(
        caught instanceof ApiError ? caught.message : "Could not create the invitation.",
      );
    } finally {
      setInviteBusy(false);
    }
  };

  const copyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch {
      // Clipboard can be blocked; the code is visible to select manually.
    }
  };

  const revoke = async (invitation: InvitationSummary) => {
    if (revokeBusy) return;
    setRevokeBusy(invitation.invite_id);
    try {
      const remaining = await revokeInvitation(invitation.invite_id);
      setInvitations(remaining.invitations);
    } catch {
      // Leave the list as is; a retry is one click away.
    } finally {
      setRevokeBusy(null);
    }
  };

  return (
    <div>
      <SectionHeader
        title="Members"
        description="People with access to this workspace. All members can view and decide the workspace's cases; only the owner manages membership."
        action={
          isOwner ? (
            <Button size="sm" onClick={() => setInviting(true)}>
              <Plus className="h-3.5 w-3.5" aria-hidden />
              Invite member
            </Button>
          ) : undefined
        }
      />

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : members === null ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left">
            <thead>
              <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                <th className="py-2 pr-4">Member</th>
                <th className="py-2 pr-4">Role</th>
                <th className="py-2 pr-4">Joined</th>
                <th className="py-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => {
                const label = member.email ?? member.user_id;
                const you = member.user_id === session?.userId;
                return (
                  <tr
                    key={member.user_id}
                    className="border-b border-slate-100 text-sm last:border-0"
                  >
                    <td className="py-3 pr-4">
                      <span className="flex items-center gap-3">
                        <span
                          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-50 text-sm font-semibold text-brand-800"
                          aria-hidden
                        >
                          {label.charAt(0).toUpperCase()}
                        </span>
                        <span>
                          <p className="font-medium text-ink-900">
                            {label}
                            {you && (
                              <span className="ml-1.5 text-[10px] font-normal text-ink-400">
                                (you)
                              </span>
                            )}
                          </p>
                          <p className="break-all font-mono text-[10px] text-ink-400">
                            {member.user_id}
                          </p>
                        </span>
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className="inline-flex items-center gap-1 text-sm capitalize text-ink-900">
                        {member.role === "owner" ? (
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                        ) : (
                          <UserRound className="h-3.5 w-3.5 text-ink-400" aria-hidden />
                        )}
                        {member.role}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-xs text-ink-600">
                      {formatTimestamp(member.created_at)}
                    </td>
                    <td className="py-3 text-right">
                      <StatePill tone="positive">Active</StatePill>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Invitations — rendered only where the backend let us list them */}
      {invitations !== null && (
        <div className="mt-8">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-600">
            Invitations
          </h3>
          {invitations.length === 0 ? (
            <p className="text-xs text-ink-400">
              No invitations yet. Cut a join code and hand it to a colleague;
              they enter it on the signup screen.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="py-2 pr-4">Invited</th>
                    <th className="py-2 pr-4">Role</th>
                    <th className="py-2 pr-4">Code</th>
                    <th className="hidden py-2 pr-4 sm:table-cell">Created</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 text-right" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {invitations.map((invitation) => (
                    <tr
                      key={invitation.invite_id}
                      className="border-b border-slate-100 text-sm last:border-0"
                    >
                      <td className="break-all py-2.5 pr-4 font-medium text-ink-900">
                        {invitation.email}
                      </td>
                      <td className="py-2.5 pr-4 capitalize text-ink-600">
                        {invitation.role}
                      </td>
                      <td className="py-2.5 pr-4">
                        {invitation.accepted ? (
                          <span className="font-mono text-xs text-ink-400 line-through">
                            {invitation.code}
                          </span>
                        ) : (
                          <button
                            onClick={() => copyCode(invitation.code)}
                            title="Copy the join code"
                            className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-ink-900 transition-colors hover:bg-slate-200"
                          >
                            {invitation.code}
                            {copiedCode === invitation.code ? (
                              <Check className="h-3 w-3 text-emerald-600" aria-hidden />
                            ) : (
                              <Copy className="h-3 w-3 text-ink-400" aria-hidden />
                            )}
                          </button>
                        )}
                      </td>
                      <td className="hidden py-2.5 pr-4 text-xs text-ink-600 sm:table-cell">
                        {formatTimestamp(invitation.created_at)}
                      </td>
                      <td className="py-2.5 pr-4">
                        {invitation.accepted ? (
                          <StatePill tone="positive">Accepted</StatePill>
                        ) : (
                          <StatePill tone="neutral">Open</StatePill>
                        )}
                      </td>
                      <td className="py-2.5 text-right">
                        {!invitation.accepted && (
                          <button
                            onClick={() => revoke(invitation)}
                            disabled={revokeBusy === invitation.invite_id}
                            title="Revoke this invitation"
                            aria-label={`Revoke the invitation for ${invitation.email}`}
                            className="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-rose-50 hover:text-rose-600 disabled:opacity-40"
                          >
                            {revokeBusy === invitation.invite_id ? (
                              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                            ) : (
                              <Ban className="h-4 w-4" aria-hidden />
                            )}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Invite dialog */}
      <Dialog
        open={inviting}
        onClose={() => !inviteBusy && setInviting(false)}
        title="Invite a member"
      >
        <div className="space-y-4">
          <Input
            label="Email"
            autoFocus
            type="email"
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
            placeholder="colleague@your-firm.pk"
            hint="Recorded on the invitation; the join code is what admits them."
          />
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-600">Role</p>
            <div className="flex gap-2">
              {(["member", "owner"] as OrgRole[]).map((role) => (
                <button
                  key={role}
                  onClick={() => setInviteRole(role)}
                  className={
                    inviteRole === role
                      ? "rounded-full bg-brand-800 px-3 py-1.5 text-xs font-medium capitalize text-white"
                      : "rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium capitalize text-ink-600 hover:bg-slate-200"
                  }
                >
                  {role}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-ink-400">
              Members see and decide the workspace&apos;s cases. Owners also
              manage members, invitations, and settings.
            </p>
          </div>
          {inviteError && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {inviteError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setInviting(false)}
              disabled={inviteBusy}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={submitInvite} disabled={inviteBusy || !inviteEmail.trim()}>
              {inviteBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Create invitation
            </Button>
          </div>
        </div>
      </Dialog>

      {/* The freshly cut code, front and centre */}
      <Dialog
        open={created !== null}
        onClose={() => setCreated(null)}
        title="Hand this code to your colleague"
      >
        {created && (
          <div className="space-y-3">
            <p className="text-xs text-ink-600">
              {created.email} enters it in the invite-code field on the signup
              screen and joins this workspace as {created.role}. The code is
              single-use and can be revoked below until it is used.
            </p>
            <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
              <code className="flex-1 font-mono text-lg font-semibold tracking-wide text-ink-900">
                {created.code}
              </code>
              <Button size="sm" variant="outline" onClick={() => copyCode(created.code)}>
                {copiedCode === created.code ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                ) : (
                  <Copy className="h-3.5 w-3.5" aria-hidden />
                )}
                {copiedCode === created.code ? "Copied" : "Copy"}
              </Button>
            </div>
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setCreated(null)}>
                Done
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
