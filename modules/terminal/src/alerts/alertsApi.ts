/**
 * Its own client rather than a route under another module's: the alerts package is a package behind a record of its own, and
 * its back end may not be there at all — a workbench without its database answers 404 to every route here, and the view says
 * so rather than showing an empty list of rules. Wire shapes stay in the generated contract; this maps them to dates and to the
 * names the screen uses. A refusal of a rule carries every field it was refused for (`RuleRefused`), so the form can put each
 * reason beside its field.
 */

import { noIdentity, type Identity } from "../auth/identity";
import type { components } from "../data/contract.alerts.generated";
import { jsonClient, statusMapper } from "../data/http";
import { MarketDataError } from "../data/types";

type Schemas = components["schemas"];

export type Comparison = Schemas["ConditionSource"]["comparison"];
export type FilterOp = Schemas["FilterTerm"]["op"];
export type Mode = Schemas["RuleIn"]["mode"];
export type FireState = Schemas["FireOut"]["state"];
export type CheckOutcome = Schemas["CheckOut"]["outcome"];

/** A value the tool surface is asked for, compared with a number. `threshold` stays text: it is what the operator typed. */
export interface ConditionSource {
  kind: "condition";
  toolName: string;
  arguments: Record<string, unknown>;
  fieldPath: string;
  comparison: Comparison;
  threshold: string;
  pollIntervalSeconds: number;
}

export interface FilterTerm {
  attribute: string;
  op: FilterOp;
  value: boolean | number | string | string[];
}

export interface EventSource {
  kind: "event";
  eventType: string;
  filter: FilterTerm[];
}

export type Source = ConditionSource | EventSource;

/** What the form submits, and what a draft is filled with. `null` where the package takes the default of the rule's kind. */
export interface RuleInput {
  name: string;
  source: Source;
  destination: string;
  /** The @name of the bot to tell through; `null` means the recipient's only bot. */
  bot: string | null;
  template: string;
  cooldownSeconds: number | null;
  mode: Mode;
  maxPerHour: number | null;
  enabled: boolean;
}

export interface Defect {
  field: string;
  message: string;
}

export interface Rule extends RuleInput {
  id: number;
  disabledReason: string | null;
  /** What is wrong with the rule now, that was not when it was written. */
  defects: Defect[];
  lastResult: boolean | null;
  lastCheckedAt: Date | null;
  lastFiredAt: Date | null;
  nextCheckAt: Date | null;
}

export interface CatalogTool {
  name: string;
  description: string;
  source: string;
  /** The tool's input schema, as the tool publishes it. */
  arguments: { properties?: Record<string, ArgumentSchema>; required?: string[] };
  /** The paths into its answer that hold a number — the only ones a rule can compare. */
  numberFields: string[];
}

export interface ArgumentSchema {
  type?: string | string[];
  description?: string;
  enum?: unknown[];
  default?: unknown;
  anyOf?: { type?: string }[];
}

export interface AttributeSchema {
  type?: string | string[];
  enum?: string[];
  items?: { type?: string };
  anyOf?: { type?: string }[];
  description?: string;
}

export interface CatalogEventType {
  name: string;
  description: string;
  attributes: Record<string, AttributeSchema>;
  /** Values a text attribute has had in the events kept, for the attributes with a handful worth choosing between. */
  seen: Record<string, string[]>;
}

export interface Recipient {
  name: string;
  bot: string;
  receives: boolean;
}

export interface Catalog {
  tools: CatalogTool[];
  eventTypes: CatalogEventType[];
  recipients: Recipient[];
  /** `false` when the process has no door to Telegram: rules can be written, and nothing is delivered. */
  gateway: boolean;
  minIntervalSeconds: number;
  /** The pairs the archive follows; empty where it cannot be asked. */
  symbols: string[];
  /** `false` without the package's own model key. */
  drafting: boolean;
}

export interface PackageState {
  rulesEnabled: number;
  rulesDisabled: number;
  rulesWithDefects: number;
  waitingFires: number;
  delivering: boolean;
  drafting: boolean;
  readingValues: boolean;
  clock: { ran: boolean; ageSeconds: number; expectedSeconds: number };
}

export interface Fire {
  at: Date;
  state: FireState;
  reason: string | null;
  text: string;
}

export interface Check {
  at: Date;
  outcome: CheckOutcome;
  reason: string;
}

export interface History {
  fires: Fire[];
  checks: Check[];
}

export interface Draft {
  understood: string;
  rule: RuleInput | null;
  defects: Defect[];
  notes: string[];
}

