"use client";

/**
 * The auth context: who is signed in, and how to sign in, up, and out.
 * All HTTP goes through `api.ts`; this file only manages session state.
 */

import * as React from "react";
import { login as apiLogin, signup as apiSignup } from "./api";
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
  ) => Promise<void>;
  signOut: () => void;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = React.useState<Session | null | undefined>(undefined);

  React.useEffect(() => {
    setSession(getStoredSession());
  }, []);

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
  }, []);

  const signUp = React.useCallback(
    async (email: string, password: string, organizationName: string) => {
      const created = await apiSignup(email, password, organizationName);
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

  const value = React.useMemo(
    () => ({ session, signIn, signUp, signOut }),
    [session, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
