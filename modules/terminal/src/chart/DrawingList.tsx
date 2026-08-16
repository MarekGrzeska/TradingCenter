import { useState } from "react";
import type { AgentChartDrawing, AgentDrawingPatch } from "../agent/agentApi";
import { formatInstant } from "../ui/formatTime";
import type { ChartDrawings } from "./Chart";

/**
 * The objects standing on this instrument, and the only way the operator takes one off.
 *
 * That is what it is for: whatever the agent draws must be undoable by hand, without a
 * conversation and without the model (`agent-tools` spec, "Zapis MUST być odwracalny ręką
 * operatora"). So this sits in the chart's own header beside the indicator picker, not
 * inside the agent panel — a list reachable only through the thing it exists to undo
 * would not be reachable at all.
 *
 * Nothing here holds its own copy of the list. Every write goes to the module and the
 * store re-reads: an object removed from the screen but not from the record comes back
 * on the next read, and that reads as a fault (`terminal-chart` spec, "Nieudane usunięcie
 * albo nieudana poprawka").
 */
export interface DrawingListProps {
  drawings: ChartDrawings;
}

/** The prices a shape has, by the role each plays — the same roles `PatchDrawingIn`
 *  accepts, so an edited field maps to its patch without a second table anywhere. */
type PriceRole = "price" | "top" | "bottom" | "aPrice" | "bPrice";

function priceFields(drawing: AgentChartDrawing): Array<{ role: PriceRole; label: string; value: number }> {
  const geometry = drawing.geometry;
  if (geometry.kind === "level") return [{ role: "price", label: "Price", value: geometry.price }];
  if (geometry.kind === "zone") {
    return [
      { role: "top", label: "Top", value: geometry.top },
      { role: "bottom", label: "Bottom", value: geometry.bottom },
    ];
  }
  return [
    { role: "aPrice", label: "From", value: geometry.a.price },
    { role: "bPrice", label: "To", value: geometry.b.price },
  ];
}

function shapeLabel(drawing: AgentChartDrawing): string {
  return drawing.geometry.kind === "trendline" ? "trend line" : drawing.geometry.kind;
}

/** The prices as one line, for the row's own summary — `priceFields` in reading order. */
function priceSummary(drawing: AgentChartDrawing): string {
  return priceFields(drawing)
    .map((field) => field.value)
    .join(" – ");
}

