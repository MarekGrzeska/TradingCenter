/**
 * What the workbench's door made of the signed-in person (`GET /me`): their roles, from the token. The screens use it to
 * show only what would not be refused; every route enforces the same rule itself.
 */

import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient } from "../data/http";

export interface Me {
  roles: string[];
  person: string;
}

export interface AccessApi {
  me(signal: AbortSignal): Promise<Me>;
}

export function createAccessApi(base: string, identity: Identity = noIdentity): AccessApi {
  const http = jsonClient("workbench", { 403: "refused" }, identity);
  return { me: (signal) => http.json<Me>(`${base}/me`, { signal }) };
}
