/**
 * The account, read straight from `capital-gateway` — the half it opens to an authenticated browser. The credential is
 * not here and must never be: for its first days the gateway's Easy Auth forwarded no principal, which read as signed out.
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
  /** Open positions on `accountId`, or on the active account when it is null. Naming one never makes it active:
   *  the gateway keeps a session per account. */
  listPositions(signal: AbortSignal, accountId?: string | null): Promise<AccountPosition[]>;
  /** Makes another account active, and answers with it. Every later order naming no account acts on it. */
  switchAccount(accountId: string, signal: AbortSignal): Promise<DemoAccount>;
  /** Moves the balance of `accountId` (or of the active one) by `amount` — negative takes funds away — and answers
   *  with the account after. A refusal carries the provider's own reason. */
  topUp(amount: number, signal: AbortSignal, accountId?: string | null): Promise<DemoAccount>;
}

// 403: the gateway recognised this caller and this path is not the caller's, which for this screen means a
// bug in it. 422: the module read the request and declined it, an amount of zero being the one it declines.
const mapStatus = statusMapper({ 403: "refused", 404: "not-found", 422: "refused" });

/** The gateway's name for "act on this account"; absent, it acts on the active one. */
const ACCOUNT_HEADER = "X-Capital-Account";

function onAccount(accountId: string | null | undefined): Record<string, string> {
  return accountId ? { [ACCOUNT_HEADER]: accountId } : {};
}

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

    async listPositions(signal, accountId) {
      const raw = await http.json<RawPosition[]>(`${httpBase}/positions`, {
        signal,
        headers: onAccount(accountId),
      });
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

    async topUp(amount, signal, accountId) {
      const raw = await http.json<RawAccount>(`${httpBase}/accounts/top-up`, {
        method: "POST",
        body: { amount },
        signal,
        headers: onAccount(accountId),
      });
      return mapAccount(raw);
    },
  };
}
