import type {
  ArgumentSchema,
  AttributeSchema,
  Catalog,
  CatalogEventType,
  CatalogTool,
  Comparison,
  Defect,
  FilterOp,
  FilterTerm,
  Mode,
  Rule,
  RuleInput,
  Source,
} from "./alertsApi";

/**
 * Words and shapes for the Alerts tab, kept out of the components so the rules about what a form may offer are testable
 * without drawing one. Everything the form lets an operator choose comes from the catalogue; what is typed is a name, a
 * number, a template, and a value the catalogue has not seen yet.
 */

export const COMPARISON_LABEL: Record<Comparison, string> = {
  gt: "powyżej",
  gte: "co najmniej",
  lt: "poniżej",
  lte: "co najwyżej",
  eq: "równa się",
};

export const OP_LABEL: Record<FilterOp, string> = {
  eq: "jest",
  ne: "nie jest",
  in: "jest jednym z",
  gt: "większe niż",
  gte: "co najmniej",
  lt: "mniejsze niż",
  lte: "co najwyżej",
  contains: "zawiera",
};

export type AttributeKind = "string" | "number" | "boolean" | "array";

/** The one type an attribute has once `null` is set aside, in the four the filter knows. */
export function attributeKind(schema: AttributeSchema | undefined): AttributeKind | null {
  if (!schema) return null;
  const declared = Array.isArray(schema.type) ? schema.type.find((one) => one !== "null") : schema.type;
  const named = declared ?? schema.anyOf?.map((one) => one.type).find((one) => one && one !== "null");
  if (named === "string") return "string";
  if (named === "number" || named === "integer") return "number";
  if (named === "boolean") return "boolean";
  if (named === "array") return "array";
  return null;
}

const OPS: Record<AttributeKind, FilterOp[]> = {
  string: ["eq", "ne", "in"],
  number: ["eq", "ne", "gt", "gte", "lt", "lte", "in"],
  boolean: ["eq", "ne"],
  array: ["contains"],
};

/** The comparisons an attribute of this kind can take — the same table the back end refuses by. */
export function opsFor(kind: AttributeKind | null): FilterOp[] {
  return kind === null ? [] : OPS[kind];
}

export function describeSource(source: Source): string {
  if (source.kind === "condition") {
    const given = Object.entries(source.arguments)
      .map(([name, value]) => `${name}=${String(value)}`)
      .join(", ");
    return `${source.toolName}(${given}).${source.fieldPath} ${COMPARISON_LABEL[source.comparison]} ${source.threshold} · co ${source.pollIntervalSeconds} s`;
  }
  const terms = source.filter.map(describeTerm).join(" i ");
  return `${source.eventType}${terms ? ` — gdy ${terms}` : " — każde"}`;
}

export function describeTerm(term: FilterTerm): string {
  const value = Array.isArray(term.value) ? term.value.join(", ") : String(term.value);
  return `${term.attribute} ${OP_LABEL[term.op]} ${value}`;
}

export interface Status {
  label: string;
  tone: "ok" | "warning" | "critical" | "muted";
}

/** What one line can say about a rule: switched off and why, wrong and how, or working — and, for a value rule, whether
 *  its last look could tell. A rule that cannot read its value is quiet for a reason that is not the market's. */
export function statusOf(rule: Rule): Status {
  if (!rule.enabled) return { label: rule.disabledReason ? `wyłączona — ${rule.disabledReason}` : "wyłączona", tone: "muted" };
  if (rule.defects.length > 0) return { label: "ma wadę — nie zadziała tak, jak ją zapisano", tone: "critical" };
  if (rule.source.kind === "condition") {
    if (rule.lastCheckedAt === null) return { label: "jeszcze nie sprawdzona", tone: "muted" };
    if (rule.lastResult === null) return { label: "nie może odczytać wartości", tone: "warning" };
  }
  return { label: "działa", tone: "ok" };
}

export function defectsFor(defects: Defect[], field: string): Defect[] {
  return defects.filter((one) => one.field === field || one.field.startsWith(`${field}.`));
}

// --- the arguments of a tool, from the schema the tool published ---------------------------------------------------------

export interface ArgumentField {
  name: string;
  required: boolean;
  description: string;
  kind: "symbol" | "text" | "number" | "choice";
  choices: string[];
}

function argumentType(schema: ArgumentSchema): string | undefined {
  const declared = Array.isArray(schema.type) ? schema.type.find((one) => one !== "null") : schema.type;
  return declared ?? schema.anyOf?.map((one) => one.type).find((one) => one && one !== "null");
}

/** The fields a tool's arguments make: an instrument is chosen among those the archive follows, an enumeration among its
 *  values, a number is a number, and anything else is the text it is. */
export function argumentFields(tool: CatalogTool | undefined, symbols: string[]): ArgumentField[] {
  if (!tool) return [];
  const required = new Set(tool.arguments.required ?? []);
  return Object.entries(tool.arguments.properties ?? {}).map(([name, schema]) => {
    const choices = Array.isArray(schema.enum) ? schema.enum.map(String) : [];
    const type = argumentType(schema);
    const kind: ArgumentField["kind"] =
      name === "symbol" && symbols.length > 0
        ? "symbol"
        : choices.length > 0
          ? "choice"
          : type === "integer" || type === "number"
            ? "number"
            : "text";
    return {
      name,
      required: required.has(name),
      description: schema.description ?? "",
      kind,
      choices: kind === "symbol" ? symbols : choices,
    };
  });
}

