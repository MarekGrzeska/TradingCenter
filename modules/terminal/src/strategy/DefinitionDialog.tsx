import { useMemo, useState } from "react";
import { useIndicatorCatalogue } from "../chart/indicators/useIndicatorCatalogue";
import { indicators as archiveIndicators } from "../data/marketData";
import type { IndicatorSource } from "../data/source";
import type { IndicatorCatalogueEntry } from "../data/types";
import { RESOLUTIONS } from "../data/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { ConditionEditor, NumericEditor, type EditorContext } from "./rule/NodeEditor";
import { blankCondition, blankNumeric, blankRule } from "./rule/vocabulary";
import type { Definition, Rule, RuleFact, RuleParam, StrategyApi } from "./strategyApi";

/**
 * **Every picker is the archive's**, read through `useIndicatorCatalogue`: the cache is keyed by name, and two readers
 * holding two *shapes* poison each other. The refusal is the module's, and saving a revision starts nothing.
 */

// The same height every control in this dialog has, including inside the tree (`rule/NodeEditor.tsx`): a select two
// pixels shorter than the input beside it reads as broken before anybody has read a word.
const FIELD = "h-8 w-full rounded border border-border bg-sunken px-2 text-ink";
const SMALL = "h-7 rounded border border-border bg-sunken px-1 text-ink";
const HINT = "text-ink-faint";

