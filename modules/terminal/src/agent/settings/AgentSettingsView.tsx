import { CollapsibleSection } from "../../ui/CollapsibleSection";
import { AgentCostView } from "../cost/AgentCostView";
import { PromptManagementView } from "./PromptManagementView";

/**
 * Where the operator's agent-facing settings live — sections stacked, each collapsible
 * on its own so a page with several of them stays scannable. Cost is the first section;
 * others join the same way, this file growing one `CollapsibleSection` at a time rather
 * than each getting its own tab.
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