// --- the form ----------------------------------------------------------------------------------------------------------

export interface TermForm {
  attribute: string;
  op: FilterOp;
  /** What the operator chose or typed; turned into the attribute's own type when the rule is built. */
  value: string;
  /** For `in` over values the catalogue has seen: the ones ticked. */
  picked: string[];
}

export interface RuleForm {
  name: string;
  kind: "condition" | "event";
  tool: string;
  args: Record<string, string>;
  fieldPath: string;
  comparison: Comparison;
  threshold: string;
  interval: string;
  eventType: string;
  terms: TermForm[];
  destination: string;
  template: string;
  cooldown: string;
  mode: Mode;
  maxPerHour: string;
  enabled: boolean;
}

export function blankForm(catalog: Catalog): RuleForm {
  const tool = catalog.tools[0];
  return {
    name: "",
    kind: catalog.tools.length > 0 || catalog.eventTypes.length === 0 ? "condition" : "event",
    tool: tool?.name ?? "",
    args: {},
    fieldPath: tool?.numberFields[0] ?? "",
    comparison: "gt",
    threshold: "",
    interval: String(Math.max(catalog.minIntervalSeconds, 60)),
    eventType: catalog.eventTypes[0]?.name ?? "",
    terms: [],
    destination: catalog.recipients.find((one) => one.receives)?.name ?? catalog.recipients[0]?.name ?? "",
    template: "",
    cooldown: "",
    mode: "repeat",
    maxPerHour: "",
    enabled: true,
  };
}

export function formFrom(input: RuleInput, catalog: Catalog): RuleForm {
  const blank = blankForm(catalog);
  const common = {
    name: input.name,
    destination: input.destination,
    template: input.template,
    cooldown: input.cooldownSeconds === null ? "" : String(input.cooldownSeconds),
    mode: input.mode,
    maxPerHour: input.maxPerHour === null ? "" : String(input.maxPerHour),
    enabled: input.enabled,
  };
  if (input.source.kind === "condition") {
    const source = input.source;
    return {
      ...blank,
      ...common,
      kind: "condition",
      tool: source.toolName,
      args: Object.fromEntries(Object.entries(source.arguments).map(([name, value]) => [name, String(value)])),
      fieldPath: source.fieldPath,
      comparison: source.comparison,
      threshold: source.threshold,
      interval: String(source.pollIntervalSeconds),
    };
  }
  const source = input.source;
  const type = catalog.eventTypes.find((one) => one.name === source.eventType);
  return {
    ...blank,
    ...common,
    kind: "event",
    eventType: source.eventType,
    terms: source.filter.map((term) => termFormFrom(term, type)),
  };
}

function termFormFrom(term: FilterTerm, type: CatalogEventType | undefined): TermForm {
  const seen = type?.seen[term.attribute] ?? [];
  if (Array.isArray(term.value)) {
    return { attribute: term.attribute, op: term.op, value: term.value.join(", "), picked: term.value.filter((one) => seen.includes(one)) };
  }
  return { attribute: term.attribute, op: term.op, value: String(term.value), picked: [] };
}

/** An empty term for the first attribute the type has, with the first comparison its kind allows. */
export function blankTerm(type: CatalogEventType | undefined): TermForm | null {
  const attribute = Object.keys(type?.attributes ?? {}).find((name) => opsFor(attributeKind(type?.attributes[name])).length > 0);
  if (!attribute || !type) return null;
  return { attribute, op: opsFor(attributeKind(type.attributes[attribute]))[0], value: "", picked: [] };
}

