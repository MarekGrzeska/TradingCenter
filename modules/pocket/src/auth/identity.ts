/**
 * Who the operator is, as the rest of this app needs to know it. Three states, and the third is not an
 * error: a phone pointed at `localhost` has no identity configured and must not ask anybody to sign in.
 */
export type IdentityState = "unconfigured" | "signed-out" | "signed-in";

/** Said in one place because the sign-in screen and a refused request both say it. */
export const SIGNED_OUT_MESSAGE = "you are signed out — sign in to reach the archive";

/** A refusal signing in would fix, told apart from every other refusal. Never thrown in the
 *  `unconfigured` case, where there is no session to have lost. */
export class SignedOut extends Error {
  constructor(message: string = SIGNED_OUT_MESSAGE) {
    super(message);
    this.name = "SignedOut";
  }
}

export interface Identity {
  state(): IdentityState;
  /** Notified whenever `state()` would answer differently; returns the unsubscribe. */
  subscribe(listener: (state: IdentityState) => void): () => void;
  /** A token for the archive, or `null` when no identity is configured — which means "send no
   *  credential", not "something went wrong". Rejects with `SignedOut` when there was a session
   *  and it is gone. */
  token(): Promise<string | null>;
  /** The same, having thrown away what was cached. This is what a 401 asks for: the token the
   *  request carried was rejected, so asking for the identical one again asks to be refused twice. */
  refresh(): Promise<string | null>;
  /** Sends the operator through sign-in. Resolves nothing: with the redirect flow the page is gone. */
  signIn(): void;
}

/** What this app runs on locally. `token()` answering `null` rather than throwing is the whole of it:
 *  requests go out bare, and nothing has to branch on "are we in local mode". */
export const noIdentity: Identity = {
  state: () => "unconfigured",
  subscribe: () => () => {},
  token: async () => null,
  refresh: async () => null,
  signIn: () => {},
};
