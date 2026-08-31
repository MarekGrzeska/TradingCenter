/** Where each back end answers. A relative path needs no expansion — `fetch("/polymarket-api/events")`
 *  already resolves against the page origin — so this only trims the trailing slash callers join onto. */
function base(raw: string | undefined, fallback: string): string {
  return (raw?.trim() || fallback).replace(/\/+$/, "");
}

export function archiveBase(
  raw: string | undefined = import.meta.env.VITE_POLYMARKET_HTTP as string | undefined,
): string {
  return base(raw, "/polymarket-api");
}

/** The workbench, which is where the conversation lives. The browser never speaks MCP: the workbench
 *  holds the model key and the tool servers' addresses. */
export function workbenchBase(
  raw: string | undefined = import.meta.env.VITE_WORKBENCH_HTTP as string | undefined,
): string {
  return base(raw, "/workbench-api");
}

export interface EntraConfig {
  clientId: string;
  tenantId: string;
  scopes: {
    /** `api://tradingcenter-polymarket-data/access_as_user` — what this app is for. */
    archive: string;
    /** The conversation's own audience, or `null` where none is configured: a token minted for one
     *  module is never sent to another, so the agent goes without rather than borrowing the
     *  archive's. The screen says so instead of meeting a 401 it cannot explain. */
    workbench: string | null;
  };
}

/** What a deployed copy needs to sign the operator in, or `null` for the local stack, where neither
 *  back end requires a principal.
 *
 *  **The client id, the tenant and the archive's scope are all three or none.** Two of the three is a
 *  build that sends the operator to a sign-in it cannot finish, and Entra reports that as an unknown
 *  resource rather than as the missing setting it is. All of these are public by nature — they travel
 *  in every authorization request the browser makes — so they arrive through `vars`, never `secrets`. */
export function entraConfig(env: ImportMetaEnv = import.meta.env): EntraConfig | null {
  const clientId = (env.VITE_ENTRA_CLIENT_ID as string | undefined)?.trim();
  const tenantId = (env.VITE_ENTRA_TENANT_ID as string | undefined)?.trim();
  const archive = (env.VITE_ENTRA_SCOPE_POLYMARKET as string | undefined)?.trim();
  const workbench = (env.VITE_ENTRA_SCOPE_WORKBENCH as string | undefined)?.trim();
  if (!clientId || !tenantId || !archive) return null;
  return { clientId, tenantId, scopes: { archive, workbench: workbench || null } };
}
