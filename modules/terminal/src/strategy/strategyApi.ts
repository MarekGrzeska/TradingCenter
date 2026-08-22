/**
 * The strategy platform, read straight from `strategy`.
 *
 * Its own client rather than a route under the archive's: a different App Service behind a
 * different gate, so it carries a token minted for **its** audience and nobody else's
 * (specs/terminal-identity). The wire types come from `contract.strategy.generated.ts`,
 * generated from that module's own Pydantic models — this file maps them to what the views
 * want and is the only place the two shapes meet.
 *
 * **Most of what this reads is a refusal.** A strategy worth running says no to the large
 * majority of the bars it sees, so `listDecisions` is not a feed of opportunities; it is
 * the record that answers "why has nothing happened". `reasonKind` travels with every
 * refusal because the three kinds have three different answers — fetch history, read the
 * strategy, or raise a limit — and a view that flattened them into "no signal" would send
 * somebody the wrong way.
 *
 * **Nothing here can move an account.** The module has no route that does, by design, so
 * there is no call to write and none to guard against.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.strategy.generated";
import { jsonClient, statusMapper } from "../data/http";

type Schemas = components["schemas"];

// --- what the views work in -----------------------------------------------------------

/** Which layer said no. `null` on a decision that is not a refusal. */
export type ReasonKind = "strategy" | "coverage" | "limit";

export interface Param {
  name: string;
  type: "int" | "float";
  default: number;
  min: number;
  max: number;
}

export interface Fact {
  key: string;
  indicator: string;
  resolution: string;
  /** A value is a number, or the name of one of this strategy's own parameters — which is
   *  what lets a period be tuned without the declaration stopping being a declaration. */
  params: Record<string, number | string>;
  bars: number;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  /** The bars whose closes drive evaluation. */
  resolution: string;
  candles: number;
  facts: Fact[];
  params: Param[];
}

export interface Watch {
  id: number;
  strategyId: string;
  symbol: string;
  parameterSetId: number;
  active: boolean;
  createdAt: Date;
}

export interface ParameterSet {
  id: number;
  strategyId: string;
  version: number;
  params: Record<string, number>;
  createdAt: Date;
}

export interface Decision {
  id: number;
  strategyId: string;
  symbol: string;
  parameterSetId: number;
  /** The closing time of the bar decided on, never a wall clock. */
  asOf: Date;
  action: "trade" | "no_trade";
  reason: string | null;
  reasonKind: ReasonKind | null;
  direction: "long" | "short" | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  /** Reward over risk, computed by the module from the levels. */
  rr: number | null;
  score: number | null;
  features: Record<string, number>;
  createdAt: Date;
}

export interface DecisionDetail extends Decision {
  /** The readings this decision stood on — enough to re-decide it without the archive. */
  facts: Record<string, unknown>;
}

export interface BacktestRun {
  id: number;
  strategyId: string;
  symbol: string;
  resolution: string;
  rangeFrom: Date;
  rangeTo: Date;
  params: Record<string, number>;
  /** Named rather than assumed: a report without its cost model is not a result. */
  costs: Record<string, number>;
  report: Record<string, unknown>;
  ranAt: Date;
}

// --- wire to view ---------------------------------------------------------------------

function mapStrategy(raw: Schemas["StrategyOut"]): Strategy {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description,
    resolution: raw.resolution,
    candles: raw.candles,
    facts: raw.facts.map((fact) => ({
      key: fact.key,
      indicator: fact.indicator,
      resolution: fact.resolution,
      params: fact.params,
      bars: fact.bars,
    })),
    params: raw.params.map((param) => ({
      name: param.name,
      type: param.type,
      default: param.default,
      min: param.min,
      max: param.max,
    })),
  };
}

function mapWatch(raw: Schemas["WatchOut"]): Watch {
  return {
    id: raw.id,
    strategyId: raw.strategy_id,
    symbol: raw.symbol,
    parameterSetId: raw.parameter_set_id,
    active: raw.active,
    createdAt: new Date(raw.created_at),
  };
}

