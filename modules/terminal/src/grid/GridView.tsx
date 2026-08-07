import { useSyncExternalStore } from "react";
import { Chart } from "../chart/Chart";
import { sourceStore } from "../data/sourceStore";
import { gridStore } from "./gridStore";
import { SymbolField } from "./SymbolField";
import { LAYOUTS, LAYOUT_IDS, visibleSlotIds, type SlotId } from "./model";

export function GridView() {
  const source = useSyncExternalStore(sourceStore.subscribe, sourceStore.getSnapshot);
  const config = useSyncExternalStore(gridStore.subscribe, gridStore.getSnapshot);

  const visible = visibleSlotIds(config.layout);
  const { cols, rows } = LAYOUTS[config.layout];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
        <span className="text-xs text-ink-muted">Layout</span>
        <div className="flex gap-1" role="group" aria-label="Layout">
          {LAYOUT_IDS.map((id) => (
            <button
              key={id}
              type="button"
              aria-pressed={config.layout === id}
              onClick={() => gridStore.setLayout(id)}
              className={`rounded border px-2 py-0.5 text-xs transition-colors ${
                config.layout === id
                  ? "border-accent text-ink"
                  : "border-border text-ink-muted hover:text-ink"
              }`}
            >
              {id}
            </button>
          ))}
        </div>
      </div>

      <div
        className="grid min-h-0 flex-1 gap-px bg-border p-px"
        style={{
          gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
        }}
      >
        {visible.map((slotId) => (
          <Slot key={slotId} slotId={slotId} active={config.activeSlot === slotId} source={source} />
        ))}
      </div>
    </div>
  );
}

function Slot({
  slotId,
  active,
  source,
}: {
  slotId: SlotId;
  active: boolean;
  source: ReturnType<typeof sourceStore.getSnapshot>;
}) {
  const config = useSyncExternalStore(gridStore.subscribe, gridStore.getSnapshot);
  const slot = config.slots[slotId];

  return (
    // Marking the slot the moment focus lands anywhere inside it, not just on
    // a click, so keyboard users get the same "actions land here" signal
    // (terminal-grid spec, "Który slot jest aktywny").
    <div
      onMouseDown={() => gridStore.setActiveSlot(slotId)}
      onFocusCapture={() => gridStore.setActiveSlot(slotId)}
      data-testid={`slot-${slotId}`}
      data-active={active}
      className={`relative min-h-0 min-w-0 -outline-offset-2 ${
        active ? "outline-2 outline-accent" : ""
      }`}
    >
      {slot.symbol === null ? (
        <EmptySlot slotId={slotId} />
      ) : (
        <Chart
          source={source}
          symbol={slot.symbol}
          resolution={slot.resolution}
          onResolutionChange={(resolution) => gridStore.setSlotResolution(slotId, resolution)}
          headerLeft={
            <span className="flex items-center gap-1">
              <SymbolField
                label={`Symbol for slot ${slotId}`}
                value={slot.symbol}
                onCommit={(symbol) => gridStore.setSlotSymbol(slotId, symbol)}
              />
              <button
                type="button"
                aria-label={`Clear slot ${slotId}`}
                title="Empty this slot"
                onClick={() => gridStore.clearSlotSymbol(slotId)}
                className="px-1 text-xs text-ink-muted hover:text-ink"
              >
                ×
              </button>
            </span>
          }
        />
      )}
    </div>
  );
}

function EmptySlot({ slotId }: { slotId: SlotId }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 bg-panel">
      <p className="text-sm text-ink-muted">Pick an instrument for this slot.</p>
      <SymbolField
        label={`Symbol for slot ${slotId}`}
        value={null}
        onCommit={(symbol) => gridStore.setSlotSymbol(slotId, symbol)}
      />
      <p className="text-xs text-ink-muted">or find one on the Instruments tab</p>
    </div>
  );
}
