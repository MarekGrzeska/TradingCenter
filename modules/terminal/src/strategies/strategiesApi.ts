/**
 * The strategy engine's REST, under `/strategies` of the workbench — which may not have the package at all: then every route
 * answers 404 and the tab says so rather than showing no strategies. Wire shapes stay in the generated contract; this maps
 * them to dates and to the names the screen uses. A report stays in its wire shape: it is numbers under their own names,
 * and renaming forty of them would be a second contract to keep in step.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.strategies.generated";
import { jsonClient, statusMapper } from "../data/http";
import { MarketDataError } from "../data/types";

type Schemas = components["schemas"];

export type Report = Schemas["ReportOut"];
export type Language = Schemas["LanguageOut"];
export type Summary = Schemas["SummaryOut"];
export type Costs = Schemas["CostModel"];
export type RunStatus = Schemas["RunOut"]["status"];
export type Author = "operator" | "agent";

export interface Problem {
  path: string;
  message: string;
  column: number | null;
  hint: string | null;
}

export interface StrategyItem {
  id: number;
  name: string;
  symbol: string;
  timeframe: string;
  latestRevision: number;
  latestAuthor: Author;
  changedAt: Date;
  createdAt: Date;
  archivedAt: Date | null;
  trials: number;
}

export interface Revision {
  strategyId: number;
  n: number;
  document: Record<string, unknown>;
  author: Author;
  createdAt: Date;
  summary: Summary | null;
}

export interface RevisionEntry {
  n: number;
  author: Author;
  createdAt: Date;
}

export interface Change {
  path: string;
  kind: "added" | "removed" | "changed";
  before: unknown;
  after: unknown;
}

export interface Validation {
  valid: boolean;
  problems: Problem[];
  summary: Summary | null;
}

export interface Headline {
  trades: number | null;
  totalR: number | null;
  expectancyR: number | null;
  maxDrawdownR: number | null;
  sharpe: number | null;
}

export interface RunItem {
  id: number;
  revision: number;
  status: RunStatus;
  reason: string | null;
  requestedBy: Author;
  from: Date;
  to: Date;
  queuedAt: Date;
  headline: Headline | null;
}

export interface Run extends RunItem {
  engineVersion: number | null;
  request: Record<string, unknown>;
  report: Report | null;
  provenance: Record<string, unknown> | null;
}

export interface Trade {
  seq: number;
  side: "long" | "short";
  entryTime: Date;
  entryPrice: number;
  exitTime: Date;
  exitPrice: number;
  units: number;
  initialStop: number;
  resultR: number;
  resultMoney: number;
  costs: Record<string, number>;
  exitReason: Schemas["TradeOut"]["exit_reason"];
  pessimistic: boolean;
}

export interface RunRequest {
  strategyId: number;
  revision: number;
  from: Date;
  to: Date;
  params: Record<string, number>;
  costs: Costs;
  capital: number;
  seed: number;
}

/** A save that came too late: someone saved `latest` after the revision the edit was made to. */
export class SaveConflict extends Error {
  readonly latest: number;

  constructor(message: string, latest: number) {
    super(message);
    this.name = "SaveConflict";
    this.latest = latest;
  }
}

/** A refusal that names what is wrong, one problem per place, so the editor and the form can put each beside its place. */
export class Refused extends Error {
  readonly problems: Problem[];

  constructor(message: string, problems: Problem[]) {
    super(message);
    this.name = "Refused";
    this.problems = problems;
  }
}

export interface Health {
  queued: number;
  running: number;
  maxMinuteBars: number;
}

export interface StrategiesApi {
  /** 404 here means the workbench has no strategies package; the caller tells that from a failure. */
  health(signal: AbortSignal): Promise<Health>;
  language(signal: AbortSignal): Promise<Language>;
  strategies(archived: boolean, signal: AbortSignal): Promise<StrategyItem[]>;
  revision(strategyId: number, n: number | null, signal: AbortSignal): Promise<Revision>;
  revisions(strategyId: number, signal: AbortSignal): Promise<RevisionEntry[]>;
  changes(strategyId: number, n: number, signal: AbortSignal): Promise<Change[]>;
  validate(document: unknown, signal: AbortSignal): Promise<Validation>;
  create(document: unknown, signal: AbortSignal): Promise<{ strategyId: number; revision: number }>;
  save(
    strategyId: number,
    document: unknown,
    basedOn: number,
    signal: AbortSignal,
  ): Promise<{ revision: number; created: boolean }>;
  setArchived(strategyId: number, archived: boolean, signal: AbortSignal): Promise<void>;
  costs(symbol: string, signal: AbortSignal): Promise<Costs | null>;
  putCosts(symbol: string, costs: Costs, signal: AbortSignal): Promise<Costs>;
  runs(strategyId: number, signal: AbortSignal): Promise<RunItem[]>;
  run(id: number, signal: AbortSignal): Promise<Run>;
  trades(id: number, offset: number, limit: number, signal: AbortSignal): Promise<{ total: number; trades: Trade[] }>;
  enqueue(request: RunRequest, signal: AbortSignal): Promise<number>;
  cancel(id: number, signal: AbortSignal): Promise<void>;
}

