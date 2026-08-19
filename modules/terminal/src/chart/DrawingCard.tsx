import { useState } from "react";
import type { AgentChartDrawing } from "../agent/agentApi";
import { formatInstant } from "../ui/formatTime";
import type { ChartDrawings } from "./Chart";
import { DrawingEditor } from "./DrawingEditor";
import { cardPosition } from "./cardPosition";
import { priceSummary, shapeLabel } from "./drawingFields";
import { Button } from "../ui/Button";

/**
 * What the picked object is, said beside it.
 *
 * The question this answers — "what is this line" — could already be answered by opening
 * the list in the header and finding the object by its price. That is a long way round
 * for something the operator is already pointing at (`terminal-chart-objects` spec,
 * "Wskazany obiekt mówi, czym jest").
 *
 * It is DOM over the canvas rather than drawing on it: it has buttons and a field to type
 * a price into, and painting a form onto a canvas means writing hit-testing for buttons,
 * text selection and keyboard handling that the browser already has (design.md, "Karta
 * obiektu jest DOM-em nad canvasem").
 *
 * Both writes come from `ChartDrawings` — the same `remove` and `patch` the list calls —
 * so "Save" here and "Save" there are one behaviour, down to what a failure leaves on
 * screen.
 */
export interface DrawingCardProps {
  drawing: AgentChartDrawing;
  drawings: ChartDrawings;
  /** Where the operator clicked, in the pane's own coordinates, or null when the object
   *  was picked from the list rather than off the chart. */
  at: { x: number; y: number } | null;
  onClose(): void;
}

export function DrawingCard({ drawing, drawings, at, onClose }: DrawingCardProps) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function act(run: () => Promise<string | null>): Promise<boolean> {
    setBusy(true);
    setFailure(null);
    const problem = await run();
    setBusy(false);
    setFailure(problem);
    return problem === null;
  }

  return (
    <div
      data-testid={`drawing-card-${drawing.id}`}
      // Positioned by the pane it sits in, measured live so a resized chart does not leave
      // the card hanging off it.
      ref={(node) => {
        if (!node) return;
        const pane = node.offsetParent as HTMLElement | null;
        const { left, top } = cardPosition(at, {
          width: pane?.clientWidth ?? 0,
          height: pane?.clientHeight ?? 0,
        });
        node.style.left = `${left}px`;
        node.style.top = `${top}px`;
      }}
      className="absolute z-20 w-56 rounded border border-border-strong bg-panel p-2 shadow-lg"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-[10px] tracking-wide text-secondary uppercase">
          {shapeLabel(drawing)}
        </span>
        <span className="text-xs text-ink">{priceSummary(drawing)}</span>
        <Button
          size="2xs"
          className="ml-auto"
          aria-label="Close object card"
          onClick={onClose}
        >
          ✕
        </Button>
      </div>

      {drawing.label && <p className="mt-0.5 truncate text-xs text-ink-muted">{drawing.label}</p>}
      <p className="text-[10px] text-secondary">
        drawn {formatInstant(drawing.createdAt)}
        {drawing.hidden && <span className="ml-1 text-warning uppercase">· hidden</span>}
      </p>

      {failure !== null && (
        <p className="mt-1 rounded border border-critical/40 px-1.5 py-0.5 text-[10px] text-critical">
          {failure}
        </p>
      )}

      <div className="mt-1 flex gap-1">
        <Button
          size="2xs"
          onClick={() => {
            setEditing(!editing);
            setFailure(null);
          }}
        >
          Edit
        </Button>
        <Button
          size="2xs"
          disabled={busy}
          aria-label={drawing.hidden ? `Show drawing ${drawing.id}` : `Hide drawing ${drawing.id}`}
          // The card stays open afterwards, with this button flipped: hiding is undoable,
          // and the nearest way back has to be where the action happened rather than in
          // the list (`terminal-chart-objects` spec, "Zgaszenie z opisu").
          onClick={() => void act(() => drawings.patch(drawing.id, { hidden: !drawing.hidden }))}
        >
          {drawing.hidden ? "Show" : "Hide"}
        </Button>
        <Button
          size="2xs"
          disabled={busy}
          aria-label={`Remove drawing ${drawing.id}`}
          // The selection is not put down here: the object leaving the list is what does
          // that, and a removal that failed must not look like one that worked
          // (`terminal-chart-objects` spec, "Usunięcie wskazanego obiektu MUST zdjąć
          // wskazanie razem z nim").
          onClick={() => void act(() => drawings.remove(drawing.id))}
        >
          Remove
        </Button>
      </div>

      {editing && (
        <DrawingEditor
          drawing={drawing}
          busy={busy}
          onSubmit={async (patch) => {
            if (await act(() => drawings.patch(drawing.id, patch))) setEditing(false);
          }}
        />
      )}
    </div>
  );
}
