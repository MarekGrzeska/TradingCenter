import { ModalShell } from "../ui/ModalShell";
import { Button } from "../ui/Button";
import type { Refusal } from "./refusal";
import type { StepRecipe, TeamStep } from "./teamsApi";

/** What an empty parameter is called where the module gives it a meaning of its own. */
const EMPTY_MEANS: Record<string, string> = {
  deposit_fraction: "from the strategy document",
  max_bar_age_seconds: "no limit",
};

/**
 * One step's parameters, drawn from the recipe the module publishes rather than from code per recipe here
 * (`terminal-teams`, "Krok widać na obrazie zespołu"). An empty field leaves the parameter out entirely.
 */
export function StepSettingsDialog({
  step,
  recipe,
  refusal,
  onChange,
  onClose,
  onRemove,
}: {
  step: TeamStep;
  /** `undefined` when the module no longer publishes the recipe — the parameters still show, as saved. */
  recipe: StepRecipe | undefined;
  refusal: Refusal | null;
  onChange(params: Record<string, unknown>): void;
  onClose(): void;
  onRemove(): void;
}) {
  const refusedHere = refusal?.agents.includes(step.key) ?? false;
  const params = recipe?.params ?? Object.keys(step.params).map((name) => ({
    name,
    type: "text" as const,
    required: false,
    description: "",
  }));

  function set(name: string, type: string, raw: string) {
    const next = { ...step.params };
    if (raw.trim() === "") delete next[name];
    // An integer the module reads as a number; anything that does not parse is kept as typed, so the
    // module's refusal names it instead of this field quietly dropping it.
    else if (type === "integer" && /^-?\d+$/.test(raw.trim())) next[name] = Number(raw.trim());
    else next[name] = raw.trim();
    onChange(next);
  }

  return (
    <ModalShell
      title={`Step: ${step.recipe}`}
      showCloseButton
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <Button tone="critical" onClick={onRemove}>
            Remove step
          </Button>
          <Button tone="primary" size="md" onClick={onClose}>
            Done
          </Button>
        </div>
      }
    >
      {refusedHere && refusal && (
        <p className="mb-3 rounded border border-critical bg-panel px-2 py-1 text-xs text-critical">
          {refusal.message}
        </p>
      )}
      <p className="mb-3 text-xs text-ink-muted">
        {recipe?.description ?? "The module no longer publishes this recipe; the next run will be refused."}
      </p>
      <div className="flex flex-col gap-3">
        {params.map((param) => {
          const value = step.params[param.name];
          const id = `step-param-${param.name}`;
          return (
            <div key={param.name} className="flex flex-col gap-1">
              <label htmlFor={id} className="text-xs uppercase tracking-wide text-ink-faint">
                {param.name}
                {param.required && " *"}
              </label>
              <input
                id={id}
                value={value === undefined || value === null ? "" : String(value)}
                placeholder={EMPTY_MEANS[param.name] ?? (param.required ? "required" : "default")}
                onChange={(event) => set(param.name, param.type, event.target.value)}
                className="w-full rounded border border-border bg-panel px-2 py-1 text-sm text-ink"
              />
              {param.description && <span className="text-xs text-ink-faint">{param.description}</span>}
            </div>
          );
        })}
      </div>
    </ModalShell>
  );
}
