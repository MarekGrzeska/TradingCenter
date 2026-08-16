import { useMemo } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Edge,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AgentNode, type AgentFlowNode } from "./AgentNode";
import { layout } from "./teamDraft";
import type { TeamDefinition, TeamDependency, TeamsModel } from "./teamsApi";
import type { Refusal } from "./refusal";

const NODE_TYPES = { agent: AgentNode };

/**
 * The team as a picture of its dependencies, which is the point of the tab: a list of
 * roles shows everything except the one thing that makes a team a team (`terminal-teams`,
 * "Zespół jest widoczny jako obraz zależności, nie jako lista ról").
 *
 * Nodes are placed by `layout`, not dragged: the module's wire carries a definition, not
 * coordinates, so a position moved by hand would be lost on the next read and the
 * operator would be the last to know. Depth-ordered columns give the one property the
 * spec actually asks for — the direction of work readable without clicking.
 */
export function TeamCanvas({
  definition,
  models,
  selectedKey,
  refusal,
  runStatuses,
  onSelect,
  onConnect,
  onDisconnect,
}: {
  definition: TeamDefinition;
  models: TeamsModel[];
  selectedKey: string | null;
  refusal: Refusal | null;
  /** Each agent's step in the run being watched, when this canvas is watching one. The
   *  editor passes nothing and gets the same picture without badges — one component, so
   *  a run is followed on the graph the operator composed rather than on a second
   *  drawing of it (`terminal-teams`). */
  runStatuses?: Map<string, string>;
  onSelect(key: string | null): void;
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
    const positions = layout(definition);
    return definition.agents.map((agent) => ({
      id: agent.key,
      type: "agent" as const,
      position: positions.get(agent.key) ?? { x: 0, y: 0 },
      selected: agent.key === selectedKey,
      data: {
        role: agent.role,
        modelLabel: modelLabels.get(agent.modelId) ?? agent.modelId,
        toolCount: agent.tools.length,
        refused: refusedAgents.has(agent.key),
        runStatus: runStatuses?.get(agent.key),
      },
    }));
  }, [definition, modelLabels, refusedAgents, runStatuses, selectedKey]);

  const edges: Edge[] = useMemo(
    () =>
      definition.dependencies.map((edge) => ({
        id: edgeId(edge),
        source: edge.from,
        target: edge.to,
        style: refusedEdges.has(edgeId(edge))
          ? { stroke: "var(--color-critical)", strokeWidth: 2 }
          : undefined,
      })),
    [definition.dependencies, refusedEdges],
  );

  const handleNodeClick: NodeMouseHandler = (_event, node) => onSelect(node.id);

  return (
    <div className="h-full min-h-0 w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        nodesDraggable={false}
        nodesConnectable={onConnect !== undefined}
        edgesReconnectable={false}
        fitView
        onNodeClick={handleNodeClick}
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