/** A rule the package would not take, with every reason at once. */
export class RuleRefused extends Error {
  readonly defects: Defect[];

  constructor(message: string, defects: Defect[]) {
    super(message);
    this.name = "RuleRefused";
    this.defects = defects;
  }
}

function mapSource(raw: Schemas["ConditionSource"] | Schemas["EventSource"]): Source {
  if (raw.kind === "condition") {
    return {
      kind: "condition",
      toolName: raw.tool_name,
      arguments: raw.arguments ?? {},
      fieldPath: raw.field_path,
      comparison: raw.comparison,
      threshold: raw.threshold,
      pollIntervalSeconds: raw.poll_interval_seconds,
    };
  }
  return {
    kind: "event",
    eventType: raw.event_type,
    filter: (raw.filter ?? []).map((term) => ({ attribute: term.attribute, op: term.op, value: term.value })),
  };
}

function sourceOnTheWire(source: Source): Schemas["ConditionSource"] | Schemas["EventSource"] {
  if (source.kind === "condition") {
    return {
      kind: "condition",
      tool_name: source.toolName,
      arguments: source.arguments,
      field_path: source.fieldPath,
      comparison: source.comparison,
      threshold: source.threshold,
      poll_interval_seconds: source.pollIntervalSeconds,
    };
  }
  return {
    kind: "event",
    event_type: source.eventType,
    filter: source.filter.map((term) => ({ attribute: term.attribute, op: term.op, value: term.value })),
  };
}

function inputOnTheWire(input: RuleInput): Schemas["RuleIn"] {
  return {
    name: input.name,
    source: sourceOnTheWire(input.source),
    destination: input.destination,
    bot: input.bot,
    template: input.template,
    cooldown_seconds: input.cooldownSeconds,
    mode: input.mode,
    max_per_hour: input.maxPerHour,
    enabled: input.enabled,
  };
}

function inputFromTheWire(raw: Schemas["RuleIn"]): RuleInput {
  return {
    name: raw.name,
    source: mapSource(raw.source),
    destination: raw.destination,
    bot: raw.bot ?? null,
    template: raw.template,
    cooldownSeconds: raw.cooldown_seconds ?? null,
    mode: raw.mode,
    maxPerHour: raw.max_per_hour ?? null,
    enabled: raw.enabled,
  };
}

function mapRule(raw: Schemas["RuleOut"]): Rule {
  return {
    id: raw.id,
    name: raw.name,
    source: mapSource(raw.source),
    destination: raw.destination,
    bot: raw.bot ?? null,
    template: raw.template,
    cooldownSeconds: raw.cooldown_seconds,
    mode: raw.mode,
    maxPerHour: raw.max_per_hour,
    enabled: raw.enabled,
    disabledReason: raw.disabled_reason,
    defects: raw.defects.map((one) => ({ field: one.field, message: one.message })),
    lastResult: raw.last_result,
    lastCheckedAt: raw.last_checked_at ? new Date(raw.last_checked_at) : null,
    lastFiredAt: raw.last_fired_at ? new Date(raw.last_fired_at) : null,
    nextCheckAt: raw.next_check_at ? new Date(raw.next_check_at) : null,
  };
}

/** The fields a refusal named, when it named any. The body is whatever the back end wrote, so its shape is checked. */
function defectsOf(problem: unknown): Defect[] {
  if (!problem || typeof problem !== "object" || !("defects" in problem)) return [];
  const raw = (problem as { defects: unknown }).defects;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((one): one is Defect => !!one && typeof one.field === "string" && typeof one.message === "string")
    .map((one) => ({ field: one.field, message: one.message }));
}

// 404 for a route that is not there (the package is absent from the workbench) and for a rule that is not there are told
// apart by the caller, which knows which it asked for. 422 is a rule that cannot work, with its reasons; 429, 501 and 503 are
// the draft's and the door's own refusals, each with words to show.
const mapStatus = statusMapper({
  404: "not-found",
  409: "refused",
  422: "refused",
  429: "refused",
  501: "refused",
  502: "upstream",
  503: "upstream",
});

export interface AlertsApi {
  state(signal: AbortSignal): Promise<PackageState>;
  catalog(signal: AbortSignal): Promise<Catalog>;
  rules(signal: AbortSignal): Promise<Rule[]>;
  history(id: number, signal: AbortSignal): Promise<History>;
  createRule(input: RuleInput, signal: AbortSignal): Promise<Rule>;
  replaceRule(id: number, input: RuleInput, signal: AbortSignal): Promise<Rule>;
  setEnabled(id: number, enabled: boolean, signal: AbortSignal): Promise<Rule>;
  deleteRule(id: number, signal: AbortSignal): Promise<void>;
  /** A proposal from a sentence — with `ruleId`, that rule as the sentence would change it. Nothing is stored; the rule
   * exists, or changes, only when the form is saved. */
  draft(sentence: string, signal: AbortSignal, ruleId?: number): Promise<Draft>;
}

