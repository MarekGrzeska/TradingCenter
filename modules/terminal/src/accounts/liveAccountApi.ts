/**
 * The live account, read from the live account's own `capital-gateway` process (`capital-live-account`): one account,
 * its positions and working orders, and one write — close everything. Nothing else of the account is offered here;
 * orders on real money come from the operator's tools and the teams, held to the gateway's limits.
 */

import { noIdentity, type Identity } from "../auth/identity";
import { jsonClient, statusMapper } from "../data/http";
import type { AccountPosition, DemoAccount } from "./accountsApi";

export interface LiveWorkingOrder {
  id: string;
  symbol: string;
  direction: string;
  size: number;
  orderType: string;
  level: number | null;
}

export interface CloseAllItem {
  kind: "position" | "working_order";
  id: string;
  symbol: string | null;
  /** The gateway's word — CLOSED, CANCELLED, REJECTED, or PENDING when the outcome is not known. */
  status: string;
  reason: string | null;
}

export interface LiveAccountApi {
  listAccounts(signal: AbortSignal): Promise<DemoAccount[]>;
  listPositions(signal: AbortSignal): Promise<AccountPosition[]>;
  listWorkingOrders(signal: AbortSignal): Promise<LiveWorkingOrder[]>;
  /** Every position closed and every working order cancelled, each with its own outcome. */
  closeAll(signal: AbortSignal): Promise<CloseAllItem[]>;
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

interface RawWorkingOrder {
  id: string;
  symbol: string;
  direction: string;
  size: number;
  order_type: string;
  level?: number | null;
}

interface RawCloseAll {
  items: {
    kind: "position" | "working_order";
    id: string;
    symbol?: string | null;
    status: string;
    reason?: string | null;
  }[];
}

const mapStatus = statusMapper({ 403: "refused", 404: "not-found", 422: "refused" });

export function createLiveAccountApi(httpBase: string, identity: Identity = noIdentity): LiveAccountApi {
  const http = jsonClient("the live account's gateway", mapStatus, identity);

  return {
    async listAccounts(signal) {
      const raw = await http.json<RawAccount[]>(`${httpBase}/accounts`, { signal });
      return raw.map((account) => ({
        id: account.id,
        name: account.name,
        currency: account.currency,
        balance: account.balance,
        available: account.available,
        pnl: account.pnl,
        active: account.active === true,
      }));
    },

    async listPositions(signal) {
      const raw = await http.json<RawPosition[]>(`${httpBase}/positions`, { signal });
      return raw.map((position) => ({
        id: position.id,
        symbol: position.symbol,
        direction: position.direction,
        size: position.size,
        openLevel: position.open_level,
        pnl: position.pnl,
        currency: position.currency,
      }));
    },

    async listWorkingOrders(signal) {
      const raw = await http.json<RawWorkingOrder[]>(`${httpBase}/working-orders`, { signal });
      return raw.map((order) => ({
        id: order.id,
        symbol: order.symbol,
        direction: order.direction,
        size: order.size,
        orderType: order.order_type,
        level: order.level ?? null,
      }));
    },

    async closeAll(signal) {
      const raw = await http.json<RawCloseAll>(`${httpBase}/positions/close-all`, {
        method: "POST",
        signal,
      });
      return raw.items.map((item) => ({
        kind: item.kind,
        id: item.id,
        symbol: item.symbol ?? null,
        status: item.status,
        reason: item.reason ?? null,
      }));
    },
  };
}
