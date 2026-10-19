/**
 * What the Users tab needs to know about Entra beyond the sign-in: which service principals carry the roles, and the roles'
 * ids. All of it is public (ids, not secrets) and comes from Terraform's outputs through the build. `null` is a working mode:
 * locally there is no directory to manage and the tab says so.
 */

export interface AccessConfig {
  workbenchPrincipal: string;
  gatewayPrincipal: string;
  roles: { workbenchAdmin: string; workbenchViewer: string; gatewayAdmin: string };
  /** Where an invited viewer lands from the e-mail; an admin lands on the terminal. */
  pocketUrl: string;
}

export interface AccessEnv {
  VITE_ACCESS_WORKBENCH_PRINCIPAL?: string;
  VITE_ACCESS_GATEWAY_PRINCIPAL?: string;
  VITE_ACCESS_ROLE_WORKBENCH_ADMIN?: string;
  VITE_ACCESS_ROLE_WORKBENCH_VIEWER?: string;
  VITE_ACCESS_ROLE_GATEWAY_ADMIN?: string;
  VITE_POCKET_URL?: string;
}

export function resolveAccess(env: AccessEnv = import.meta.env as AccessEnv): AccessConfig | null {
  const values = [
    env.VITE_ACCESS_WORKBENCH_PRINCIPAL,
    env.VITE_ACCESS_GATEWAY_PRINCIPAL,
    env.VITE_ACCESS_ROLE_WORKBENCH_ADMIN,
    env.VITE_ACCESS_ROLE_WORKBENCH_VIEWER,
    env.VITE_ACCESS_ROLE_GATEWAY_ADMIN,
    env.VITE_POCKET_URL,
  ].map((value) => value?.trim() ?? "");
  // The pocket's address is in every build; it alone does not mean the directory is configured.
  if (values.slice(0, 5).every((value) => value === "")) return null;
  if (values.some((value) => value === "")) {
    throw new Error(
      "the VITE_ACCESS_* settings and VITE_POCKET_URL must be set together or left out together — a partial set cannot manage anyone.",
    );
  }
  const [
    workbenchPrincipal,
    gatewayPrincipal,
    workbenchAdmin,
    workbenchViewer,
    gatewayAdmin,
    pocketUrl,
  ] = values as [string, string, string, string, string, string];
  return {
    workbenchPrincipal,
    gatewayPrincipal,
    roles: { workbenchAdmin, workbenchViewer, gatewayAdmin },
    pocketUrl,
  };
}
