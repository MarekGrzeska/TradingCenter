import { CollapsibleSection } from "../../ui/CollapsibleSection";
import { AgentCostView } from "../cost/AgentCostView";
import { PromptManagementView } from "./PromptManagementView";

/**
 * Where the operator's agent-facing settings live — sections stacked, each collapsible on its own. Cost
 * is the first; others join the same way, one `CollapsibleSection` at a time rather than one tab each.
 */
export function AgentSettingsView() {
  return (
    <div className="h-full min-h-0 overflow-auto p-4">
      <div className="flex flex-col gap-3">
        <CollapsibleSection title="Agent cost">
          <AgentCostView />
        </CollapsibleSection>
        <CollapsibleSection title="Prompt management">
          <PromptManagementView />
        </CollapsibleSection>
      </div>
    </div>
  );
}
