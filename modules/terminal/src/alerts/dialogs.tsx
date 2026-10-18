import { useState } from "react";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { RuleRefused, type AlertsApi, type Catalog, type Defect, type Rule, type FilterOp, type CatalogEventType } from "./alertsApi";
import {
  COMPARISON_LABEL,
  OP_LABEL,
  argumentFields,
  attributeKind,
  blankTerm,
  defectsFor,
  formProblem,
  inputFrom,
  opsFor,
  previewOf,
  templateSlots,
  type RuleForm,
  type TermForm,
} from "./present";

/**
 * The questions this tab asks. A refusal of a rule names every field at fault, and each reason is put beside its field; the
 * sentence on top says only that the rule was refused, so the operator is never reading the same reason twice.
 */

// One height for every control, so a row of selects, numbers and text lines sits on one line whatever sits under each.
const INPUT = "h-8 rounded border border-border bg-sunken px-2 text-ink";
const TEXTAREA = "rounded border border-border bg-sunken px-2 py-1 text-ink";
const signal = () => new AbortController().signal;
const OTHER = "__other__";

function Field({
  label,
  hint,
  problems = [],
  children,
}: {
  label: string;
  hint?: string;
  problems?: Defect[];
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-ink-secondary">{label || " "}</span>
      {children}
      {hint && <span className="text-ink-faint">{hint}</span>}
      {problems.map((one) => (
        <span key={one.message} role="alert" className="text-critical">
          {one.message}
        </span>
      ))}
    </label>
  );
}

export interface Start {
  form: RuleForm;
  /** What is already known to be wrong — a draft arrives with its reasons. */
  defects: Defect[];
  /** Said above the form: how a sentence was read, and what was chosen for the operator. */
  understood?: string;
  notes?: string[];
}

