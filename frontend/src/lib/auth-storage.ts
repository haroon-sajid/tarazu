/**
 * Session persistence, kept dependency-free so `api.ts` can read the token
 * without importing React. The session is a short-lived access token plus the
 * identity facts the auth endpoints returned — never a password, never a
 * secret beyond the token itself.
 */

import type { Session } from "./types";

const STORAGE_KEY = "tarazu.session";

export function getStoredSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session.accessToken || !session.userId) return null;
    if (Date.now() >= session.expiresAt) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function storeSession(session: Session): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Private windows can refuse storage; the in-memory context still works.
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear.
  }
}
