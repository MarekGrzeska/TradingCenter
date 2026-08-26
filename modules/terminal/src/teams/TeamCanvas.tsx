import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AgentNode, type AgentFlowNode } from "./AgentNode";
import { DependencyEdge, type DependencyFlowEdge } from "./DependencyEdge";
import { layout } from "./teamDraft";
import type { TeamDefinition, TeamDependency, TeamLayout, TeamsModel } from "./teamsApi";
import type { Refusal } from "./refusal";

const NODE_TYPES = { agent: AgentNode };
const EDGE_TYPES = { dependency: DependencyEdge };

/**
 * The team as a picture of its dependencies (`terminal-teams`). Positions come from the module's remembered
 * layout, then `layout()` for anything it does not name; moving a node is not an edit and takes its own route.
 */
export function TeamCanvas({
  definition,
  models,
  selectedKey,
  refusal,
  runStatuses,
  places,
  onSelect,
  onOpenSettings,
  onMove,
  onConnect,
  onDisconnect,
}: {
  definition: TeamDefinition;
  models: TeamsModel[];
  selectedKey: string | null;
  refusal: Refusal | null;
  /** What the module remembers for this team. Agents it does not name fall back to
   *  `layout()`; a monitor watching a run passes it too, so a run is watched on the
   *  arrangement the operator built rather than on a second one. */
  places?: TeamLayout;
  /** Each agent's step in the run being watched, when this canvas is watching one. The
   *  editor passes nothing and gets the same picture without badges — one component, so
   *  a run is followed on the graph the operator composed rather than on a second
   *  drawing of it (`terminal-teams`). */
  runStatuses?: Map<string, string>;
  onSelect(key: string | null): void;
  /** Puts a gear on every box, which is how an agent's settings are opened
   *  (`AgentSettingsDialog`). Left out while a run is watched — that revision is saved,
   *  and there is nothing on that picture to edit. */
  onOpenSettings?(agentKey: string): void;
  /** Called once, when the node is let go — not on every frame of the drag. Left out
   *  while a run is watched: nothing there is the operator's to rearrange mid-run. */
  onMove?(agentKey: string, at: { x: number; y: number }): void;
  /** Left out while a run is being watched: its revision is saved and immutable, and a
   *  handle that draws an edge nothing will keep is a handle that lies. */
  onConnect?(edge: TeamDependency): void;
  onDisconnect?(edge: TeamDependency): void;
}) {
  const modelLabels = useMemo(
    () => new Map(models.map((model) => [model.id, model.displayName])),
    [models],
  );
  const refusedAgents = useMemo(() => new Set(refusal?.agents ?? []), [refusal]);
  const refusedEdges = useMemo(
    () => new Set((refusal?.dependencies ?? []).map(edgeId)),
    [refusal],
  );

  const nodes: AgentFlowNode[] = useMemo(() => {
    const computed = layout(definition);
    return definition.agents.map((agent) => ({
      id: agent.key,
      type: "agent" as const,
      position: places?.get(agent.key) ?? computed.get(agent.key) ?? { x: 0, y: 0 },
      selected: agent.key === selectedKey,
      data: {
        role: agent.role,
        modelLabel: modelLabels.get(agent.modelId) ?? agent.modelId,
        toolCount: agent.tools.length,
        refused: refusedAgents.has(agent.key),
        runStatus: runStatuses?.get(agent.key),
        onOpenSettings: onOpenSettings ? () => onOpenSettings(agent.key) : undefined,
      },
    }));
  }, [definition, modelLabels, onOpenSettings, places, refusedAgents, runStatuses, selectedKey]);

  const edges: DependencyFlowEdge[] = useMemo(
    () =>
      definition.dependencies.map((edge) => ({
        id: edgeId(edge),
        type: "dependency" as const,
        source: edge.from,
        target: edge.to,
        data: { onRemove: onDisconnect, refused: refusedEdges.has(edgeId(edge)) },
      })),
    [definition.dependencies, onDisconnect, refusedEdges],
  );

  const handleNodeClick: NodeMouseHandler = (_event, node) => onSelect(node.id);
  // The gear on the box is the way that is visible; this is the way that gets guessed.
  // Both open the same dialog, so neither has to be the one an operator finds.
  const handleNodeDoubleClick: NodeMouseHandler = (_event, node) => onOpenSettings?.(node.id);

  return (
    /* `teams-canvas` is where the library's chrome is given this terminal's tokens
       (index.css) — without it the zoom buttons and the connection handles render in
       React Flow's light defaults, which on this surface means invisible. */
    <div className="teams-canvas h-full min-h-0 w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        nodesDraggable={onMove !== undefined}
        nodesConnectable={onConnect !== undefined}
        edgesReconnectable={false}
        fitView
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onNodeDragStop={(_event, node) => onMove?.(node.id, node.position)}
        onPaneClick={() => onSelect(null)}
        onConnect={(connection: Connection) => {
          if (onConnect && connection.source && connection.target) {
            onConnect({ from: connection.source, to: connection.target });
          }
        }}
        onEdgesDelete={(deleted) => {
          if (!onDisconnect) return;
          for (const edge of deleted) onDisconnect({ from: edge.source, to: edge.target });
        }}
        proOptions={{ hideAttribution: false }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function edgeId(edge: TeamDependency): string {
  return `${edge.from}->${edge.to}`;
}
