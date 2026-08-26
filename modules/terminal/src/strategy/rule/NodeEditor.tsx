import type { IndicatorCatalogueEntry } from "../../data/types";
import type { ConditionNode, NumericNode, RuleFact, RuleParam } from "../strategyApi";
import {
  ARITH_OPS,
  BAR_FIELDS,
  CALL_FNS,
  COMPARE_OPS,
  CONDITION_KINDS,
  CONDITION_LABELS,
  LOGIC_LABELS,
  LOGIC_OPS,
  NUMERIC_KINDS,
  NUMERIC_LABELS,
  blankCondition,
  blankNumeric,
  operandLimits,
} from "./vocabulary";

/**
 * A tree edited as a tree — no text to parse, which is why the vocabulary is data and not a little language. The
 * pickers come from the archive, and nothing here validates: the module refuses at save, naming what it refused.
 */

export interface EditorContext {
  facts: RuleFact[];
  params: RuleParam[];
  /** The archive's catalogue, keyed by indicator id. Missing while it is still loading, in
   *  which case the line picker degrades to a plain field rather than to nothing. */
  indicators: Map<string, IndicatorCatalogueEntry>;
}

// One height for every control in the tree, load-bearing rather than tidy: a row mixing a 24px select with a 28px
// input reads as two rows, and a tree is only legible while its rows read as a column.
const CONTROL = "h-7 rounded border border-border bg-sunken px-1 text-ink";
// The kind picker is the column an operator's eye runs down, so it has one width whatever it
// currently says. The operator picker beside it has another, narrower one.
const KIND = `${CONTROL} w-44`;
const OPERATOR = `${CONTROL} w-28`;
const SELECT = `${CONTROL} w-32`;
const NUMBER = `${CONTROL} w-24`;
const OFFSET = `${CONTROL} w-14`;

function Row({ depth, children }: { depth: number; children: React.ReactNode }) {
  return (
    <div
      // The indent is a rule, not padding: nesting three deep is unreadable when the only
      // sign of it is where a row starts.
      className={`flex flex-wrap items-center gap-1 py-0.5 text-xs${
        depth > 0 ? " border-l border-border pl-2" : ""
      }`}
      style={{ marginLeft: depth > 0 ? `${(depth - 1) * 0.85}rem` : undefined }}
    >
      {children}
    </div>
  );
}

function Operands<T extends NumericNode | ConditionNode>({
  node,
  operands,
  depth,
  onChange,
  render,
  blank,
}: {
  node: NumericNode | ConditionNode;
  operands: T[];
  depth: number;
  onChange(next: T[]): void;
  render(child: T, index: number): React.ReactNode;
  blank(): T;
}) {
  const limits = operandLimits(node);
  return (
    <>
      {operands.map((child, index) => (
        <div key={index} className="flex items-start gap-1">
          <div className="min-w-0 flex-1">{render(child, index)}</div>
          {operands.length > limits.min && (
            <button
              type="button"
              className="mt-1 shrink-0 text-xs text-ink-faint hover:text-critical"
              aria-label="Usuń składnik"
              onClick={() => onChange(operands.filter((_, at) => at !== index))}
            >
              ×
            </button>
          )}
        </div>
      ))}
      {operands.length < limits.max && (
        <Row depth={depth + 1}>
          <button
            type="button"
            className="text-xs text-ink-faint underline hover:text-ink"
            onClick={() => onChange([...operands, blank()])}
          >
            dodaj składnik
          </button>
        </Row>
      )}
    </>
  );
}

function KindPicker<K extends string>({
  label,
  value,
  kinds,
  labels,
  onChange,
}: {
  label: string;
  value: K;
  kinds: K[];
  labels: Record<K, string>;
  onChange(kind: K): void;
}) {
  return (
    <select
      className={KIND}
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value as K)}
    >
      {kinds.map((kind) => (
        <option key={kind} value={kind}>
          {labels[kind]}
        </option>
      ))}
    </select>
  );
}

