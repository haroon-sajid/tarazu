import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearSession,
  consumeSessionEndReason,
  getStoredSession,
  markSessionEnded,
  storeSession,
} from "./auth-storage";
import type { Session } from "./types";

/** A `Storage` stand-in: the tests run in Node, where there is no window. */
function memoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => store.get(key) ?? null,
    key: (index) => Array.from(store.keys())[index] ?? null,
    removeItem: (key) => {
      store.delete(key);
    },
    setItem: (key, value) => {
      store.set(key, String(value));
    },
  };
}

const session: Session = {
  accessToken: "token-abc",
  expiresAt: Date.now() + 60_000,
  userId: "user-1",
  email: "auditor@example.com",
  orgId: "org-1",
  organizationName: "Demo Firm",
  role: "owner",
};

describe("session storage", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      localStorage: memoryStorage(),
      sessionStorage: memoryStorage(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("round-trips a session", () => {
    storeSession(session);
    expect(getStoredSession()).toEqual(session);
  });

  it("forgets an expired session instead of handing back a dead token", () => {
    storeSession({ ...session, expiresAt: Date.now() - 1 });
    expect(getStoredSession()).toBeNull();
    // And it is gone from storage, not merely hidden.
    expect(window.localStorage.getItem("tarazu.session")).toBeNull();
  });

  it("rejects a record with no token or no user", () => {
    window.localStorage.setItem(
      "tarazu.session",
      JSON.stringify({ ...session, accessToken: "" }),
    );
    expect(getStoredSession()).toBeNull();
    window.localStorage.setItem("tarazu.session", JSON.stringify({ ...session, userId: "" }));
    expect(getStoredSession()).toBeNull();
  });

  it("survives corrupt storage", () => {
    window.localStorage.setItem("tarazu.session", "{not json");
    expect(getStoredSession()).toBeNull();
  });

  it("clears on demand", () => {
    storeSession(session);
    clearSession();
    expect(getStoredSession()).toBeNull();
  });

  it("returns null with no window at all", () => {
    vi.unstubAllGlobals();
    expect(getStoredSession()).toBeNull();
  });
});

describe("why a session ended", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      localStorage: memoryStorage(),
      sessionStorage: memoryStorage(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is told once, then forgotten", () => {
    markSessionEnded("expired");
    expect(consumeSessionEndReason()).toBe("expired");
    expect(consumeSessionEndReason()).toBeNull();
  });

  it("ignores a value it did not write", () => {
    window.sessionStorage.setItem("tarazu.session-ended", "hacked");
    expect(consumeSessionEndReason()).toBeNull();
  });

  it("is quiet when storage is unavailable", () => {
    vi.stubGlobal("window", {
      sessionStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
      },
    });
    expect(() => markSessionEnded("expired")).not.toThrow();
    expect(consumeSessionEndReason()).toBeNull();
  });
});
