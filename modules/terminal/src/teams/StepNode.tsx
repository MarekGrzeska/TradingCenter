import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

/** A step on the canvas: a recipe the module runs without a model (`terminal-teams`, "Krok widać na obrazie
 *  zespołu"). Drawn apart from an agent so the two never read as the same kind of thing. */
export type StepNodeData = {
  recipe: string;
  /** The deposit override, or `null` when the strategy document sizes the position. */
  deposit: string | null;
  refused: boolean;
  runStatus?: string;
  onOpenSettings?: () => void;
  [key: string]: unknown;
};

const RUN_STATUS: Record<string, { label: string; className: string }> = {
  pending: { label: "waiting", className: "text-ink-faint" },
  running: { label: "working", className: "text-primary" },
  completed: { label: "done", className: "text-good" },
  failed: { label: "failed", className: "text-critical" },
};

export type StepFlowNode = Node<StepNodeData, "step">;

export function StepNode({ data, selected }: NodeProps<StepFlowNode>) {
  const border = data.refused
    ? "border-critical"
    : data.runStatus === "running"
      ? "border-primary"
      : selected
        ? "border-primary-line"
        : "border-border";
  const run =
    data.runStatus === undefined
      ? null
      : (RUN_STATUS[data.runStatus] ?? { label: data.runStatus, className: "text-ink-muted" });

  return (
    <div
      className={`relative min-w-48 rounded border-2 border-dashed ${border} bg-panel-strong px-3 py-2 text-left shadow-sm`}
      data-testid={`step-node-${data.recipe}`}
    >
      <Handle type="target" position={Position.Left} />
      {data.onOpenSettings && (
        <button
          type="button"
          aria-label={`Settings for step ${data.recipe}`}
          title="Step settings"
          onClick={(event) => {
            event.stopPropagation();
            data.onOpenSettings?.();
          }}
          className="nodrag nopan absolute right-1 top-1 cursor-pointer rounded border border-transparent px-1 text-xs text-ink-faint hover:border-border hover:text-ink"
        >
          ⚙
        </button>
      )}
      <div className="text-[0.65rem] uppercase tracking-wide text-ink-faint">step · no model</div>
      <div className="pr-6 text-sm font-semibold text-ink">{data.recipe}</div>
      <div className="text-xs text-ink-muted">
        deposit: {data.deposit ?? "from the strategy document"}
      </div>
      {run && (
        <div className={`mt-1 text-xs ${run.className}`} data-testid="step-run-status">
          {run.label}
        </div>
      )}
      {data.refused && <div className="mt-1 text-xs text-critical">refused</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
