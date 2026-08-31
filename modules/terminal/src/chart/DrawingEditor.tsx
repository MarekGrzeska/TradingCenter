import { useState } from "react";
import type { AgentChartDrawing, AgentDrawingPatch } from "../agent/agentApi";
import { priceFields } from "./drawingFields";
import { Button } from "../ui/Button";

/**
 * Built from `priceFields`, so a shape offers only its own roles — a field that can only be refused is a form
 * that lies. One component for the list and the card, because "Save" has to mean the same thing in both.
 */
export function DrawingEditor({
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
            onChange={(event) => setValues({ ...values, [field.role]: event.target.value })}
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
      <Button
        size="2xs"
        className="self-start"
        type="submit"
        disabled={busy}
      >
        Save
      </Button>
    </form>
  );
}
