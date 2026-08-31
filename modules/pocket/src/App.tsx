import { useMemo, useSyncExternalStore } from "react";
import { noIdentity, type Identity } from "./auth/identity";
import { createPolymarketApi } from "./polymarket/api";
import { PolymarketScreen } from "./polymarket/PolymarketScreen";
import { SignInScreen } from "./SignInScreen";

/** One screen, and no router: this app is the prediction-market tab of the terminal, on a phone. A
 *  second surface here would be the terminal again, badly. */
export function App({ identity = noIdentity }: { identity?: Identity }) {
  const state = useSyncExternalStore(identity.subscribe, identity.state);

  // Built once per identity: the screen's effects take it as a dependency, and a client rebuilt on
  // every render would re-read the archive on every render with it.
  const api = useMemo(() => createPolymarketApi(undefined, identity), [identity]);

  // `unconfigured` is the local stack and renders the screen bare — only a deployment that has an
  // identity to lose can be signed out of one.
  if (state === "signed-out") {
    return <SignInScreen onSignIn={identity.signIn} />;
  }
  return <PolymarketScreen api={api} />;
}
