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
  [key: string]: unknown;
};

export type AgentFlowNode = Node<AgentNodeData, "agent">;

export function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const border = data.refused
    ? "border-critical"
    : selected
      ? "border-primary-line"
      : "border-border";

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
      {data.refused && <div className="mt-1 text-xs text-critical">refused</div>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
