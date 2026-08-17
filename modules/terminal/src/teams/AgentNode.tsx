import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

/** What one agent shows on the canvas. The role and the model are required by
 *  `terminal-teams` ("Przy każdym agencie MUST być widoczna jego rola i model"); the
 *  rest is what makes a node worth looking at before clicking it. */
export type AgentNodeData = {
  role: string;
  /** The catalogue's display name where the module knows the model, and the raw id where
   *  it does not — a revision saved on a model since withdrawn still has to render, and
   *  showing nothing there would hide exactly the thing that will refuse the next run. */
  modelLabel: string;
  toolCount: number;
  /** Set when the module's last refusal named this agent — see `refusal.ts`. */
  refused: boolean;
  /** This agent's step in the run being watched, when one is: `pending`, `running`,
   *  `completed` or `failed`. Absent while the team is merely being edited — the same
   *  node draws both, because it is the same graph (`terminal-teams`, "Przebieg widać na
   *  obrazie zespołu"). */
  runStatus?: string;
  /** Opens this agent's settings. Absent while a run is watched: that revision is saved
   *  and immutable, and a gear that opens fields nothing will keep is a gear that lies. */
  onOpenSettings?: () => void;
  [key: string]: unknown;
};

/** What each step status is called on the node, and in what colour. Waiting is deliberately
 *  as visible as working: an operator's first question about a run that looks stuck is
 *  which agents have not started. */
const RUN_STATUS: Record<string, { label: string; className: string }> = {
  pending: { label: "waiting", className: "text-ink-faint" },
  running: { label: "working", className: "text-primary" },
  completed: { label: "done", className: "text-good" },
  failed: { label: "failed", className: "text-critical" },
};

export type AgentFlowNode = Node<AgentNodeData, "agent">;

export function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const border = data.refused
    ? "border-critical"
    : data.runStatus === "running"
      ? "border-primary"
      : selected
        ? "border-primary-line"
        : "border-border";
  // An unknown status still shows, under its own name: the module owns that vocabulary,
  // and a badge that disappears when it grows a value is worse than one reading `queued`.
  const run =
    data.runStatus === undefined
      ? null
      : (RUN_STATUS[data.runStatus] ?? { label: data.runStatus, className: "text-ink-muted" });

  return (
    <div
      className={`relative min-w-48 rounded border ${border} bg-panel px-3 py-2 text-left shadow-sm`}
      data-testid={`agent-node-${data.role}`}
    >
      {/* Both handles always present: an agent with no dependency today is one an edge
          can be drawn to tomorrow, and a handle that appears on hover is a handle nobody
          finds. */}
      <Handle type="target" position={Position.Left} />
      {data.onOpenSettings && (
        /* `nodrag nopan` are React Flow's own opt-outs: without them a press here starts
           dragging the node instead of pressing a button, and the click never lands. The
           gear is always visible for the same reason both handles are — one that appears
           on hover is one nobody finds. */
        <button
          type="button"
          aria-label={`Settings for ${data.role}`}
          title="Agent settings"
          onClick={(event) => {
            event.stopPropagation();
            data.onOpenSettings?.();
          }}
          className="nodrag nopan absolute right-1 top-1 cursor-pointer rounded border border-transparent p-1 text-ink-faint hover:border-border hover:bg-panel-strong hover:text-ink"
        >
          <GearIcon />
        </button>
      )}
      <div className="pr-6 text-sm font-semibold text-ink">{data.role}</div>
      <div className="text-xs text-ink-muted">{data.modelLabel}</div>
      <div className="text-xs text-ink-faint">
        {data.toolCount === 0 ? "no tools" : `${data.toolCount} tool${data.toolCount === 1 ? "" : "s"}`}
      </div>
      {run && (
        <div className={`mt-1 text-xs ${run.className}`} data-testid="agent-run-status">
          {run.label}
        </div>
      )}
      {data.refused && <div className="mt-1 text-xs text-critical">refused</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

/** Drawn from primitives rather than pulled from an icon set: this terminal has no icon
 *  dependency, and one added for a single glyph is a dependency to keep for a single
 *  glyph. */
function GearIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <circle cx="8" cy="8" r="3" />
        <path d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3.05 3.05l1.13 1.13M11.82 11.82l1.13 1.13M12.95 3.05l-1.13 1.13M4.18 11.82l-1.13 1.13" />
      </g>
    </svg>
  );
}
