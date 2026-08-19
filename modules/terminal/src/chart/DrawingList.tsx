import { useState } from "react";
import type { ChartDrawings } from "./Chart";
import { DrawingEditor } from "./DrawingEditor";
import { priceSummary, shapeLabel } from "./drawingFields";
import { formatInstant } from "../ui/formatTime";
import { Button } from "../ui/Button";

/**
 * The objects standing on this instrument, and one of the two ways the operator takes one
 * off — the other being the card beside the object itself.
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
  /** Which object is picked out, and how to change that. Held by `Chart` rather than
   *  here, because the chart shows the same pick — two pieces of state would be two
   *  answers to "which object is chosen", one of them always stale
   *  (`terminal-chart-objects` spec, "Wskazanie jest jedno, wspólne z listą"). */
  selectedId: number | null;
  onSelect(id: number | null): void;
}

export function DrawingList({ drawings, selectedId, onSelect }: DrawingListProps) {
  const [open, setOpen] = useState(false);
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
      <Button
        className="h-6"
        onClick={() => {
          setOpen(!open);
          setFailure(null);
        }}
        aria-expanded={open}
        aria-label="Drawn objects"
      >
        Objects{items.length > 0 ? ` (${items.length})` : ""}
        {drawings.status === "error" && <span className="ml-1 text-critical">!</span>}
      </Button>

      {open && (
        <div className="absolute top-7 left-0 z-20 max-h-96 w-80 overflow-y-auto rounded border border-border bg-panel p-2 shadow-lg">
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
                  aria-current={selectedId === drawing.id}
                  data-hidden={drawing.hidden}
                  className={
                    (selectedId === drawing.id
                      ? "rounded border border-primary bg-panel-strong px-2 py-1"
                      : "rounded border border-border px-2 py-1") +
                    // Faded, but never dropped: this list is the only way back to a
                    // hidden object, so one that left it would be hidden for good
                    // (`terminal-chart` spec, "Operator zarządza naniesionymi obiektami
                    // z listy").
                    (drawing.hidden ? " opacity-60" : "")
                  }
                >
                  <div className="flex items-baseline gap-2">
                    <span className="text-[10px] tracking-wide text-secondary uppercase">
                      {shapeLabel(drawing)}
                    </span>
                    {drawing.hidden && (
                      // Said in a word rather than by the fading alone: the operator has
                      // to be able to tell "hidden" from "not selected".
                      <span className="text-[10px] tracking-wide text-warning uppercase">
                        hidden
                      </span>
                    )}
                    <span className="text-xs text-ink">{priceSummary(drawing)}</span>
                    {drawing.label && (
                      <span className="truncate text-xs text-ink-muted">{drawing.label}</span>
                    )}
                    <span className="ml-auto flex gap-1">
                      <Button
                        size="2xs"
                        // Picking a row out is the same act as clicking the object on the
                        // chart, and opens the same editor — the row is where the editor
                        // appears, the chart is where the card does.
                        onClick={() => {
                          onSelect(selectedId === drawing.id ? null : drawing.id);
                          setFailure(null);
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        size="2xs"
                        disabled={busy === drawing.id}
                        aria-label={
                          drawing.hidden ? `Show drawing ${drawing.id}` : `Hide drawing ${drawing.id}`
                        }
                        onClick={() =>
                          void act(drawing.id, () =>
                            drawings.patch(drawing.id, { hidden: !drawing.hidden }),
                          )
                        }
                      >
                        {drawing.hidden ? "Show" : "Hide"}
                      </Button>
                      <Button
                        size="2xs"
                        disabled={busy === drawing.id}
                        aria-label={`Remove drawing ${drawing.id}`}
                        onClick={() => void act(drawing.id, () => drawings.remove(drawing.id))}
                      >
                        Remove
                      </Button>
                    </span>
                  </div>
                  <p className="text-[10px] text-secondary">
                    drawn {formatInstant(drawing.createdAt)}
                  </p>
                  {selectedId === drawing.id && (
                    <DrawingEditor
                      drawing={drawing}
                      busy={busy === drawing.id}
                      onSubmit={async (patch) => {
                        if (await act(drawing.id, () => drawings.patch(drawing.id, patch))) {
                          onSelect(null);
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
