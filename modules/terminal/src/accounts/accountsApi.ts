/**
 * The account, read straight from `capital-gateway`.
 *
 * Straight, and that is new: the gateway used to be unreachable from a browser, and the
 * one thing the terminal wanted from it — the instrument catalogue — came through
 * market-data. It still does. What this file reaches is the other half, the account, which
 * the gateway now opens to an authenticated browser and to nothing else it serves
 * (`capital_gateway/caller_access.py`).
 *
 * The credential is not here and must never be: the gateway's shared key belongs to the
 * modules that call it over the network. In development the dev server attaches it
 * (`vite.config.ts`); in production the browser's own token was meant to do the work.
 *
 * **In production it does not, and this screen has never read an account there.** The token is
 * sent, but the gateway's Easy Auth runs with `AllowAnonymous` — it cannot require a token,
 * because two modules call that app with a shared key and none — and under that setting it
 * validates nothing and forwards no principal, so the module refuses every browser request as
 * an unidentified caller. A 401 reaches this file as "you are signed out", which is what the
 * operator saw on 20 August 2026. `capital_gateway/caller_access.py` carries the measurement;
 * the fix is a change to the gateway's door, not to this file.
 */

import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient, statusMapper } from "../data/http";

export interface DemoAccount {
  id: string;
  name: string;
  currency: string;
  balance: number;
  available: number;
  pnl: number;
  /** The one orders act on. Exactly one account carries it. */
  active: boolean;
}

export interface AccountPosition {
  id: string;
  symbol: string;
  direction: string;
  size: number;
  openLevel: number | null;
  pnl: number | null;
  currency: string | null;
}

interface RawAccount {
  id: string;
  name: string;
  currency: string;
  balance: number;
  available: number;
  pnl: number;
  active?: boolean;
}

interface RawPosition {
  id: string;
  symbol: string;
  direction: string;
  size: number;
  open_level: number | null;
  pnl: number | null;
  currency: string | null;
}

function mapAccount(raw: RawAccount): DemoAccount {
  return {
    id: raw.id,
    name: raw.name,
    currency: raw.currency,
    balance: raw.balance,
    available: raw.available,
    pnl: raw.pnl,
    active: raw.active === true,
  };
}

function mapPosition(raw: RawPosition): AccountPosition {
  return {
    id: raw.id,
    symbol: raw.symbol,
    direction: raw.direction,
    size: raw.size,
    openLevel: raw.open_level,
    pnl: raw.pnl,
    currency: raw.currency,
  };
}

export interface AccountsApi {
  listAccounts(signal: AbortSignal): Promise<DemoAccount[]>;
  /** Open positions on the **active** account — the provider ties them to the session, so
   *  there is no such thing as "the positions of an account that is not active" to ask
   *  for. */
  listPositions(signal: AbortSignal): Promise<AccountPosition[]>;
  /** Makes another account active, and answers with it. Every later order acts on it, and
   *  the provider ends the quote stream when this succeeds. */
  switchAccount(accountId: string, signal: AbortSignal): Promise<DemoAccount>;
  /** Moves the demo balance by `amount` — negative takes funds away — and answers with the
   *  account after the move. A refusal carries the provider's own reason: the balance
   *  ceiling, the range of one adjustment, or the day's count. */
  topUp(amount: number, signal: AbortSignal): Promise<DemoAccount>;
}

// 403: the gateway recognised this caller and this path is not the caller's — which for
// this screen means a bug in it, not something the operator did. 422: the module read the
// request and declined it, an amount of zero being the one it declines by itself.
const mapStatus = statusMapper({ 403: "refused", 404: "not-found", 422: "refused" });

export function createAccountsApi(
  httpBase: string,
  identity: Identity = noIdentity,
): AccountsApi {
  const http = jsonClient("capital-gateway", mapStatus, identity);

  return {
    async listAccounts(signal) {
      const raw = await http.json<RawAccount[]>(`${httpBase}/accounts`, { signal });
      return raw.map(mapAccount);
    },

    async listPositions(signal) {
      const raw = await http.json<RawPosition[]>(`${httpBase}/positions`, { signal });
      return raw.map(mapPosition);
    },

    async switchAccount(accountId, signal) {
      const raw = await http.json<RawAccount>(`${httpBase}/accounts/active`, {
        method: "PUT",
        body: { account_id: accountId },
        signal,
      });
      return mapAccount(raw);
    },

    async topUp(amount, signal) {
      const raw = await http.json<RawAccount>(`${httpBase}/accounts/top-up`, {
        method: "POST",
        body: { amount },
        signal,
      });
      return mapAccount(raw);
    },
  };
}
