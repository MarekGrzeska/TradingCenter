import { BaseEdge, EdgeLabelRenderer, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react";
import type { TeamDependency } from "./teamsApi";

export type DependencyEdgeData = {
  /** Absent while a run is watched: its revision is saved and immutable, so there is
   *  nothing on that picture to take away. */
  onRemove?(edge: TeamDependency): void;
  refused: boolean;
  [key: string]: unknown;
};

export type DependencyFlowEdge = Edge<DependencyEdgeData, "dependency">;

/**
 * One dependency, with the way to take it away sitting on the dependency itself.
 *
 * The panel can remove one too, and did first — but the panel removes it from the agent
 * that was picked, which means finding that agent before removing a line the operator is
 * already pointing at. A cross on the line is where the action is (`terminal-teams`,
 * "Operator składa zespół w tym samym widoku, w którym go ogląda").
 *
 * Deliberately not the Delete key: React Flow's own key deletes whatever is selected, and
 * on this canvas that includes agents — a keystroke that removes a line here and a whole
 * role there is a keystroke nobody can trust.
 */
export function DependencyEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<DependencyFlowEdge>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const onRemove = data?.onRemove;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={
          data?.refused ? { stroke: "var(--color-critical)", strokeWidth: 2 } : undefined
        }
      />
      {onRemove && (
        <EdgeLabelRenderer>
          <button
            type="button"
            aria-label={`Remove dependency: ${source} to ${target}`}
            onClick={() => onRemove({ from: source, to: target })}
            // `pointer-events: auto` because the layer this renders into has them off:
            // it sits over the whole canvas, and anything but the labels themselves would
            // swallow every pan and every click on a node.
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "auto",
            }}
            className="absolute cursor-pointer rounded-full border border-border bg-panel px-1.5 text-xs leading-4 text-ink-muted hover:border-critical hover:text-critical"
          >
            ×
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