function mapParameterSet(raw: Schemas["ParameterSetOut"]): ParameterSet {
  return {
    id: raw.id,
    strategyId: raw.strategy_id,
    version: raw.version,
    params: raw.params,
    createdAt: new Date(raw.created_at),
  };
}

function mapDecision(raw: Schemas["DecisionOut"]): Decision {
  return {
    id: raw.id,
    strategyId: raw.strategy_id,
    symbol: raw.symbol,
    parameterSetId: raw.parameter_set_id,
    asOf: new Date(raw.as_of),
    action: raw.action,
    reason: raw.reason,
    reasonKind: raw.reason_kind,
    direction: raw.direction,
    entry: raw.entry,
    stop: raw.stop,
    target: raw.target,
    rr: raw.rr,
    score: raw.score,
    features: raw.features,
    createdAt: new Date(raw.created_at),
  };
}

function mapBacktestRun(raw: Schemas["BacktestRunOut"]): BacktestRun {
  return {
    id: raw.id,
    strategyId: raw.strategy_id,
    symbol: raw.symbol,
    resolution: raw.resolution,
    rangeFrom: new Date(raw.range_from),
    rangeTo: new Date(raw.range_to),
    params: raw.params,
    costs: raw.costs,
    report: raw.report,
    ranAt: new Date(raw.ran_at),
  };
}

// --- the client -----------------------------------------------------------------------

/**
 * What each refusal means here.
 *
 * 403 is `refused` rather than a sign-in problem, and that is the distinction this module
 * makes and the platform cannot: a caller Easy Auth admitted may still have no business on
 * the REST contract, because the gate authorizes an application and not a route
 * (`strategy/caller_access.py`). 401 is not in this table and cannot be — `jsonClient`
 * turns it into a lost session before a mapper is reached.
 *
 * 422 covers both a parameter outside its declared range and a strategy this image does not
 * carry: understood, declined, and unchanged on a retry. 504 is the archive being
 * unreachable *from the module* — the module says so rather than pretending it saw nothing,
 * and it is the one status here worth trying again.
 */
const mapStatus = statusMapper({
  403: "refused",
  404: "not-found",
  422: "refused",
  502: "upstream",
  504: "upstream",
});

export interface DecisionQuery {
  strategyId?: string;
  symbol?: string;
  /** Left out on purpose by default: the refusals are the content of this screen. */
  action?: "trade" | "no_trade";
  limit?: number;
}

export interface StrategyApi {
  listStrategies(signal: AbortSignal): Promise<Strategy[]>;
  readStrategy(strategyId: string, signal: AbortSignal): Promise<Strategy>;
  listWatches(signal: AbortSignal, activeOnly?: boolean): Promise<Watch[]>;
  /** Starts watching a pair. Omitting `params` has the module write a set from the
   *  strategy's own defaults, resolved — which is what gets stored either way. */
  startWatch(
    strategyId: string,
    symbol: string,
    signal: AbortSignal,
    params?: Record<string, number>,
  ): Promise<Watch>;
  /** Stops or resumes evaluation of one pair. **No decision is deleted** — what the
   *  platform decided stays readable after it stops watching. */
  setWatchActive(watchId: number, active: boolean, signal: AbortSignal): Promise<Watch>;
  listParameterSets(signal: AbortSignal, strategyId?: string): Promise<ParameterSet[]>;
  addParameterSet(
    strategyId: string,
    params: Record<string, number>,
    signal: AbortSignal,
  ): Promise<ParameterSet>;
  /** Newest first, refusals included. */
  listDecisions(signal: AbortSignal, query?: DecisionQuery): Promise<Decision[]>;
  readDecision(decisionId: number, signal: AbortSignal): Promise<DecisionDetail>;
  listBacktests(signal: AbortSignal, strategyId?: string): Promise<BacktestRun[]>;
  readBacktest(runId: number, signal: AbortSignal): Promise<BacktestRun>;
}

