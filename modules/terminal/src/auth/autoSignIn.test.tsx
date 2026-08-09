import { beforeEach, describe, expect, it, vi } from "vitest";
import { SIGN_IN_ATTEMPTED_KEY, startSignInIfNeeded } from "./autoSignIn";
import { noIdentity } from "./identity";
import type { Identity, IdentityState } from "./identity";

/** `sessionStorage`'s three methods, in memory — enough to stand in for it and
 *  to be *missing* on purpose in the test that needs it gone. */
function fakeStorage(initial: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(initial));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => [...values.keys()][index] ?? null,
    removeItem: (key: string) => void values.delete(key),
    setItem: (key: string, value: string) => void values.set(key, value),
  };
}

function identityIn(state: IdentityState): Identity & { signIn: ReturnType<typeof vi.fn> } {
  return { ...noIdentity, state: () => state, signIn: vi.fn() };
}

let storage: Storage;

beforeEach(() => {
  storage = fakeStorage();
});

describe("startSignInIfNeeded (terminal-identity spec)", () => {
  it("sends a signed-out operator through sign-in without being asked", () => {
    const identity = identityIn("signed-out");

    expect(startSignInIfNeeded(identity, storage)).toBe(true);
    expect(identity.signIn).toHaveBeenCalledTimes(1);
  });

  it("does not sign in when no identity is configured", () => {
    // Local work against an archive with nothing in front of it. There is
    // nowhere to send anybody, and a developer must never be redirected.
    const identity = identityIn("unconfigured");

    expect(startSignInIfNeeded(identity, storage)).toBe(false);
    expect(identity.signIn).not.toHaveBeenCalled();
    expect(storage.getItem(SIGN_IN_ATTEMPTED_KEY)).toBeNull();
  });

  it("does not sign in an operator who already is", () => {
    const identity = identityIn("signed-in");

    expect(startSignInIfNeeded(identity, storage)).toBe(false);
    expect(identity.signIn).not.toHaveBeenCalled();
  });

  it("stops at one attempt when the operator comes back still signed out", () => {
    // The redirect loop this exists to prevent: the marker was written before
    // the page left, so finding it here means the round trip already happened.
    const identity = identityIn("signed-out");
    storage.setItem(SIGN_IN_ATTEMPTED_KEY, "1");

    expect(startSignInIfNeeded(identity, storage)).toBe(false);
    expect(identity.signIn).not.toHaveBeenCalled();
  });

  it("marks the attempt before leaving, not after coming back", () => {
    const identity = identityIn("signed-out");
    identity.signIn.mockImplementation(() => {
      // Whatever the real one does, the page is gone by the time it returns —
      // so the marker has to already be there when it is called.
      expect(storage.getItem(SIGN_IN_ATTEMPTED_KEY)).not.toBeNull();
    });

    startSignInIfNeeded(identity, storage);

    expect(identity.signIn).toHaveBeenCalledTimes(1);
  });

  it("forgets the attempt once the operator is signed in, so a later expiry may try again", () => {
    storage.setItem(SIGN_IN_ATTEMPTED_KEY, "1");

    startSignInIfNeeded(identityIn("signed-in"), storage);
    expect(storage.getItem(SIGN_IN_ATTEMPTED_KEY)).toBeNull();

    const expired = identityIn("signed-out");
    expect(startSignInIfNeeded(expired, storage)).toBe(true);
    expect(expired.signIn).toHaveBeenCalledTimes(1);
  });

  it("does nothing at all without storage to remember the attempt in", () => {
    // No storage means no way to stop at one attempt — and a terminal that
    // cannot keep a session anyway. The button stays; the redirect does not.
    const identity = identityIn("signed-out");

    expect(startSignInIfNeeded(identity, null)).toBe(false);
    expect(identity.signIn).not.toHaveBeenCalled();
  });
});
