import { useEffect, useState } from "react";
import type { IdentityState } from "../auth/identity";
import type { Role } from "../app/tabs";
import type { AccessApi } from "./accessApi";

/** `none` is a person the door knows and gave nothing; `loading` is not having asked yet. */
export type RoleState = Role | "none" | "loading";

/**
 * Who the workbench says this person is. Local work (no identity) is the admin's screen, as it has always been. An answer that
 * cannot be had becomes `viewer`: this only decides what is shown, the door refuses the rest, and a screen that offered
 * actions it cannot honour would be the worse failure.
 */
export function useRole(api: AccessApi, identityState: IdentityState): RoleState {
  const [role, setRole] = useState<RoleState>("loading");

  useEffect(() => {
    if (identityState !== "signed-in") return;
    const controller = new AbortController();
    api
      .me(controller.signal)
      .then((me) =>
        setRole(me.roles.includes("admin") ? "admin" : me.roles.includes("viewer") ? "viewer" : "none"),
      )
      .catch(() => {
        if (!controller.signal.aborted) setRole("viewer");
      });
    return () => controller.abort();
  }, [api, identityState]);

  return identityState === "unconfigured" ? "admin" : role;
}