export function RuleDialog({
  api,
  catalog,
  start,
  editing,
  onClose,
  onDone,
}: {
  api: AlertsApi;
  catalog: Catalog;
  start: Start;
  editing?: Rule;
  onClose(): void;
  onDone(): void;
}) {
  const [form, setForm] = useState<RuleForm>(start.form);
  const [defects, setDefects] = useState<Defect[]>(start.defects);
  // A draft arrives with what is wrong with it; saving it as it stands would only be refused, so it waits for a change.
  const [asDrafted] = useState(() => JSON.stringify(start.form));
  const stillAsDrafted = start.defects.length > 0 && JSON.stringify(form) === asDrafted;
  const problem = formProblem(form);
  const change = (patch: Partial<RuleForm>) => setForm((current) => ({ ...current, ...patch }));
  const about = (field: string) => defectsFor(defects, field);

  const tool = catalog.tools.find((one) => one.name === form.tool);
  const eventType = catalog.eventTypes.find((one) => one.name === form.eventType);
  const slots = templateSlots(form, catalog);

  async function save(): Promise<void> {
    setDefects([]);
    const input = inputFrom(form, catalog);
    try {
      if (editing) await api.replaceRule(editing.id, input, signal());
      else await api.createRule(input, signal());
    } catch (cause: unknown) {
      if (cause instanceof RuleRefused) setDefects(cause.defects);
      throw cause;
    }
    onDone();
  }

  return (
    <ConfirmDialog
      title={editing ? "Edytuj regułę" : "Nowa reguła"}
      confirmLabel="Zapisz"
      busyLabel="Zapisuję…"
      confirmDisabled={problem !== null || stillAsDrafted}
      fallbackError="nie udało się zapisać reguły"
      size="wide"
      onConfirm={save}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        {start.understood && <p className="text-xs text-ink-secondary">Zrozumiałem to tak: {start.understood}</p>}
        {(start.notes ?? []).map((note) => (
          <p key={note} className="text-xs text-warning">
            {note}
          </p>
        ))}
        {about("sentence").map((one) => (
          <p key={one.message} role="alert" className="text-xs text-critical">
            {one.message}
          </p>
        ))}

        <Field label="Nazwa" problems={about("name")}>
          <input className={INPUT} value={form.name} autoFocus onChange={(e) => change({ name: e.target.value })} />
        </Field>

        <div className="flex gap-4 text-xs text-ink">
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="kind"
              checked={form.kind === "condition"}
              disabled={catalog.tools.length === 0}
              onChange={() => change({ kind: "condition" })}
            />
            Wartość (cena, wskaźnik) przekroczy próg
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="kind"
              checked={form.kind === "event"}
              disabled={catalog.eventTypes.length === 0}
              onChange={() => change({ kind: "event" })}
            />
            Coś się wydarzy (film, post, przebieg zespołu)
          </label>
        </div>

        {form.kind === "condition" ? (
          <fieldset className="flex flex-col gap-3 rounded border border-border/60 p-3">
            <Field label="Co sprawdzać" hint={tool?.description.split("\n")[0]} problems={about("source.tool_name")}>
              <select
                className={INPUT}
                value={form.tool}
                onChange={(e) => {
                  const next = catalog.tools.find((one) => one.name === e.target.value);
                  change({ tool: e.target.value, args: {}, fieldPath: next?.numberFields[0] ?? "" });
                }}
              >
                {catalog.tools.map((one) => (
                  <option key={one.name} value={one.name}>
                    {one.name} ({one.source})
                  </option>
                ))}
              </select>
            </Field>

            {argumentFields(tool, catalog.symbols).map((field) => (
              <Field
                key={field.name}
                label={field.name + (field.required ? " *" : "")}
                hint={field.description}
                problems={about(`source.arguments.${field.name}`)}
              >
                {field.kind === "symbol" || field.kind === "choice" ? (
                  <select
                    className={INPUT}
                    value={form.args[field.name] ?? ""}
                    onChange={(e) => change({ args: { ...form.args, [field.name]: e.target.value } })}
                  >
                    <option value="">{field.required ? "— wybierz —" : "— domyślnie —"}</option>
                    {field.choices.map((one) => (
                      <option key={one} value={one}>
                        {one}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className={INPUT}
                    type={field.kind === "number" ? "number" : "text"}
                    value={form.args[field.name] ?? ""}
                    onChange={(e) => change({ args: { ...form.args, [field.name]: e.target.value } })}
                  />
                )}
              </Field>
            ))}
            {about("source.arguments").map((one) => (
              <p key={one.message} role="alert" className="text-xs text-critical">
                {one.message}
              </p>
            ))}

            <div className="flex flex-wrap items-start gap-3">
              <Field label="Której wartości" problems={about("source.field_path")}>
                {tool && tool.numberFields.length > 0 ? (
                  <select className={INPUT} value={form.fieldPath} onChange={(e) => change({ fieldPath: e.target.value })}>
                    {tool.numberFields.map((one) => (
                      <option key={one} value={one}>
                        {one}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="text-ink-faint">to narzędzie nie zwraca liczb</span>
                )}
              </Field>
              <Field label="Gdy jest">
                <select
                  className={INPUT}
                  value={form.comparison}
                  onChange={(e) => change({ comparison: e.target.value as RuleForm["comparison"] })}
                >
                  {(Object.keys(COMPARISON_LABEL) as RuleForm["comparison"][]).map((one) => (
                    <option key={one} value={one}>
                      {COMPARISON_LABEL[one]}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Próg">
                <input
                  className={`${INPUT} w-32`}
                  inputMode="decimal"
                  value={form.threshold}
                  onChange={(e) => change({ threshold: e.target.value })}
                />
              </Field>
              <Field
                label="Sprawdzaj co (s)"
                hint={`nie rzadziej niż co ${catalog.minIntervalSeconds} s`}
                problems={about("source.poll_interval_seconds")}
              >
                <input
                  className={`${INPUT} w-24`}
                  type="number"
                  min={catalog.minIntervalSeconds}
                  value={form.interval}
                  onChange={(e) => change({ interval: e.target.value })}
                />
              </Field>
            </div>
            <p className="text-xs text-ink-faint">
              Reguła widzi wartość w chwili każdego sprawdzenia: szpilka, która wróci między dwoma sprawdzeniami, nie zostanie
              złapana.
            </p>
          </fieldset>
        ) : (
          <fieldset className="flex flex-col gap-3 rounded border border-border/60 p-3">
            <Field label="Zdarzenie" hint={eventType?.description} problems={about("source.event_type")}>
              <select
                className={INPUT}
                value={form.eventType}
                onChange={(e) => change({ eventType: e.target.value, terms: [] })}
              >
                {catalog.eventTypes.map((one) => (
                  <option key={one.name} value={one.name}>
                    {one.name}
                  </option>
                ))}
              </select>
            </Field>

            {form.terms.map((term, index) => (
              <TermRow
                key={index}
                term={term}
                type={eventType}
                problems={[...about(`source.filter.${index}`)]}
                onChange={(next) => change({ terms: form.terms.map((one, at) => (at === index ? next : one)) })}
                onRemove={() => change({ terms: form.terms.filter((_, at) => at !== index) })}
              />
            ))}
            <div>
              <Button
                size="xs"
                disabled={blankTerm(eventType) === null}
                onClick={() => {
                  const next = blankTerm(eventType);
                  if (next) change({ terms: [...form.terms, next] });
                }}
              >
                Dodaj warunek
              </Button>
              {form.terms.length === 0 && <span className="ml-2 text-xs text-ink-faint">bez warunków — każde takie zdarzenie</span>}
            </div>
          </fieldset>
        )}

        <Field
          label="Kogo powiadomić"
          hint={
            catalog.recipients.length === 0
              ? "Najpierw dodaj odbiorcę w zakładce Telegram."
              : !catalog.gateway
                ? "Ten proces nie ma bramy Telegrama — reguła odpali, ale nic nie dotrze."
                : undefined
          }
          problems={about("destination")}
        >
          <select className={INPUT} value={form.destination} onChange={(e) => change({ destination: e.target.value })}>
            <option value="">— wybierz —</option>
            {catalog.recipients.map((one) => (
              <option key={one.name} value={one.name}>
                {one.name} (@{one.bot}){one.receives ? "" : " — jeszcze nie odbiera"}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label="Treść wiadomości"
          hint={`Puste = treść domyślna. W nawiasach klamrowych: ${slots.map((one) => `{${one}}`).join(" ")}`}
          problems={about("template")}
        >
          <textarea className={TEXTAREA} rows={2} value={form.template} onChange={(e) => change({ template: e.target.value })} />
        </Field>
        <p className="rounded bg-sunken/60 px-2 py-1 text-xs text-ink-secondary" aria-label="podgląd wiadomości">
          Podgląd: {previewOf(form, catalog)}
        </p>

        <details className="text-xs">
          <summary className="cursor-pointer text-ink-secondary">Rytm i granice</summary>
          <div className="mt-2 flex flex-wrap items-start gap-3">
            <Field label="Czas martwy (s)" hint="pusto = domyślnie (900 dla wartości, 0 dla zdarzeń)">
              <input
                className={`${INPUT} w-28`}
                type="number"
                min={0}
                value={form.cooldown}
                onChange={(e) => change({ cooldown: e.target.value })}
              />
            </Field>
            <Field label="Powiadamiaj">
              <select className={INPUT} value={form.mode} onChange={(e) => change({ mode: e.target.value as RuleForm["mode"] })}>
                <option value="repeat">za każdym razem</option>
                <option value="once">raz, potem wyłącz</option>
              </select>
            </Field>
            <Field label="Najwyżej na godzinę" hint="pusto = granica pakietu">
              <input
                className={`${INPUT} w-28`}
                type="number"
                min={1}
                value={form.maxPerHour}
                onChange={(e) => change({ maxPerHour: e.target.value })}
              />
            </Field>
            <Field label="">
              <span className="flex h-8 items-center gap-1 text-ink">
                <input type="checkbox" checked={form.enabled} onChange={(e) => change({ enabled: e.target.checked })} />
                włączona
              </span>
            </Field>
          </div>
        </details>

        {problem && <p className="text-xs text-ink-faint">{problem}</p>}
      </div>
    </ConfirmDialog>
  );
}

function TermRow({
  term,
  type,
  problems,
  onChange,
  onRemove,
}: {
  term: TermForm;
  type: CatalogEventType | undefined;
  problems: Defect[];
  onChange(next: TermForm): void;
  onRemove(): void;
}) {
  const attributes = Object.keys(type?.attributes ?? {}).filter((name) => opsFor(attributeKind(type?.attributes[name])).length > 0);
  const kind = attributeKind(type?.attributes[term.attribute]);
  const seen = type?.seen[term.attribute] ?? [];
  const known = seen.includes(term.value);

  function pick(attribute: string) {
    const ops = opsFor(attributeKind(type?.attributes[attribute]));
    onChange({ attribute, op: ops[0], value: "", picked: [] });
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-start gap-2">
        <Field label="Gdy">
          <select className={INPUT} value={term.attribute} onChange={(e) => pick(e.target.value)}>
            {attributes.map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
        </Field>
        <Field label="">
          <select className={INPUT} value={term.op} onChange={(e) => onChange({ ...term, op: e.target.value as FilterOp })}>
            {opsFor(kind).map((one) => (
              <option key={one} value={one}>
                {OP_LABEL[one]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="">
          {kind === "boolean" ? (
            <select className={INPUT} value={term.value || "true"} onChange={(e) => onChange({ ...term, value: e.target.value })}>
              <option value="true">tak</option>
              <option value="false">nie</option>
            </select>
          ) : term.op === "in" && seen.length > 0 ? (
            <span className="flex flex-wrap items-center gap-2 text-xs text-ink">
              {seen.map((one) => (
                <label key={one} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={term.picked.includes(one)}
                    onChange={(e) =>
                      onChange({ ...term, picked: e.target.checked ? [...term.picked, one] : term.picked.filter((x) => x !== one) })
                    }
                  />
                  {one}
                </label>
              ))}
            </span>
          ) : kind === "string" && seen.length > 0 ? (
            <span className="flex gap-2">
              <select
                className={INPUT}
                value={known ? term.value : OTHER}
                onChange={(e) => onChange({ ...term, value: e.target.value === OTHER ? "" : e.target.value })}
              >
                {seen.map((one) => (
                  <option key={one} value={one}>
                    {one}
                  </option>
                ))}
                <option value={OTHER}>inna wartość…</option>
              </select>
              {!known && (
                <input
                  className={INPUT}
                  aria-label="inna wartość"
                  value={term.value}
                  onChange={(e) => onChange({ ...term, value: e.target.value })}
                />
              )}
            </span>
          ) : (
            <input
              className={INPUT}
              type={kind === "number" && term.op !== "in" ? "number" : "text"}
              placeholder={term.op === "in" ? "wartości po przecinku" : ""}
              value={term.value}
              onChange={(e) => onChange({ ...term, value: e.target.value })}
            />
          )}
        </Field>
        <div className="flex flex-col gap-1 text-xs">
          <span>{" "}</span>
          <span className="flex h-8 items-center">
            <Button size="xs" tone="muted" aria-label="usuń warunek" onClick={onRemove}>
              ×
            </Button>
          </span>
        </div>
      </div>
      {problems.map((one) => (
        <span key={one.message} role="alert" className="text-xs text-critical">
          {one.message}
        </span>
      ))}
    </div>
  );
}

export function DeleteRuleDialog({
  api,
  rule,
  onClose,
  onDone,
}: {
  api: AlertsApi;
  rule: Rule;
  onClose(): void;
  onDone(): void;
}) {
  return (
    <ConfirmDialog
      title="Usuń regułę"
      confirmLabel="Usuń"
      busyLabel="Usuwam…"
      tone="danger"
      fallbackError="nie udało się usunąć reguły"
      onConfirm={async () => {
        await api.deleteRule(rule.id, signal());
        onDone();
      }}
      onClose={onClose}
    >
      <p className="text-sm text-ink">
        Reguła „{rule.name}” przestanie działać, a jej historia zniknie. Wiadomości, które już dotarły, zostają na telefonie.
        Wyłączenie jest odwracalne; usunięcie nie.
      </p>
    </ConfirmDialog>
  );
}
