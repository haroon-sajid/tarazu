"use client";

/**
 * The auth context: who is signed in, and how to sign in, up, and out.
 * All HTTP goes through `api.ts`; this file only manages session state.
 */

import * as React from "react";
import {
  FIXTURE_MODE,
  getOrgProfile,
  listMembers,
  login as apiLogin,
  signup as apiSignup,
} from "./api";
import { clearSession, getStoredSession, storeSession } from "./auth-storage";
import type { Session } from "./types";

interface AuthContextValue {
  /** null = signed out. undefined = still reading localStorage (first paint). */
  session: Session | null | undefined;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (
    email: string,
    password: string,
    organizationName: string,
    inviteCode?: string,
  ) => Promise<void>;
  signOut: () => void;
  /** Update the cached organization name without a full re-sign-in. */
  updateOrganizationName: (name: string) => void;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = React.useState<Session | null | undefined>(undefined);

  /**
   * The login response deliberately carries no org claim, so a session that
   * did not just sign up in this browser (the seeded demo login, a fresh
   * machine) starts with null org facts. Fill them from the backend: the org
   * profile names the workspace, the member list carries this user's role.
   */
  const hydrateOrgFacts = React.useCallback((base: Session) => {
    if (FIXTURE_MODE) return;
    if (base.orgId && base.organizationName && base.role) return;
    void (async () => {
      try {
        const [org, members] = await Promise.all([
          getOrgProfile(),
          listMembers().catch(() => null),
        ]);
        const role = members?.members.find(
          (member) => member.user_id === base.userId,
        )?.role;
        setSession((current) => {
          // Signed out (or in again) while fetching: leave that session be.
          if (!current || current.accessToken !== base.accessToken) return current;
          const next: Session = {
            ...current,
            orgId: current.orgId ?? org.org_id,
            organizationName: current.organizationName ?? org.name,
            role: current.role ?? role ?? null,
          };
          storeSession(next);
          return next;
        });
      } catch {
        // Offline or denied: the facts stay null and screens keep their fallbacks.
      }
    })();
  }, []);

  React.useEffect(() => {
    const stored = getStoredSession();
    setSession(stored);
    if (stored) hydrateOrgFacts(stored);
  }, [hydrateOrgFacts]);

  const signIn = React.useCallback(async (email: string, password: string) => {
    const response = await apiLogin(email, password);
    // Keep whatever org facts a previous signup on this browser recorded —
    // the login response deliberately carries no org claim.
    const previous = getStoredSession();
    const next: Session = {
      accessToken: response.access_token,
      expiresAt: Date.now() + response.expires_in * 1000,
      userId: response.user_id,
      email: response.email ?? email,
      orgId: previous?.email === (response.email ?? email) ? (previous?.orgId ?? null) : null,
      organizationName:
        previous?.email === (response.email ?? email)
          ? (previous?.organizationName ?? null)
          : null,
      role: previous?.email === (response.email ?? email) ? (previous?.role ?? null) : null,
    };
    storeSession(next);
    setSession(next);
    hydrateOrgFacts(next);
  }, [hydrateOrgFacts]);

  const signUp = React.useCallback(
    async (
      email: string,
      password: string,
      organizationName: string,
      inviteCode?: string,
    ) => {
      const created = await apiSignup(email, password, organizationName, inviteCode);
      // Signup returns no token — sign in next, then attach the org facts.
      const response = await apiLogin(email, password);
      const next: Session = {
        accessToken: response.access_token,
        expiresAt: Date.now() + response.expires_in * 1000,
        userId: created.user_id,
        email: created.email,
        orgId: created.org_id,
        organizationName: created.organization_name,
        role: created.role,
      };
      storeSession(next);
      setSession(next);
    },
    [],
  );

  const signOut = React.useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  const updateOrganizationName = React.useCallback((name: string) => {
    setSession((current) => {
      if (!current) return current;
      const next = { ...current, organizationName: name };
      storeSession(next);
      return next;
    });
  }, []);

  const value = React.useMemo(
    () => ({ session, signIn, signUp, signOut, updateOrganizationName }),
    [session, signIn, signUp, signOut, updateOrganizationName],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
