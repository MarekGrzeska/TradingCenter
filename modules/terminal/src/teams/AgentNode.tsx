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
      className={`min-w-44 rounded border ${border} bg-panel px-3 py-2 text-left shadow-sm`}
      data-testid={`agent-node-${data.role}`}
    >
      {/* Both handles always present: an agent with no dependency today is one an edge
          can be drawn to tomorrow, and a handle that appears on hover is a handle nobody
          finds. */}
      <Handle type="target" position={Position.Left} />
      <div className="text-sm font-semibold text-ink">{data.role}</div>
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