export function NumericEditor({
  node,
  context,
  onChange,
  depth = 0,
  label = "Wyrażenie",
}: {
  node: NumericNode;
  context: EditorContext;
  onChange(next: NumericNode): void;
  depth?: number;
  label?: string;
}) {
  const firstFact = context.facts[0]?.key;
  const firstParam = context.params[0]?.name;

  const head = (
    <KindPicker
      label={label}
      value={node.node}
      kinds={NUMERIC_KINDS}
      labels={NUMERIC_LABELS}
      onChange={(kind) => onChange(blankNumeric(kind, firstFact, firstParam))}
    />
  );

  if (node.node === "const") {
    return (
      <Row depth={depth}>
        {head}
        <input
          className={NUMBER}
          type="number"
          step="any"
          aria-label="Wartość"
          value={node.value}
          onChange={(e) => onChange({ ...node, value: Number(e.target.value) })}
        />
      </Row>
    );
  }

  if (node.node === "param") {
    return (
      <Row depth={depth}>
        {head}
        <select
          className={SELECT}
          aria-label="Parametr"
          value={node.name}
          onChange={(e) => onChange({ ...node, name: e.target.value })}
        >
          <option value="">—</option>
          {context.params.map((param) => (
            <option key={param.name} value={param.name}>
              {param.name}
            </option>
          ))}
        </select>
      </Row>
    );
  }

  if (node.node === "fact") {
    const fact = context.facts.find((one) => one.key === node.key);
    const lines = fact ? (context.indicators.get(fact.indicator)?.lines ?? []) : [];
    return (
      <Row depth={depth}>
        {head}
        <select
          className={SELECT}
          aria-label="Fakt"
          value={node.key}
          onChange={(e) => onChange({ ...node, key: e.target.value })}
        >
          <option value="">—</option>
          {context.facts.map((one) => (
            <option key={one.key} value={one.key}>
              {one.key}
            </option>
          ))}
        </select>
        <select
          className={SELECT}
          aria-label="Linia"
          value={node.line}
          onChange={(e) => onChange({ ...node, line: e.target.value })}
        >
          <option value="">—</option>
          {lines.map((line) => (
            <option key={line.key} value={line.key}>
              {line.key}
            </option>
          ))}
        </select>
        <OffsetField value={node.offset ?? 0} onChange={(offset) => onChange({ ...node, offset })} />
      </Row>
    );
  }

  if (node.node === "bar") {
    return (
      <Row depth={depth}>
        {head}
        <select
          className={SELECT}
          aria-label="Pole świecy"
          value={node.field ?? "close"}
          onChange={(e) => onChange({ ...node, field: e.target.value as (typeof BAR_FIELDS)[number] })}
        >
          {BAR_FIELDS.map((field) => (
            <option key={field} value={field}>
              {field}
            </option>
          ))}
        </select>
        <OffsetField value={node.offset ?? 0} onChange={(offset) => onChange({ ...node, offset })} />
      </Row>
    );
  }

  if (node.node === "previous") {
    return (
      <>
        <Row depth={depth}>{head}</Row>
        <NumericEditor
          node={node.of}
          context={context}
          depth={depth + 1}
          onChange={(of) => onChange({ ...node, of })}
        />
      </>
    );
  }

  const operands = node.operands;
  return (
    <>
      <Row depth={depth}>
        {head}
        {node.node === "arith" ? (
          <select
            className={OPERATOR}
            aria-label="Działanie"
            value={node.op}
            onChange={(e) =>
              onChange({ ...node, op: e.target.value as (typeof ARITH_OPS)[number] })
            }
          >
            {ARITH_OPS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
        ) : (
          <select
            className={OPERATOR}
            aria-label="Funkcja"
            value={node.fn}
            onChange={(e) => onChange({ ...node, fn: e.target.value as (typeof CALL_FNS)[number] })}
          >
            {CALL_FNS.map((fn) => (
              <option key={fn} value={fn}>
                {fn}
              </option>
            ))}
          </select>
        )}
      </Row>
      <Operands
        node={node}
        operands={operands}
        depth={depth}
        onChange={(next) => onChange({ ...node, operands: next })}
        blank={() => blankNumeric("const")}
        render={(child, index) => (
          <NumericEditor
            node={child}
            context={context}
            depth={depth + 1}
            onChange={(next) =>
              onChange({
                ...node,
                operands: operands.map((one, at) => (at === index ? next : one)),
              })
            }
          />
        )}
      />
    </>
  );
}

function OffsetField({ value, onChange }: { value: number; onChange(next: number): void }) {
  return (
    <label className="flex shrink-0 items-center gap-1 whitespace-nowrap text-ink-faint">
      wstecz
      <input
        className={OFFSET}
        type="number"
        min={0}
        aria-label="Świec wstecz"
        value={value}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value)))}
      />
    </label>
  );
}