export function createStrategyApi(
  httpBase: string,
  identity: Identity = noIdentity,
): StrategyApi {
  const http = jsonClient("strategy", mapStatus, identity);

  return {
    async listStrategies(signal) {
      const raw = await http.json<Schemas["StrategyOut"][]>(`${httpBase}/strategies`, { signal });
      return raw.map(mapStrategy);
    },

    async readStrategy(strategyId, signal) {
      const raw = await http.json<Schemas["StrategyOut"]>(
        `${httpBase}/strategies/${encodeURIComponent(strategyId)}`,
        { signal },
      );
      return mapStrategy(raw);
    },

    async listWatches(signal, activeOnly) {
      const suffix = activeOnly === undefined ? "" : `?active_only=${String(activeOnly)}`;
      const raw = await http.json<Schemas["WatchOut"][]>(`${httpBase}/watches${suffix}`, {
        signal,
      });
      return raw.map(mapWatch);
    },

    async startWatch(strategyId, symbol, signal, params) {
      // Two requests when parameters were given, one when they were not — and the module
      // is what resolves them either way. Sending a set of its own defaults from here
      // would be this file holding an opinion about values it does not own.
      let parameterSetId: number | undefined;
      if (params !== undefined) {
        const written = await http.json<Schemas["ParameterSetOut"]>(
          `${httpBase}/parameter-sets`,
          { signal, method: "POST", body: { strategy_id: strategyId, params } },
        );
        parameterSetId = written.id;
      }
      const raw = await http.json<Schemas["WatchOut"]>(`${httpBase}/watches`, {
        signal,
        method: "POST",
        body: {
          strategy_id: strategyId,
          symbol,
          ...(parameterSetId === undefined ? {} : { parameter_set_id: parameterSetId }),
        },
      });
      return mapWatch(raw);
    },

    async setWatchActive(watchId, active, signal) {
      const raw = await http.json<Schemas["WatchOut"]>(`${httpBase}/watches/${watchId}`, {
        signal,
        method: "PATCH",
        body: { active },
      });
      return mapWatch(raw);
    },

    async listParameterSets(signal, strategyId) {
      const suffix =
        strategyId === undefined ? "" : `?strategy_id=${encodeURIComponent(strategyId)}`;
      const raw = await http.json<Schemas["ParameterSetOut"][]>(
        `${httpBase}/parameter-sets${suffix}`,
        { signal },
      );
      return raw.map(mapParameterSet);
    },

    async addParameterSet(strategyId, params, signal) {
      const raw = await http.json<Schemas["ParameterSetOut"]>(`${httpBase}/parameter-sets`, {
        signal,
        method: "POST",
        body: { strategy_id: strategyId, params },
      });
      return mapParameterSet(raw);
    },

    async listDecisions(signal, query) {
      const search = new URLSearchParams();
      if (query?.strategyId !== undefined) search.set("strategy_id", query.strategyId);
      if (query?.symbol !== undefined) search.set("symbol", query.symbol);
      // Only when asked for. Absent means "both kinds", which is the default this screen
      // wants: a list of setups alone is empty on exactly the days somebody is asking why.
      if (query?.action !== undefined) search.set("action", query.action);
      if (query?.limit !== undefined) search.set("limit", String(query.limit));
      const suffix = search.size === 0 ? "" : `?${search}`;
      const raw = await http.json<Schemas["DecisionOut"][]>(`${httpBase}/decisions${suffix}`, {
        signal,
      });
      return raw.map(mapDecision);
    },

    async readDecision(decisionId, signal) {
      const raw = await http.json<Schemas["DecisionDetailOut"]>(
        `${httpBase}/decisions/${decisionId}`,
        { signal },
      );
      return { ...mapDecision(raw), facts: raw.facts };
    },

    async listBacktests(signal, strategyId) {
      const suffix =
        strategyId === undefined ? "" : `?strategy_id=${encodeURIComponent(strategyId)}`;
      const raw = await http.json<Schemas["BacktestRunOut"][]>(
        `${httpBase}/backtests${suffix}`,
        { signal },
      );
      return raw.map(mapBacktestRun);
    },

    async readBacktest(runId, signal) {
      const raw = await http.json<Schemas["BacktestRunOut"]>(`${httpBase}/backtests/${runId}`, {
        signal,
      });
      return mapBacktestRun(raw);
    },
  };
}