const mapStatus = statusMapper({ 404: "not-found", 409: "refused", 422: "refused", 503: "upstream" });

function problemsOf(problem: unknown): Problem[] {
  const listed = (problem as { problems?: unknown } | undefined)?.problems;
  return Array.isArray(listed) ? (listed as Problem[]) : [];
}

function mapStrategy(raw: Schemas["StrategyOut"]): StrategyItem {
  return {
    id: raw.id,
    name: raw.name,
    symbol: raw.symbol,
    timeframe: raw.timeframe,
    latestRevision: raw.latest_revision,
    latestAuthor: raw.latest_author,
    changedAt: new Date(raw.changed_at),
    createdAt: new Date(raw.created_at),
    archivedAt: raw.archived_at ? new Date(raw.archived_at) : null,
    trials: raw.trials,
  };
}

function mapRevision(raw: Schemas["RevisionOut"]): Revision {
  return {
    strategyId: raw.strategy_id,
    n: raw.n,
    document: raw.document as Record<string, unknown>,
    author: raw.author,
    createdAt: new Date(raw.created_at),
    summary: raw.summary ?? null,
  };
}

function mapHeadline(raw: Schemas["HeadlineOut"] | null | undefined): Headline | null {
  if (!raw) return null;
  return {
    trades: raw.trades,
    totalR: raw.total_r,
    expectancyR: raw.expectancy_r,
    maxDrawdownR: raw.max_drawdown_r,
    sharpe: raw.sharpe,
  };
}

function rangeOf(request: Record<string, unknown>): { from: Date; to: Date } {
  return { from: new Date(String(request.from)), to: new Date(String(request.to)) };
}

function mapRunItem(raw: Schemas["RunSummaryOut"]): RunItem {
  return {
    id: raw.id,
    revision: raw.revision,
    status: raw.status,
    reason: raw.reason,
    requestedBy: raw.requested_by,
    ...rangeOf(raw.request as Record<string, unknown>),
    queuedAt: new Date(raw.queued_at),
    headline: mapHeadline(raw.headline),
  };
}

function mapRun(raw: Schemas["RunOut"]): Run {
  const report = raw.report ?? null;
  return {
    id: raw.id,
    revision: raw.revision,
    status: raw.status,
    reason: raw.reason,
    requestedBy: raw.requested_by,
    ...rangeOf(raw.request as Record<string, unknown>),
    queuedAt: new Date(raw.queued_at),
    headline: report
      ? mapHeadline({
          trades: report.trades,
          total_r: report.total_r,
          expectancy_r: report.expectancy_r,
          max_drawdown_r: report.max_drawdown_r,
          sharpe: report.sharpe,
        })
      : null,
    engineVersion: raw.engine_version,
    request: raw.request as Record<string, unknown>,
    report,
    provenance: (raw.provenance as Record<string, unknown> | null) ?? null,
  };
}

function mapTrade(raw: Schemas["TradeOut"]): Trade {
  return {
    seq: raw.seq,
    side: raw.side,
    entryTime: new Date(raw.entry_time),
    entryPrice: raw.entry_price,
    exitTime: new Date(raw.exit_time),
    exitPrice: raw.exit_price,
    units: raw.units,
    initialStop: raw.initial_stop,
    resultR: raw.result_r,
    resultMoney: raw.result_money,
    costs: raw.costs as Record<string, number>,
    exitReason: raw.exit_reason,
    pessimistic: raw.pessimistic,
  };
}

