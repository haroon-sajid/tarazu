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

/**
 * Why the last session ended, when it ended on its own rather than by a
 * sign-out click — so the login screen can say "your session ended" instead
 * of greeting someone who was mid-task as if they had just arrived. Kept in
 * sessionStorage: it is a note for the next screen in this tab, not a fact
 * about the person.
 */
const ENDED_KEY = "tarazu.session-ended";

export type SessionEndReason = "expired";

export function markSessionEnded(reason: SessionEndReason): void {
  try {
    window.sessionStorage.setItem(ENDED_KEY, reason);
  } catch {
    // Storage unavailable: the login screen shows its usual greeting.
  }
}

/** Read and clear the note, so it is shown once. */
export function consumeSessionEndReason(): SessionEndReason | null {
  try {
    const reason = window.sessionStorage.getItem(ENDED_KEY);
    if (reason) window.sessionStorage.removeItem(ENDED_KEY);
    return reason === "expired" ? reason : null;
  } catch {
    return null;
  }
}
