/**
 * Who the workbench's door made of the signed-in person: their roles, from the token. A screen shows "no access" from it;
 * it enforces nothing — the door does, on every route.
 */

import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient, statusMapper } from "../data/http";

export interface Me {
  roles: string[];
  /** The person's directory object id; empty where there is no door. */
  person: string;
}

export interface AccessApi {
  me(signal: AbortSignal): Promise<Me>;
}

export function createAccessApi(httpBase: string, identity: Identity = noIdentity): AccessApi {
  const http = jsonClient("workbench", statusMapper({ 403: "refused" }), identity);
  return {
    me: (signal) => http.json<Me>(`${httpBase}/me`, { signal }),
  };
}

export const ADMIN_ROLE = "admin";
