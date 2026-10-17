/**
 * Its own client rather than a route under another module's: the door to Telegram is a package behind a record of its own,
 * where this terminal's application is admitted beside the operator's `az`. Wire shapes stay in the generated contract; this
 * maps them to dates and to the names the screen uses. Nothing here ever holds a bot's token or the account's session: the
 * contract has nowhere to put one, and the only token that passes through is the one the operator pastes in (adopting a bot).
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.telegram.generated";
import { jsonClient, statusMapper } from "../data/http";

type Schemas = components["schemas"];

export type AccountStatus = Schemas["AccountOut"]["status"];
export type DestinationState = Schemas["DestinationOut"]["state"];

export interface Account {
  status: AccountStatus;
  username: string | null;
  /** Masked by the door: at most the last four digits. */
  phone: string | null;
  /** Why a stored account cannot be used; present with `needs_login`. */
  reason: string | null;
  /** Both are settings of the server; their absence is a supported configuration the screen names. */
  sessionKeyConfigured: boolean;
  apiCredentialsConfigured: boolean;
}

export interface GateState {
  account: Account;
  /** Creating, deleting and rotating would be attempted right now. */
  canCreateBots: boolean;
  bots: number;
  destinations: number;
  destinationsReady: number;
  defaultAssignment: boolean;
  /** Known purposes no assignment matches: collected and told to nobody. */
  purposesUnheard: number;
}

export interface Bot {
  username: string;
  title: string;
  createdHere: boolean;
}

export interface Destination {
  name: string;
  bot: string;
  state: DestinationState;
  receives: boolean;
  /** Who it is on Telegram, as Telegram reported it when the chat was bound; null until known. */
  username: string | null;
  title: string | null;
  kind: string | null;
}

export interface StartLink {
  destination: Destination;
  url: string;
  expiresAt: Date;
}

export interface Purpose {
  name: string;
  description: string | null;
  firstSeen: Date;
  lastSeen: Date;
  lastCaller: string | null;
  /** Who hears it today, or null when nobody does. */
  destination: string | null;
  /** The assignment key that decides it: the purpose itself, a prefix, or `*`. */
  assignedBy: string | null;
}

export interface Assignment {
  key: string;
  destination: string;
  bot: string;
  receives: boolean;
}

/** Where Telegram said the login code went. `app` is a message from "Telegram" in an app already logged in to the account. */
export type CodeDelivery = Schemas["LoginStepOut"]["delivery"] extends infer D ? Exclude<D, null | undefined> : never;

export type LoginStep =
  | { step: "code"; delivery: CodeDelivery | null; canResend: boolean }
  | { step: "password" }
  | { step: "done"; account: Account };

/** A login by QR code, as the door reports it while the code is on screen. */
export interface QrLogin {
  status: Schemas["QrLoginOut"]["status"];
  /** `tg://login?token=…` — drawn as a QR code; changes about every half minute. */
  url: string | null;
  account: Account | null;
  reason: string | null;
}

function mapAccount(raw: Schemas["AccountOut"]): Account {
  return {
    status: raw.status,
    username: raw.username ?? null,
    phone: raw.phone ?? null,
    reason: raw.reason ?? null,
    sessionKeyConfigured: raw.session_key_configured,
    apiCredentialsConfigured: raw.api_credentials_configured,
  };
}

function mapDestination(raw: Schemas["DestinationOut"]): Destination {
  return {
    name: raw.name,
    bot: raw.bot,
    state: raw.state,
    receives: raw.receives,
    username: raw.username ?? null,
    title: raw.title ?? null,
    kind: raw.kind ?? null,
  };
}

function mapBot(raw: Schemas["BotOut"]): Bot {
  return { username: raw.username, title: raw.title, createdHere: raw.created_here };
}

// 409 is the door declining on purpose (an assignment still points here, a login not in progress, Telegram's own "no") and
// 501 is a setting it names; both are reasons the operator can act on, so both read as a refusal with the door's words.
const mapStatus = statusMapper({ 404: "not-found", 409: "refused", 422: "refused", 501: "refused", 502: "upstream" });

export interface TelegramApi {
  state(signal: AbortSignal): Promise<GateState>;
  loginStart(phone: string, signal: AbortSignal): Promise<LoginStep>;
  loginCode(code: string, signal: AbortSignal): Promise<LoginStep>;
  /** A login with no code at all: an app logged in to the account scans the QR code this returns. */
  loginQrStart(signal: AbortSignal): Promise<QrLogin>;
  loginQrState(signal: AbortSignal): Promise<QrLogin>;
  /** The code did not come: Telegram's next way of delivering it (app → SMS → call), on the same login. */
  loginResend(signal: AbortSignal): Promise<LoginStep>;
  loginPassword(password: string, signal: AbortSignal): Promise<LoginStep>;
  /** `true` when Telegram was told; `false` when only this side forgot, and the device should be ended from the phone. */
  logout(signal: AbortSignal): Promise<boolean>;
  bots(signal: AbortSignal): Promise<Bot[]>;
  adoptBot(token: string, signal: AbortSignal): Promise<Bot>;
  createBot(title: string, username: string, signal: AbortSignal): Promise<Bot>;
  rotateBot(username: string, signal: AbortSignal): Promise<Bot>;
  removeBot(username: string, signal: AbortSignal): Promise<void>;
  destinations(signal: AbortSignal): Promise<Destination[]>;
  offerDestination(name: string, bot: string, signal: AbortSignal): Promise<StartLink>;
  removeDestination(name: string, signal: AbortSignal): Promise<void>;
  purposes(signal: AbortSignal): Promise<Purpose[]>;
  assignments(signal: AbortSignal): Promise<Assignment[]>;
  assign(key: string, destination: string, signal: AbortSignal): Promise<Assignment>;
  unassign(key: string, signal: AbortSignal): Promise<void>;
}