export function createAlertsApi(httpBase: string, identity: Identity = noIdentity): AlertsApi {
  const http = jsonClient("alerts", mapStatus, identity);

  /** A refusal that names fields becomes `RuleRefused`; any other failure passes through as it came. */
  async function writing<T>(work: () => Promise<T>): Promise<T> {
    try {
      return await work();
    } catch (cause: unknown) {
      if (cause instanceof MarketDataError && cause.kind === "refused") {
        const defects = defectsOf(cause.problem);
        if (defects.length > 0) throw new RuleRefused(cause.message, defects);
      }
      throw cause;
    }
  }

  return {
    async state(signal) {
      const raw = await http.json<Schemas["StateOut"]>(`${httpBase}/state`, { signal });
      return {
        rulesEnabled: raw.rules_enabled,
        rulesDisabled: raw.rules_disabled,
        rulesWithDefects: raw.rules_with_defects,
        waitingFires: raw.waiting_fires,
        delivering: raw.delivering,
        drafting: raw.drafting,
        readingValues: raw.reading_values,
        clock: { ran: raw.clock.ran, ageSeconds: raw.clock.age_seconds, expectedSeconds: raw.clock.expected_seconds },
      };
    },

    async catalog(signal) {
      const raw = await http.json<Schemas["CatalogOut"]>(`${httpBase}/catalog`, { signal });
      return {
        tools: raw.tools.map((tool) => ({
          name: tool.name,
          description: tool.description,
          source: tool.source,
          arguments: tool.arguments as CatalogTool["arguments"],
          numberFields: tool.number_fields,
        })),
        eventTypes: raw.event_types.map((one) => ({
          name: one.name,
          description: one.description,
          attributes: ((one.schema as { properties?: Record<string, AttributeSchema> }).properties ?? {}) as Record<
            string,
            AttributeSchema
          >,
          seen: one.seen ?? {},
        })),
        recipients: raw.destinations.map((one) => ({ name: one.name, bot: one.bot, receives: one.receives })),
        gateway: raw.gateway,
        minIntervalSeconds: raw.min_interval_seconds,
        symbols: raw.symbols,
        drafting: raw.drafting,
      };
    },

    async rules(signal) {
      return (await http.json<Schemas["RuleOut"][]>(`${httpBase}/rules`, { signal })).map(mapRule);
    },

    async history(id, signal) {
      const raw = await http.json<Schemas["HistoryOut"]>(`${httpBase}/rules/${id}/history`, { signal });
      return {
        fires: raw.fires.map((one) => ({ at: new Date(one.at), state: one.state, reason: one.reason, text: one.text })),
        checks: raw.checks.map((one) => ({ at: new Date(one.at), outcome: one.outcome, reason: one.reason })),
      };
    },

    createRule(input, signal) {
      return writing(async () =>
        mapRule(
          await http.json<Schemas["RuleOut"]>(`${httpBase}/rules`, { signal, method: "POST", body: inputOnTheWire(input) }),
        ),
      );
    },

    replaceRule(id, input, signal) {
      return writing(async () =>
        mapRule(
          await http.json<Schemas["RuleOut"]>(`${httpBase}/rules/${id}`, { signal, method: "PUT", body: inputOnTheWire(input) }),
        ),
      );
    },

    async setEnabled(id, enabled, signal) {
      const body: Schemas["RulePatch"] = { enabled };
      return mapRule(await http.json<Schemas["RuleOut"]>(`${httpBase}/rules/${id}`, { signal, method: "PATCH", body }));
    },

    async deleteRule(id, signal) {
      await http.send(`${httpBase}/rules/${id}`, { signal, method: "DELETE" });
    },

    async draft(sentence, signal, ruleId) {
      const body: Schemas["DraftIn"] = ruleId === undefined ? { sentence } : { sentence, rule_id: ruleId };
      const raw = await http.json<Schemas["DraftOut"]>(`${httpBase}/drafts`, { signal, method: "POST", body });
      return {
        understood: raw.understood,
        rule: raw.rule ? inputFromTheWire(raw.rule) : null,
        defects: raw.defects.map((one) => ({ field: one.field, message: one.message })),
        notes: raw.notes,
      };
    },
  };
}