export function DrawingList({ drawings }: DrawingListProps) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  // What the last write said went wrong, if anything. One at a time: the operator is
  // acting on one row, and a list of stale failures is noise rather than information.
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const items = drawings.items;

  async function act(id: number, run: () => Promise<string | null>): Promise<boolean> {
    setBusy(id);
    setFailure(null);
    const problem = await run();
    setBusy(null);
    setFailure(problem);
    return problem === null;
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen(!open);
          setFailure(null);
          setEditing(null);
        }}
        aria-expanded={open}
        aria-label="Drawn objects"
        className="h-6 rounded border border-border px-1.5 text-xs text-ink hover:bg-panel-strong"
      >
        Objects{items.length > 0 ? ` (${items.length})` : ""}
        {drawings.status === "error" && <span className="ml-1 text-critical">!</span>}
      </button>

      {open && (
        <div className="absolute left-0 top-7 z-20 max-h-96 w-80 overflow-y-auto rounded border border-border bg-panel p-2 shadow-lg">
          {drawings.status === "error" ? (
            // Said as its own line above whatever is still on screen: the chart keeps
            // drawing what it last read, and this says the list may be out of date rather
            // than pretending the instrument has nothing on it.
            <p className="mb-2 rounded border border-critical/40 px-2 py-1 text-xs text-critical">
              The drawn objects could not be read. {drawings.error}
            </p>
          ) : null}

          {failure !== null && (
            <p className="mb-2 rounded border border-critical/40 px-2 py-1 text-xs text-critical">
              {failure}
            </p>
          )}

          {items.length === 0 ? (
            drawings.status === "loading" ? (
              <p className="px-1 py-2 text-xs text-ink-muted">Reading…</p>
            ) : drawings.status === "error" ? null : (
              // Only when the read actually succeeded. "Nothing is drawn here" said after
              // a failed read is a claim about the instrument nobody has grounds for —
              // and it is precisely the sentence that must not be mistakable for one
              // (`terminal-chart` spec, "Instrument bez obiektów"); the failure above
              // stands on its own instead.
              <p className="px-1 py-2 text-xs text-ink-muted">
                Nothing is drawn on this instrument.
              </p>
            )
          ) : (
            <ul className="flex flex-col gap-1">
              {items.map((drawing) => (
                <li
                  key={drawing.id}
                  data-testid={`drawing-${drawing.id}`}
                  className="rounded border border-border px-2 py-1"
                >
                  <div className="flex items-baseline gap-2">
                    <span className="text-[10px] uppercase tracking-wide text-secondary">
                      {shapeLabel(drawing)}
                    </span>
                    <span className="text-xs text-ink">{priceSummary(drawing)}</span>
                    {drawing.label && (
                      <span className="truncate text-xs text-ink-muted">{drawing.label}</span>
                    )}
                    <span className="ml-auto flex gap-1">
                      <button
                        type="button"
                        onClick={() => {
                          setEditing(editing === drawing.id ? null : drawing.id);
                          setFailure(null);
                        }}
                        className="rounded border border-border px-1.5 text-[10px] text-ink hover:bg-panel-strong"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={busy === drawing.id}
                        aria-label={`Remove drawing ${drawing.id}`}
                        onClick={() => void act(drawing.id, () => drawings.remove(drawing.id))}
                        className="rounded border border-border px-1.5 text-[10px] text-ink hover:bg-panel-strong disabled:opacity-50"
                      >
                        Remove
                      </button>
                    </span>
                  </div>
                  <p className="text-[10px] text-secondary">
                    drawn {formatInstant(drawing.createdAt)}
                  </p>
                  {editing === drawing.id && (
                    <DrawingEditor
                      drawing={drawing}
                      busy={busy === drawing.id}
                      onSubmit={async (patch) => {
                        if (await act(drawing.id, () => drawings.patch(drawing.id, patch))) {
                          setEditing(null);
                        }
                      }}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** The prices and the caption of one object, editable. Built from `priceFields`, so a
 *  shape's own roles are the only ones it offers — the module refuses the others anyway,
 *  and offering a field that can only be refused is a form that lies. */
function DrawingEditor({
  drawing,
  busy,
  onSubmit,
}: {
  drawing: AgentChartDrawing;
  busy: boolean;
  onSubmit(patch: AgentDrawingPatch): Promise<void>;
}) {
  const fields = priceFields(drawing);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((field) => [field.role, String(field.value)])),
  );
  const [label, setLabel] = useState(drawing.label ?? "");

  function build(): AgentDrawingPatch | string {
    const patch: AgentDrawingPatch = {};
    for (const field of fields) {
      const raw = values[field.role] ?? "";
      const value = Number(raw);
      if (!Number.isFinite(value) || value <= 0) return `${field.label} must be a price above zero`;
      // Only what actually moved: sending every field back would make a correction of the
      // caption alone into a write of the prices too.
      if (value !== field.value) patch[field.role] = value;
    }
    const trimmed = label.trim();
    if (trimmed !== (drawing.label ?? "")) {
      if (trimmed === "") return "A caption cannot be blank — leave the old one or type a new one";
      patch.label = trimmed;
    }
    if (Object.keys(patch).length === 0) return "Nothing was changed";
    return patch;
  }

  const [problem, setProblem] = useState<string | null>(null);

  return (
    <form
      className="mt-1 flex flex-col gap-1"
      onSubmit={(event) => {
        event.preventDefault();
        const built = build();
        if (typeof built === "string") {
          setProblem(built);
          return;
        }
        setProblem(null);
        void onSubmit(built);
      }}
    >
      {fields.map((field) => (
        <label key={field.role} className="flex items-center gap-2 text-[10px] text-ink-muted">
          <span className="w-12">{field.label}</span>
          <input
            type="number"
            step="any"
            aria-label={`${field.label} of drawing ${drawing.id}`}
            value={values[field.role] ?? ""}
            onChange={(event) =>
              setValues({ ...values, [field.role]: event.target.value })
            }
            className="w-24 rounded border border-border bg-sunken px-1 text-xs text-ink"
          />
        </label>
      ))}
      <label className="flex items-center gap-2 text-[10px] text-ink-muted">
        <span className="w-12">Caption</span>
        <input
          type="text"
          aria-label={`Caption of drawing ${drawing.id}`}
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          className="w-40 rounded border border-border bg-sunken px-1 text-xs text-ink"
        />
      </label>
      {problem !== null && <p className="text-[10px] text-critical">{problem}</p>}
      <button
        type="submit"
        disabled={busy}
        className="self-start rounded border border-border px-1.5 py-0.5 text-[10px] text-ink hover:bg-panel-strong disabled:opacity-50"
      >
        Save
      </button>
    </form>
  );
}
