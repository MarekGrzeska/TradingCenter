import { useSyncExternalStore } from "react";
import type { Identity, IdentityState } from "../auth/identity";

/** The operator's sign-in state, as a React value.
 *
 *  `useSyncExternalStore` rather than an effect and a `useState`: the identity
 *  is a store that already exists outside React and already knows how to notify
 *  — copying its state into component state would add a render's worth of lag
 *  and a second source of truth for no gain. */
export function useIdentityState(identity: Identity): IdentityState {
  return useSyncExternalStore(
    (onChange) => identity.subscribe(onChange),
    () => identity.state(),
  );
}
