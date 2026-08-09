import type { EntraConfig } from "../data/config";

/**
 * Who the operator is, as everything else in the terminal needs to know it.
 *
 * The data layer asks for a token and gets one; the shell asks for a state and
 * shows it. Neither knows that Entra exists, which is the point — `entra.ts`
 * is the only file that does, and this interface is the seam. It is also what
 * makes the data layer testable at all: a test hands it a two-line object
 * instead of standing up a sign-in flow.
 *
 * There are three states rather than two, and the third is not an error. A
 * terminal running against `localhost` has **no identity configured**, talks to
 * an archive with nothing in front of it, and must not ask anybody to sign in
 * — that is `unconfigured`. Not being signed in when identity *is* configured
 * is a different thing entirely, and the difference is what stops the shell
 * from telling a developer their local session expired.
 */
export type IdentityState = "unconfigured" | "signed-out" | "signed-in";

/** A refusal that signing in would fix, told apart from every other refusal.
 *  Thrown by `token`/`refresh` when identity is configured and the operator's
 *  session is gone — never in the `unconfigured` case, where there is no
 *  session to lose. */
export class SignedOut extends Error {
  constructor(message = SIGNED_OUT_MESSAGE) {
    super(message);
    this.name = "SignedOut";
  }
}

/** Said in one place because it is said in three: the chart, the top bar and
 *  any failed request all have to phrase this the same way. */
export const SIGNED_OUT_MESSAGE = "you are signed out — sign in to reach the archive";

export interface Identity {
  state(): IdentityState;

  /** Notified whenever `state()` would answer differently. Returns the
   *  unsubscribe, the same shape the socket hub and the source use. */
  subscribe(listener: (state: IdentityState) => void): () => void;

  /** A token for the archive, or `null` when no identity is configured — which
   *  means "send no credential", not "something went wrong". Rejects with
   *  `SignedOut` when identity is configured and the session is gone. */
  token(): Promise<string | null>;

  /** The same, having first thrown away whatever was cached. This is what a
   *  refusal asks for: the token the request carried was rejected, so asking
   *  for the identical one again would be asking to be refused twice. */
  refresh(): Promise<string | null>;

  /** Sends the operator through sign-in. Returns nothing and resolves nothing:
   *  with the redirect flow the page is gone before this returns. */
  signIn(): void;
}

/**
 * What the terminal runs on when nothing is configured — local development,
 * and every test that does not care about identity.
 *
 * `token()` answering `null` rather than throwing is the whole of it: requests
 * go out bare, exactly as they did before any of this existed, and nothing
 * anywhere has to branch on "are we in local mode".
 */
export const noIdentity: Identity = {
  state: () => "unconfigured",
  subscribe: () => () => {},
  token: async () => null,
  refresh: async () => null,
  signIn: () => {},
};

/** Bookkeeping every implementation needs and none should write twice. */
export function createListeners() {
  const listeners = new Set<(state: IdentityState) => void>();
  return {
    add(listener: (state: IdentityState) => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    notify(state: IdentityState): void {
      for (const listener of listeners) listener(state);
    },
  };
}

/** The configuration an identity needs, or `null` when there is none — the one
 *  place that decision is read, so `marketData.ts` does not repeat it. */
export type MaybeEntraConfig = EntraConfig | null;