export function DefinitionDialog({
  client,
  existing,
  startFrom,
  source = archiveIndicators,
  onClose,
  onSaved,
}: {
  client: StrategyApi;
  /** The definition being revised, or `undefined` when this is a new one. */
  existing?: Definition;
  /** What to open with — the newest revision of `existing`, or nothing for a blank rule. */
  startFrom?: Rule;
  source?: IndicatorSource;
  onClose(): void;
  onSaved(): void;
}) {
  const [strategyId, setStrategyId] = useState(existing?.strategyId ?? "");
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [rule, setRule] = useState<Rule>(() => startFrom ?? blankRule());

  const catalogue = useIndicatorCatalogue(source);

  const indicators = useMemo(
    () => new Map(catalogue.entries.map((entry) => [entry.id, entry])),
    [catalogue.entries],
  );
  // Only the ones this vocabulary can read. An indicator answering zones or markers is a real entry the comparison
  // cannot point at yet — offering it would end in a refusal the operator could do nothing about.
  const readable = useMemo(
    () => catalogue.entries.filter((entry) => entry.output === "lines"),
    [catalogue.entries],
  );

  const context: EditorContext = { facts: rule.facts, params: rule.params, indicators };
  const patch = (next: Partial<Rule>) => setRule((current) => ({ ...current, ...next }));

  return (
    <ConfirmDialog
      title={existing ? `Nowa rewizja — ${existing.strategyId}` : "Nowa reguła"}
      confirmLabel={existing ? "Zapisz rewizję" : "Zapisz regułę"}
      busyLabel="Pytam moduł…"
      // A rule is composed here, not read. At the width of a question every row of the tree
      // wraps, and a tree whose rows wrap stops looking like a tree.
      size="wide"
      confirmDisabled={strategyId.trim() === "" || name.trim() === ""}
      fallbackError="nie udało się zapisać reguły"
      onConfirm={async () => {
        const signal = new AbortController().signal;
        if (existing) await client.addRevision(existing.strategyId, rule, signal);
        else await client.addDefinition(strategyId.trim(), name.trim(), description, rule, signal);
        onSaved();
      }}
      onClose={onClose}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto pr-1">
        {catalogue.error !== null && (
          <p className="text-warning">
            Katalog wskaźników nie odpowiedział — {catalogue.error}. Bez niego moduł i tak
            odmówi zapisu, bo nie ma z czym sprawdzić reguły.
          </p>
        )}

        <fieldset className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
          <legend className="text-ink-secondary">Tożsamość</legend>
          {/* The hint sits under its field rather than beside it: beside it, one long
              sentence sets the width of the whole row and the fields stop lining up. This is
              the shape every other form in the terminal uses. */}
          <label className="flex flex-col gap-1">
            <span className="text-ink-secondary">Identyfikator</span>
            <input
              className={FIELD}
              aria-label="Identyfikator"
              value={strategyId}
              disabled={existing !== undefined}
              placeholder="np. wybicie_kanalu"
              onChange={(e) => setStrategyId(e.target.value)}
            />
            <span className={HINT}>
              małe litery i podkreślenia; identyfikator wpisu z obrazu jest zajęty
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-ink-secondary">Nazwa</span>
            <input
              className={FIELD}
              aria-label="Nazwa"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-ink-secondary">Opis</span>
            <input
              className={FIELD}
              aria-label="Opis"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-ink-secondary">Decyduje na</span>
            <select
              className={FIELD}
              aria-label="Rozdzielczość"
              value={rule.resolution}
              onChange={(e) => patch({ resolution: e.target.value })}
            >
              {RESOLUTIONS.map((one) => (
                <option key={one} value={one}>
                  {RESOLUTION_LABEL[one] ?? one}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <FactsSection
          facts={rule.facts}
          params={rule.params}
          readable={readable}
          indicators={indicators}
          onChange={(facts) => patch({ facts })}
        />

        <ParamsSection params={rule.params} onChange={(params) => patch({ params })} />

        <fieldset className="flex flex-col gap-2 text-xs">
          <legend className="text-ink-secondary">Odmowy</legend>
          {/* Two sentences the platform will say on the operator's behalf, so they are the
              operator's words. "Nie ustabilizowało się" means something different for an
              average than for a structure. */}
          <label className="flex flex-col gap-1">
            <span className="text-ink-secondary">Gdy odczyt nieustalony</span>
            <input
              className={FIELD}
              aria-label="Powód przy nieustalonym odczycie"
              value={rule.unsettled_reason}
              onChange={(e) => patch({ unsettled_reason: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-ink-secondary">Gdy brak setupu</span>
            <input
              className={FIELD}
              aria-label="Powód przy braku setupu"
              value={rule.no_setup_reason}
              onChange={(e) => patch({ no_setup_reason: e.target.value })}
            />
          </label>
        </fieldset>

        <fieldset className="flex flex-col gap-2 text-xs">
          <legend className="text-ink-secondary">Bramki</legend>
          <p className="text-ink-faint">
            Pytane po kolei: pierwsza, która zajdzie, kończy ocenę odmową ze swoim powodem.
            Najtańsza i najczęstsza na górze.
          </p>
          {rule.guards.map((guard, index) => (
            <div key={index} className="rounded border border-border p-2">
              <div className="flex items-center gap-2">
                <input
                  className={`${SMALL} flex-1`}
                  aria-label={`Powód bramki ${index + 1}`}
                  value={guard.reason}
                  placeholder="powód odmowy"
                  onChange={(e) =>
                    patch({
                      guards: rule.guards.map((one, at) =>
                        at === index ? { ...one, reason: e.target.value } : one,
                      ),
                    })
                  }
                />
                <button
                  type="button"
                  className="text-ink-faint hover:text-critical"
                  onClick={() => patch({ guards: rule.guards.filter((_, at) => at !== index) })}
                >
                  usuń
                </button>
              </div>
              <ConditionEditor
                node={guard.when}
                context={context}
                onChange={(when) =>
                  patch({
                    guards: rule.guards.map((one, at) => (at === index ? { ...one, when } : one)),
                  })
                }
              />
            </div>
          ))}
          <button
            type="button"
            className="self-start text-ink-faint underline hover:text-ink"
            onClick={() =>
              patch({
                guards: [
                  ...rule.guards,
                  {
                    when: blankCondition("settled", rule.facts[0]?.key, rule.params[0]?.name),
                    reason: "odczyt jeszcze się nie ustabilizował",
                  },
                ],
              })
            }
          >
            dodaj bramkę
          </button>
        </fieldset>

        <fieldset className="flex flex-col gap-2 text-xs">
          <legend className="text-ink-secondary">Setupy</legend>
          {rule.setups.map((setup, index) => (
            <div key={index} className="flex flex-col gap-1 rounded border border-border p-2">
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className={SMALL}
                  aria-label={`Kierunek setupu ${index + 1}`}
                  value={setup.direction}
                  onChange={(e) =>
                    patch({
                      setups: rule.setups.map((one, at) =>
                        at === index
                          ? { ...one, direction: e.target.value as "long" | "short" }
                          : one,
                      ),
                    })
                  }
                >
                  <option value="long">długa</option>
                  <option value="short">krótka</option>
                </select>
                <input
                  className={`${SMALL} flex-1`}
                  aria-label={`Powód setupu ${index + 1}`}
                  value={setup.reason}
                  placeholder="co ten setup mówi"
                  onChange={(e) =>
                    patch({
                      setups: rule.setups.map((one, at) =>
                        at === index ? { ...one, reason: e.target.value } : one,
                      ),
                    })
                  }
                />
                {rule.setups.length > 1 && (
                  <button
                    type="button"
                    className="text-ink-faint hover:text-critical"
                    onClick={() => patch({ setups: rule.setups.filter((_, at) => at !== index) })}
                  >
                    usuń
                  </button>
                )}
              </div>
              <span className="text-ink-secondary">Warunek</span>
              <ConditionEditor
                node={setup.when}
                context={context}
                onChange={(when) =>
                  patch({
                    setups: rule.setups.map((one, at) => (at === index ? { ...one, when } : one)),
                  })
                }
              />
              {(["entry", "stop", "target"] as const).map((level) => (
                <div key={level}>
                  <span className="text-ink-secondary">
                    {level === "entry" ? "Wejście" : level === "stop" ? "Obrona" : "Cel"}
                  </span>
                  <NumericEditor
                    node={setup[level]}
                    context={context}
                    onChange={(next) =>
                      patch({
                        setups: rule.setups.map((one, at) =>
                          at === index ? { ...one, [level]: next } : one,
                        ),
                      })
                    }
                  />
                </div>
              ))}
            </div>
          ))}
          <button
            type="button"
            className="self-start text-ink-faint underline hover:text-ink"
            onClick={() => patch({ setups: [...rule.setups, blankRule().setups[0]] })}
          >
            dodaj setup
          </button>
        </fieldset>

        <FeaturesSection
          features={rule.features}
          context={context}
          onChange={(features) => patch({ features })}
        />

        <p className="text-xs text-ink-faint">
          Zapis tworzy nową rewizję i niczego nie uruchamia. Działające obserwacje liczą
          dalej rewizję, do której zostały przypięte — przejście na nowszą to osobny ruch.
        </p>
      </div>
    </ConfirmDialog>
  );
}

function FactsSection({
  facts,
  params,
  readable,
  indicators,
  onChange,
}: {
  facts: RuleFact[];
  params: RuleParam[];
  readable: IndicatorCatalogueEntry[];
  indicators: Map<string, IndicatorCatalogueEntry>;
  onChange(next: RuleFact[]): void;
}) {
  const replace = (index: number, next: RuleFact) =>
    onChange(facts.map((one, at) => (at === index ? next : one)));

  return (
    <fieldset className="flex flex-col gap-2 text-xs">
      <legend className="text-ink-secondary">Fakty</legend>
      <p className="text-ink-faint">
        Co platforma odczyta z archiwum w imieniu tej reguły. Reguła ich nie pobiera — to jest
        ta różnica, dzięki której ta sama funkcja liczy na żywo i w backteście.
      </p>
      {facts.map((fact, index) => {
        const entry = indicators.get(fact.indicator);
        return (
          <div key={index} className="flex flex-wrap items-center gap-2 rounded border border-border p-2">
            <input
              className={`${SMALL} w-28`}
              aria-label={`Klucz faktu ${index + 1}`}
              value={fact.key}
              placeholder="klucz"
              onChange={(e) => replace(index, { ...fact, key: e.target.value })}
            />
            <select
              className={SMALL}
              aria-label={`Wskaźnik faktu ${index + 1}`}
              value={fact.indicator}
              onChange={(e) => replace(index, { ...fact, indicator: e.target.value, params: {} })}
            >
              <option value="">—</option>
              {readable.map((one) => (
                <option key={one.id} value={one.id}>
                  {one.name}
                </option>
              ))}
            </select>
            <select
              className={SMALL}
              aria-label={`Rozdzielczość faktu ${index + 1}`}
              value={fact.resolution}
              onChange={(e) => replace(index, { ...fact, resolution: e.target.value })}
            >
              {RESOLUTIONS.map((one) => (
                <option key={one} value={one}>
                  {RESOLUTION_LABEL[one] ?? one}
                </option>
              ))}
            </select>
            {(entry?.params ?? []).map((param) => (
              <FactParam
                key={param.name}
                label={`${fact.key || `fakt ${index + 1}`} · ${param.name}`}
                name={param.name}
                min={param.min}
                max={param.max}
                fallback={param.default}
                value={fact.params?.[param.name]}
                params={params}
                onChange={(value) =>
                  replace(index, { ...fact, params: { ...fact.params, [param.name]: value } })
                }
              />
            ))}
            <button
              type="button"
              className="ml-auto text-ink-faint hover:text-critical"
              onClick={() => onChange(facts.filter((_, at) => at !== index))}
            >
              usuń
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="self-start text-ink-faint underline hover:text-ink"
        onClick={() =>
          onChange([
            ...facts,
            {
              key: `fakt_${facts.length + 1}`,
              indicator: readable[0]?.id ?? "",
              resolution: "HOUR",
              params: {},
              bars: 300,
            },
          ])
        }
      >
        dodaj fakt
      </button>
    </fieldset>
  );
}

function FactParam({
  label,
  name,
  min,
  max,
  fallback,
  value,
  params,
  onChange,
}: {
  label: string;
  name: string;
  min: number;
  max: number;
  fallback: number;
  value: number | string | undefined;
  params: RuleParam[];
  onChange(next: number | string): void;
}) {
  const asParam = typeof value === "string";
  return (
    <label className="flex items-center gap-1 text-ink-faint">
      {name}
      <select
        className={SMALL}
        aria-label={`${label} — źródło`}
        value={asParam ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? fallback : e.target.value)}
      >
        <option value="">liczba</option>
        {params.map((param) => (
          <option key={param.name} value={param.name}>
            {param.name}
          </option>
        ))}
      </select>
      {!asParam && (
        <input
          className={`${SMALL} w-16`}
          type="number"
          step="any"
          aria-label={label}
          value={value ?? fallback}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      )}
      {/* The archive's own range, shown and not enforced: the module refuses a value outside
          it, naming both bounds, and a copy of the rule here would be a second opinion. */}
      <span>
        {min}–{max}
      </span>
    </label>
  );
}

function ParamsSection({
  params,
  onChange,
}: {
  params: RuleParam[];
  onChange(next: RuleParam[]): void;
}) {
  const replace = (index: number, next: RuleParam) =>
    onChange(params.map((one, at) => (at === index ? next : one)));

  return (
    <fieldset className="flex flex-col gap-2 text-xs">
      <legend className="text-ink-secondary">Parametry</legend>
      <p className="text-ink-faint">
        Strojone bez zmiany reguły. Zakres szerszy niż zakres wskaźnika, który ten parametr
        napędza, moduł odrzuci — nazywając oba.
      </p>
      {params.map((param, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <input
            className={`${SMALL} w-32`}
            aria-label={`Nazwa parametru ${index + 1}`}
            value={param.name}
            onChange={(e) => replace(index, { ...param, name: e.target.value })}
          />
          <select
            className={SMALL}
            aria-label={`Typ parametru ${index + 1}`}
            value={param.type}
            onChange={(e) => replace(index, { ...param, type: e.target.value as "int" | "float" })}
          >
            <option value="int">całkowity</option>
            <option value="float">rzeczywisty</option>
          </select>
          {(["default", "min", "max"] as const).map((field) => (
            <label key={field} className="flex items-center gap-1 text-ink-faint">
              {field === "default" ? "domyślnie" : field}
              <input
                className={`${SMALL} w-16`}
                type="number"
                step="any"
                aria-label={`${param.name} — ${field}`}
                value={param[field]}
                onChange={(e) => replace(index, { ...param, [field]: Number(e.target.value) })}
              />
            </label>
          ))}
          <button
            type="button"
            className="text-ink-faint hover:text-critical"
            onClick={() => onChange(params.filter((_, at) => at !== index))}
          >
            usuń
          </button>
        </div>
      ))}
      <button
        type="button"
        className="self-start text-ink-faint underline hover:text-ink"
        onClick={() =>
          onChange([
            ...params,
            { name: `parametr_${params.length + 1}`, type: "float", default: 1, min: 0, max: 10 },
          ])
        }
      >
        dodaj parametr
      </button>
    </fieldset>
  );
}

function FeaturesSection({
  features,
  context,
  onChange,
}: {
  features: Rule["features"];
  context: EditorContext;
  onChange(next: Rule["features"]): void;
}) {
  const entries = Object.entries(features);
  return (
    <fieldset className="flex flex-col gap-2 text-xs">
      <legend className="text-ink-secondary">Cechy</legend>
      <p className="text-ink-faint">
        Nazwane liczby, po których raport z backtestu przypisuje przewagę. Nic od nich nie
        zależy — cecha, której nie dało się policzyć, po prostu nie trafia do decyzji.
      </p>
      {entries.map(([name, node]) => (
        <div key={name} className="rounded border border-border p-2">
          <div className="flex items-center gap-2">
            <input
              className={`${SMALL} w-40`}
              aria-label={`Nazwa cechy ${name}`}
              value={name}
              onChange={(e) => {
                const renamed = Object.fromEntries(
                  entries.map(([key, value]) => (key === name ? [e.target.value, value] : [key, value])),
                );
                onChange(renamed);
              }}
            />
            <button
              type="button"
              className="text-ink-faint hover:text-critical"
              onClick={() =>
                onChange(Object.fromEntries(entries.filter(([key]) => key !== name)))
              }
            >
              usuń
            </button>
          </div>
          <NumericEditor
            node={node}
            context={context}
            onChange={(next) => onChange({ ...features, [name]: next })}
          />
        </div>
      ))}
      <button
        type="button"
        className="self-start text-ink-faint underline hover:text-ink"
        onClick={() =>
          onChange({ ...features, [`cecha_${entries.length + 1}`]: blankNumeric("const") })
        }
      >
        dodaj cechę
      </button>
    </fieldset>
  );
}