export function createStrategiesApi(httpBase: string, identity: Identity = noIdentity): StrategiesApi {
  const http = jsonClient("strategies", mapStatus, identity);

  /** A refusal that names problems becomes `Refused`, a 409 `SaveConflict`; anything else passes through as it came. */
  async function writing<T>(work: () => Promise<T>): Promise<T> {
    try {
      return await work();
    } catch (cause: unknown) {
      if (cause instanceof MarketDataError && cause.kind === "refused") {
        const latest = (cause.problem as { latest_revision?: unknown } | undefined)?.latest_revision;
        if (typeof latest === "number") throw new SaveConflict(cause.message, latest);
        const problems = problemsOf(cause.problem);
        if (problems.length > 0) throw new Refused(cause.message, problems);
      }
      throw cause;
    }
  }

  return {
    async health(signal) {
      const raw = await http.json<Schemas["HealthOut"]>(`${httpBase}/health`, { signal });
      return { queued: raw.queue.queued, running: raw.queue.running, maxMinuteBars: raw.max_minute_bars };
    },

    language: (signal) => http.json<Language>(`${httpBase}/language`, { signal }),

    async strategies(archived, signal) {
      const raw = await http.json<Schemas["StrategyOut"][]>(`${httpBase}/strategies?archived=${archived}`, { signal });
      return raw.map(mapStrategy);
    },

    async revision(strategyId, n, signal) {
      if (n === null) {
        const raw = await http.json<Schemas["StrategyDetailOut"]>(`${httpBase}/strategies/${strategyId}`, { signal });
        return mapRevision(raw.revision);
      }
      return mapRevision(
        await http.json<Schemas["RevisionOut"]>(`${httpBase}/strategies/${strategyId}/revisions/${n}`, { signal }),
      );
    },

    async revisions(strategyId, signal) {
      const raw = await http.json<Schemas["RevisionEntryOut"][]>(`${httpBase}/strategies/${strategyId}/revisions`, {
        signal,
      });
      return raw.map((one) => ({ n: one.n, author: one.author, createdAt: new Date(one.created_at) }));
    },

    async changes(strategyId, n, signal) {
      const raw = await http.json<Schemas["ChangesOut"]>(`${httpBase}/strategies/${strategyId}/revisions/${n}/changes`, {
        signal,
      });
      return raw.changes.map((one) => ({ path: one.path, kind: one.kind, before: one.before, after: one.after }));
    },

    async validate(document, signal) {
      const raw = await http.json<Schemas["ValidationOut"]>(`${httpBase}/validate`, { signal, method: "POST", body: document });
      return { valid: raw.valid, problems: raw.problems, summary: raw.summary ?? null };
    },

    create(document, signal) {
      return writing(async () => {
        const raw = await http.json<Schemas["SavedOut"]>(`${httpBase}/strategies`, { signal, method: "POST", body: document });
        return { strategyId: raw.strategy_id, revision: raw.revision };
      });
    },

    save(strategyId, document, basedOn, signal) {
      return writing(async () => {
        const raw = await http.json<Schemas["SavedOut"]>(
          `${httpBase}/strategies/${strategyId}/revisions?based_on=${basedOn}`,
          { signal, method: "POST", body: document },
        );
        return { revision: raw.revision, created: raw.created };
      });
    },

    async setArchived(strategyId, archived, signal) {
      await http.send(`${httpBase}/strategies/${strategyId}/${archived ? "archive" : "restore"}`, { signal, method: "POST" });
    },

    async costs(symbol, signal) {
      try {
        const raw = await http.json<Schemas["CostProfileOut"]>(`${httpBase}/costs/${encodeURIComponent(symbol)}`, { signal });
        return raw.costs;
      } catch (cause: unknown) {
        if (cause instanceof MarketDataError && cause.kind === "not-found") return null;
        throw cause;
      }
    },

    putCosts(symbol, costs, signal) {
      return writing(async () => {
        const raw = await http.json<Schemas["CostProfileOut"]>(`${httpBase}/costs/${encodeURIComponent(symbol)}`, {
          signal,
          method: "PUT",
          body: costs,
        });
        return raw.costs;
      });
    },

    async runs(strategyId, signal) {
      const raw = await http.json<Schemas["RunSummaryOut"][]>(`${httpBase}/runs?strategy_id=${strategyId}`, { signal });
      return raw.map(mapRunItem);
    },

    async run(id, signal) {
      return mapRun(await http.json<Schemas["RunOut"]>(`${httpBase}/runs/${id}`, { signal }));
    },

    async trades(id, offset, limit, signal) {
      const raw = await http.json<Schemas["TradesPageOut"]>(`${httpBase}/runs/${id}/trades?offset=${offset}&limit=${limit}`, {
        signal,
      });
      return { total: raw.total, trades: raw.trades.map(mapTrade) };
    },

    enqueue(request, signal) {
      return writing(async () => {
        const body = {
          strategy_id: request.strategyId,
          revision: request.revision,
          from: request.from.toISOString(),
          to: request.to.toISOString(),
          params: request.params,
          costs: request.costs,
          capital: request.capital,
          seed: request.seed,
        };
        const raw = await http.json<Schemas["RunAcceptedOut"]>(`${httpBase}/runs`, { signal, method: "POST", body });
        return raw.id;
      });
    },

    async cancel(id, signal) {
      await http.send(`${httpBase}/runs/${id}/cancel`, { signal, method: "POST" });
    },
  };
}
