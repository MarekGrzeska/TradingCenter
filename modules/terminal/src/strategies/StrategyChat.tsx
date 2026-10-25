import { useEffect, useSyncExternalStore } from "react";
import type { AgentChatStore } from "../agent/agentChatStore";
import { Composer, ModelPicker, Transcript } from "../agent/ChatParts";

/**
 * The conversation beside a strategy's editor (`terminal-strategies`, „Okno tworzenia strategii ma własny czat z agentem”),
 * on its own store (`createStrategyChatStore`).
 */
export function StrategyChat({ store }: { store: AgentChatStore }) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const turnInFlight = state.turn?.status === "waiting" || state.turn?.status === "streaming";

  // "Expanded" is what makes the store load its models and transcript; with no storage it is remembered nowhere.
  useEffect(() => {
    store.setExpanded(true);
  }, [store]);

  return (
    <aside aria-label="Czat strategii" className="flex min-h-0 flex-col rounded border border-primary-line bg-panel">
      <header className="flex h-9 shrink-0 items-center border-b border-primary-line bg-panel-strong px-3 text-xs font-semibold text-ink">
        Agent — rozmowa tej strategii
      </header>
      <Transcript
        messages={state.messages}
        turn={state.turn}
        unclaimedToolCalls={state.unclaimedToolCalls}
        emptyText="Opisz strategię po polsku: agent dopyta, napisze dokument i go zapisze. Widzi też Twoje niezapisane zmiany."
      />
      <Composer
        onSend={(text) => store.send(text)}
        onStop={() => store.stop()}
        disabled={turnInFlight}
        placeholder="Opisz strategię albo poproś o zmianę…"
      >
        <ModelPicker state={state} onChange={(modelId) => store.setModel(modelId)} />
      </Composer>
    </aside>
  );
}