function numberOrNull(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function valueOf(term: TermForm, type: CatalogEventType | undefined): FilterTerm["value"] {
  const kind = attributeKind(type?.attributes[term.attribute]);
  if (term.op === "in") {
    const typed = term.value
      .split(",")
      .map((one) => one.trim())
      .filter(Boolean);
    return [...new Set([...term.picked, ...typed])];
  }
  if (kind === "number") return numberOrNull(term.value) ?? term.value;
  if (kind === "boolean") return term.value !== "false"; // a blank is what the form shows: "tak"
  return term.value;
}

/** The rule the form describes. Numbers that are not numbers are left as they were typed, so the back end names them. */
export function inputFrom(form: RuleForm, catalog: Catalog): RuleInput {
  const common = {
    name: form.name.trim(),
    destination: form.destination,
    template: form.template,
    cooldownSeconds: numberOrNull(form.cooldown),
    mode: form.mode,
    maxPerHour: numberOrNull(form.maxPerHour),
    enabled: form.enabled,
  };
  if (form.kind === "condition") {
    const tool = catalog.tools.find((one) => one.name === form.tool);
    const args: Record<string, unknown> = {};
    for (const field of argumentFields(tool, catalog.symbols)) {
      const typed = form.args[field.name]?.trim() ?? "";
      if (typed === "") continue;
      args[field.name] = field.kind === "number" ? (numberOrNull(typed) ?? typed) : typed;
    }
    return {
      ...common,
      source: {
        kind: "condition",
        toolName: form.tool,
        arguments: args,
        fieldPath: form.fieldPath,
        comparison: form.comparison,
        threshold: form.threshold.trim(),
        pollIntervalSeconds: numberOrNull(form.interval) ?? Number.NaN,
      },
    };
  }
  const type = catalog.eventTypes.find((one) => one.name === form.eventType);
  return {
    ...common,
    source: {
      kind: "event",
      eventType: form.eventType,
      filter: form.terms.map((term) => ({ attribute: term.attribute, op: term.op, value: valueOf(term, type) })),
    },
  };
}

/** Whether the form has what a rule cannot be made without. The back end says the rest, with the field. */
export function formProblem(form: RuleForm): string | null {
  if (form.name.trim() === "") return "Nazwij regułę.";
  if (form.destination === "") return "Wybierz, kogo powiadomić.";
  if (form.kind === "condition" && form.tool === "") return "Wybierz, co sprawdzać.";
  if (form.kind === "condition" && form.threshold.trim() === "") return "Podaj próg.";
  if (form.kind === "event" && form.eventType === "") return "Wybierz zdarzenie.";
  return null;
}

/** The names a template of this rule can fill, so the form can say what to write in braces. */
export function templateSlots(form: RuleForm, catalog: Catalog): string[] {
  if (form.kind === "condition") {
    const tool = catalog.tools.find((one) => one.name === form.tool);
    const given = argumentFields(tool, catalog.symbols)
      .map((field) => field.name)
      .filter((name) => !["rule", "value", "threshold", "comparison", "tool", "field"].includes(name));
    return ["rule", "value", "threshold", "comparison", "tool", "field", ...given];
  }
  const type = catalog.eventTypes.find((one) => one.name === form.eventType);
  return ["rule", "text", "type", ...Object.keys(type?.attributes ?? {}).filter((name) => !["rule", "text", "type"].includes(name))];
}

/** One line of a fire's history in words. */
export const FIRE_LABEL: Record<string, string> = {
  pending: "czeka na wysłanie",
  delivered: "dotarła",
  refused: "odrzucona",
  abandoned: "porzucona",
  throttled: "zdławiona",
  undeliverable: "nie do doręczenia",
};

export const CHECK_LABEL: Record<string, string> = {
  unavailable: "nie mogła odczytać wartości",
  refused: "narzędzie odmówiło",
  cooldown: "próg przekroczony w czasie martwym",
};

/** What the package cannot do, said at the top: a rule is written to be delivered, and these are the ways it will not be. */
export function warnings(state: { delivering: boolean; readingValues: boolean; drafting: boolean; clock: { ran: boolean; ageSeconds: number; expectedSeconds: number } }): string[] {
  const found: string[] = [];
  if (!state.delivering) found.push("Pakiet nie ma bramy Telegrama w tym procesie: reguły odpalają, ale nic nie dociera na telefon.");
  if (!state.readingValues) found.push("Pakiet nie dostał narzędzi do odczytu wartości: reguły cen i wskaźników nie mogą się sprawdzać.");
  const late = state.clock.ageSeconds > state.clock.expectedSeconds * 3;
  if (late) found.push(`Zegar nie tyka od ${Math.round(state.clock.ageSeconds)} s (powinien co ${state.clock.expectedSeconds} s) — reguły nie są sprawdzane.`);
  return found;
}

/**
 * The message as it would read, with an example in every slot, before anything is saved. The same `{slot}` substitution the
 * back end makes — and, like it, one that fills only names and reaches into nothing. A value rule's example is the threshold;
 * an event's is the first value its attribute has had, or the attribute's own name between marks.
 */
export function previewOf(form: RuleForm, catalog: Catalog): string {
  const values: Record<string, string> = {};
  if (form.kind === "condition") {
    const tool = catalog.tools.find((one) => one.name === form.tool);
    for (const field of argumentFields(tool, catalog.symbols)) values[field.name] = form.args[field.name] || `‹${field.name}›`;
    Object.assign(values, {
      rule: form.name || "‹nazwa›",
      value: form.threshold || "‹wartość›",
      threshold: form.threshold || "‹próg›",
      comparison: COMPARISON_LABEL[form.comparison],
      tool: form.tool,
      field: form.fieldPath,
    });
  } else {
    const type = catalog.eventTypes.find((one) => one.name === form.eventType);
    for (const name of Object.keys(type?.attributes ?? {})) values[name] = type?.seen[name]?.[0] ?? `‹${name}›`;
    Object.assign(values, { rule: form.name || "‹nazwa›", text: "‹treść od producenta›", type: form.eventType });
  }
  const template = form.template.trim() === "" ? (form.kind === "condition" ? "{rule}: {value}" : "{text}") : form.template;
  return template.replace(/\{([^{}]*)\}/g, (_, slot: string) => values[slot.trim()] ?? "");
}