export function ConditionEditor({
  node,
  context,
  onChange,
  depth = 0,
  label = "Warunek",
}: {
  node: ConditionNode;
  context: EditorContext;
  onChange(next: ConditionNode): void;
  depth?: number;
  label?: string;
}) {
  const firstFact = context.facts[0]?.key;
  const firstParam = context.params[0]?.name;

  const head = (
    <KindPicker
      label={label}
      value={node.node}
      kinds={CONDITION_KINDS}
      labels={CONDITION_LABELS}
      onChange={(kind) => onChange(blankCondition(kind, firstFact, firstParam))}
    />
  );

  if (node.node === "compare" || node.node === "crossed") {
    return (
      <>
        <Row depth={depth}>
          {head}
          {node.node === "compare" ? (
            <select
              className={OPERATOR}
              aria-label="Znak porównania"
              value={node.op}
              onChange={(e) =>
                onChange({ ...node, op: e.target.value as (typeof COMPARE_OPS)[number] })
              }
            >
              {COMPARE_OPS.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </select>
          ) : (
            <select
              className={OPERATOR}
              aria-label="Kierunek przecięcia"
              value={node.direction}
              onChange={(e) =>
                onChange({ ...node, direction: e.target.value as "above" | "below" })
              }
            >
              <option value="above">w górę</option>
              <option value="below">w dół</option>
            </select>
          )}
        </Row>
        <NumericEditor
          node={node.left}
          context={context}
          depth={depth + 1}
          label="Lewa strona"
          onChange={(left) => onChange({ ...node, left })}
        />
        <NumericEditor
          node={node.right}
          context={context}
          depth={depth + 1}
          label="Prawa strona"
          onChange={(right) => onChange({ ...node, right })}
        />
      </>
    );
  }

  if (node.node === "settled") {
    return (
      <>
        <Row depth={depth}>
          {head}
          {/* Said in words because it is the one node that answers instead of spreading a
              missing reading — which is exactly why an operator reaches for it. */}
          <span className="text-ink-faint">
            prawda tylko wtedy, gdy archiwum policzyło każdy z tych odczytów
          </span>
        </Row>
        <Operands
          node={node}
          operands={node.of}
          depth={depth}
          onChange={(of) => onChange({ ...node, of })}
          blank={() => blankNumeric("fact", firstFact, firstParam)}
          render={(child, index) => (
            <NumericEditor
              node={child}
              context={context}
              depth={depth + 1}
              onChange={(next) =>
                onChange({ ...node, of: node.of.map((one, at) => (at === index ? next : one)) })
              }
            />
          )}
        />
      </>
    );
  }

  return (
    <>
      <Row depth={depth}>
        {head}
        <select
          className={OPERATOR}
          aria-label="Spójnik"
          value={node.op}
          onChange={(e) => onChange({ ...node, op: e.target.value as (typeof LOGIC_OPS)[number] })}
        >
          {LOGIC_OPS.map((op) => (
            <option key={op} value={op}>
              {LOGIC_LABELS[op]}
            </option>
          ))}
        </select>
      </Row>
      <Operands
        node={node}
        operands={node.operands}
        depth={depth}
        onChange={(operands) => onChange({ ...node, operands })}
        blank={() => blankCondition("compare", firstFact, firstParam)}
        render={(child, index) => (
          <ConditionEditor
            node={child}
            context={context}
            depth={depth + 1}
            onChange={(next) =>
              onChange({
                ...node,
                operands: node.operands.map((one, at) => (at === index ? next : one)),
              })
            }
          />
        )}
      />
    </>
  );
}