export function createTelegramApi(httpBase: string, identity: Identity = noIdentity): TelegramApi {
  const http = jsonClient("telegram", mapStatus, identity);
  const segment = encodeURIComponent;

  function qr(raw: Schemas["QrLoginOut"]): QrLogin {
    return {
      status: raw.status,
      url: raw.url ?? null,
      account: raw.account ? mapAccount(raw.account) : null,
      reason: raw.reason ?? null,
    };
  }

  function step(raw: Schemas["LoginStepOut"]): LoginStep {
    if (raw.step === "done" && raw.account) return { step: "done", account: mapAccount(raw.account) };
    return raw.step === "password" ? { step: "password" } : { step: "code", delivery: raw.delivery ?? null, canResend: raw.can_resend ?? true };
  }

  return {
    async state(signal) {
      const raw = await http.json<Schemas["StateOut"]>(`${httpBase}/state`, { signal });
      return {
        account: mapAccount(raw.account),
        canCreateBots: raw.can_create_bots,
        bots: raw.bots,
        destinations: raw.destinations,
        destinationsReady: raw.destinations_ready,
        defaultAssignment: raw.default_assignment,
        purposesUnheard: raw.purposes_unheard,
      };
    },

    async loginStart(phone, signal) {
      const body: Schemas["LoginStartRequest"] = { phone };
      return step(await http.json<Schemas["LoginStepOut"]>(`${httpBase}/account/login`, { signal, method: "POST", body }));
    },

    async loginCode(code, signal) {
      const body: Schemas["LoginCodeRequest"] = { code };
      return step(
        await http.json<Schemas["LoginStepOut"]>(`${httpBase}/account/login/code`, { signal, method: "POST", body }),
      );
    },

    async loginQrStart(signal) {
      return qr(await http.json<Schemas["QrLoginOut"]>(`${httpBase}/account/login/qr`, { signal, method: "POST" }));
    },

    async loginQrState(signal) {
      return qr(await http.json<Schemas["QrLoginOut"]>(`${httpBase}/account/login/qr`, { signal }));
    },

    async loginResend(signal) {
      return step(await http.json<Schemas["LoginStepOut"]>(`${httpBase}/account/login/resend`, { signal, method: "POST" }));
    },

    async loginPassword(password, signal) {
      const body: Schemas["LoginPasswordRequest"] = { password };
      return step(
        await http.json<Schemas["LoginStepOut"]>(`${httpBase}/account/login/password`, { signal, method: "POST", body }),
      );
    },

    async logout(signal) {
      const raw = await http.json<Schemas["LogoutOut"]>(`${httpBase}/account`, { signal, method: "DELETE" });
      return raw.ended_at_telegram;
    },

    async bots(signal) {
      return (await http.json<Schemas["BotOut"][]>(`${httpBase}/bots`, { signal })).map(mapBot);
    },

    async adoptBot(token, signal) {
      const body: Schemas["AdoptBotRequest"] = { token };
      return mapBot(await http.json<Schemas["BotOut"]>(`${httpBase}/bots/adopted`, { signal, method: "POST", body }));
    },

    async createBot(title, username, signal) {
      const body: Schemas["NewBotRequest"] = { title, username };
      return mapBot(await http.json<Schemas["BotOut"]>(`${httpBase}/bots/created`, { signal, method: "POST", body }));
    },

    async rotateBot(username, signal) {
      return mapBot(
        await http.json<Schemas["BotOut"]>(`${httpBase}/bots/${segment(username)}/token`, { signal, method: "POST" }),
      );
    },

    async removeBot(username, signal) {
      await http.send(`${httpBase}/bots/${segment(username)}`, { signal, method: "DELETE" });
    },

    async destinations(signal) {
      return (await http.json<Schemas["DestinationOut"][]>(`${httpBase}/destinations`, { signal })).map(mapDestination);
    },

    async offerDestination(name, bot, signal) {
      const body: Schemas["NewDestinationRequest"] = { name, bot };
      const raw = await http.json<Schemas["StartLinkOut"]>(`${httpBase}/destinations`, { signal, method: "POST", body });
      return {
        destination: mapDestination(raw.destination),
        url: raw.start_link,
        expiresAt: new Date(Date.now() + raw.expires_in_seconds * 1000),
      };
    },

    async removeDestination(name, signal) {
      await http.send(`${httpBase}/destinations/${segment(name)}`, { signal, method: "DELETE" });
    },

    async purposes(signal) {
      const raw = await http.json<Schemas["PurposeOut"][]>(`${httpBase}/purposes`, { signal });
      return raw.map((one) => ({
        name: one.name,
        description: one.description ?? null,
        firstSeen: new Date(one.first_seen),
        lastSeen: new Date(one.last_seen),
        lastCaller: one.last_caller ?? null,
        destination: one.destination ?? null,
        assignedBy: one.assigned_by ?? null,
      }));
    },

    async assignments(signal) {
      const raw = await http.json<Schemas["AssignmentOut"][]>(`${httpBase}/assignments`, { signal });
      return raw.map((one) => ({ key: one.key, destination: one.destination, bot: one.bot, receives: one.receives }));
    },

    async assign(key, destination, signal) {
      const body: Schemas["AssignRequest"] = { destination };
      const raw = await http.json<Schemas["AssignmentOut"]>(`${httpBase}/assignments/${segment(key)}`, {
        signal,
        method: "PUT",
        body,
      });
      return { key: raw.key, destination: raw.destination, bot: raw.bot, receives: raw.receives };
    },

    async unassign(key, signal) {
      await http.send(`${httpBase}/assignments/${segment(key)}`, { signal, method: "DELETE" });
    },
  };
}
