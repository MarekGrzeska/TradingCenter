/** Where the archive answers. A relative path needs no expansion — `fetch("/polymarket-api/events")`
 *  already resolves against the page origin — so this only trims the trailing slash callers join onto. */
export function archiveBase(
  raw: string | undefined = import.meta.env.VITE_POLYMARKET_HTTP as string | undefined,
): string {
  return (raw?.trim() || "/polymarket-api").replace(/\/+$/, "");
}

export interface EntraConfig {
  clientId: string;
  tenantId: string;
  /** One scope, for the one back end this app reads. `api://tradingcenter-polymarket-data/access_as_user`. */
  scope: string;
}

/** What a deployed copy needs to sign the operator in, or `null` for the local stack, where
 *  `polymarket-data` requires no principal.
 *
 *  **All three or none.** Two of the three is a build that sends the operator to a sign-in it cannot
 *  finish, and the failure surfaces as an Entra page about an unknown resource rather than as the
 *  missing setting it is. All three are public by nature — a client id, a tenant id and a scope name
 *  travel in every authorization request the browser makes — so they arrive through `vars`, never
 *  `secrets`. */
export function entraConfig(env: ImportMetaEnv = import.meta.env): EntraConfig | null {
  const clientId = (env.VITE_ENTRA_CLIENT_ID as string | undefined)?.trim();
  const tenantId = (env.VITE_ENTRA_TENANT_ID as string | undefined)?.trim();
  const scope = (env.VITE_ENTRA_SCOPE_POLYMARKET as string | undefined)?.trim();
  if (!clientId || !tenantId || !scope) return null;
  return { clientId, tenantId, scope };
}
