import { useSyncExternalStore } from "react";
import type { Identity, IdentityState } from "../auth/identity";

/** The operator's sign-in state, as a React value. `useSyncExternalStore` rather than an effect and a
 *  `useState`: copying a store's state into component state adds a render's worth of lag and a second
 *  source of truth for no gain. */
export function useIdentityState(identity: Identity): IdentityState {
  return useSyncExternalStore(
    (onChange) => identity.subscribe(onChange),
    () => identity.state(),
  );
}
