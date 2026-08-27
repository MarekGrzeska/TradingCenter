import { useEffect, useMemo, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { Chart, type ChartDrawings } from "../chart/Chart";
import { drawingsStore } from "../agent/drawingsStore";
import { archive, indicators, marketData } from "../data/marketData";
import type { Resolution, TrackedPair } from "../data/types";
import { useTrackedPairs } from "../instruments/useTrackedPairs";
import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import { gridStore } from "./gridStore";
import { SymbolField } from "./SymbolField";
import { LAYOUTS, LAYOUT_IDS, visibleSlotIds, type SlotId } from "./model";
import { Button } from "../ui/Button";

function groupResolutionsBySymbol(pairs: TrackedPair[]): Map<string, Resolution[]> {
  const map = new Map<string, Resolution[]>();
  for (const pair of pairs) {
    const resolutions = map.get(pair.symbol) ?? [];
    resolutions.push(pair.resolution);
    map.set(pair.symbol, resolutions);
  }
  return map;
}

export function GridView() {
  // The layout and the active slot, not the whole config: six charts hang off this component, and reading it
  // whole re-rendered all six whenever one slot changed. A subscription is per value.
  const layout = useSyncExternalStore(gridStore.subscribe, () => gridStore.getSnapshot().layout);
  const activeSlot = useSyncExternalStore(
    gridStore.subscribe,
    () => gridStore.getSnapshot().activeSlot,
  );
  // Read once and shared by every slot, rather than one poll per slot — six
  // slots asking independently would be six requests for the same list.
  const archived = useTrackedPairs(archive);
  const resolutionsBySymbol = useMemo(
    () => groupResolutionsBySymbol(archived.pairs),
    [archived.pairs],
  );

  // Everything the pickers offer, sorted once for all of them.
  const symbols = useMemo(
    () => [...resolutionsBySymbol.keys()].sort((a, b) => a.localeCompare(b)),
    [resolutionsBySymbol],
  );

  const visible = visibleSlotIds(layout);
  const { cols, rows } = LAYOUTS[layout];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
        <span className="text-[11px] uppercase tracking-wide text-secondary">Layout</span>
        <div className="flex gap-1" role="group" aria-label="Layout">
          {LAYOUT_IDS.map((id) => (
            <button
              key={id}
              type="button"
              aria-pressed={layout === id}
              onClick={() => gridStore.setLayout(id)}
              className={`rounded border px-2 py-0.5 text-xs transition-colors ${
                layout === id
                  ? "border-primary text-ink"
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
          <Slot
            key={slotId}
            slotId={slotId}
            active={activeSlot === slotId}
            archivedStatus={archived.status}
            resolutionsBySymbol={resolutionsBySymbol}
            picker={{
              symbols,
              status: archived.status,
              error: archived.error,
              onRetry: archived.reload,
            }}
          />
        ))}
      </div>
    </div>
  );
}

/** What is drawn on a slot's instrument, by symbol rather than by slot, so two slots on one instrument show the
 *  same objects. The store, not a hook-local fetch: the agent re-reads every loaded symbol after a turn. */
function useSlotDrawings(symbol: string | null): ChartDrawings | null {
  // This symbol's entry, not the whole snapshot: the agent re-reads every loaded symbol after a turn, and a
  // slot watching all of them re-rendered its chart for an instrument it is not showing.
  const entry = useSyncExternalStore(drawingsStore.subscribe, () =>
    symbol === null ? undefined : drawingsStore.getSnapshot()[symbol],
  );
  useEffect(() => {
    if (symbol !== null) drawingsStore.ensureLoaded(symbol);
  }, [symbol]);
  if (symbol === null) return null;
  return {
    items: entry?.drawings ?? [],
    status: entry?.status ?? "loading",
    error: entry?.error ?? null,
    remove: (id) => drawingsStore.remove(id),
    patch: (id, patch) => drawingsStore.patch(id, patch),
  };
}

/** What every picker in the grid draws from — one read of `/pairs`, shared. */
interface PickerSource {
  symbols: string[];
  status: ReturnType<typeof useTrackedPairs>["status"];
  error: string | null;
  onRetry(): void;
}

function Slot({
  slotId,
  active,
  archivedStatus,
  resolutionsBySymbol,
  picker,
}: {
  slotId: SlotId;
  active: boolean;
  archivedStatus: ReturnType<typeof useTrackedPairs>["status"];
  resolutionsBySymbol: Map<string, Resolution[]>;
  picker: PickerSource;
}) {
  // This slot's own configuration. `updateSlot` replaces the slot it touches and leaves
  // the others as they were, so a change to another slot does not wake this one.
  const slot = useSyncExternalStore(
    gridStore.subscribe,
    () => gridStore.getSnapshot().slots[slotId],
  );
  const allowedResolutions = slot.symbol ? resolutionsBySymbol.get(slot.symbol) : undefined;
  // A separate subscription from the config above: setting a focus request must not re-render every slot
  // watching the persisted layout, only the one it is for (`gridStore`).
  const focusRequest = useSyncExternalStore(gridStore.subscribeFocusRequest, () =>
    gridStore.getFocusRequest(slotId),
  );
  const drawings = useSlotDrawings(slot.symbol);

  // Only a definite "no" — a fetch that finished without this pair — counts as stale; `unreachable` must never
  // read as "no longer archived". The resolution counts as much as the symbol, or slot and selector disagree.
  const answered = slot.symbol !== null && archivedStatus === "ready";
  const staleSymbol = answered && allowedResolutions === undefined;
  const staleResolution =
    answered && allowedResolutions !== undefined && !allowedResolutions.includes(slot.resolution);
  const stale = staleSymbol || staleResolution;

  return (
  // Marking the slot the moment focus lands anywhere inside it, not just on a click, so keyboard users get
  // the same "actions land here" signal (terminal-grid spec, "Który slot jest aktywny").
    <div
      onMouseDown={() => gridStore.setActiveSlot(slotId)}
      onFocusCapture={() => gridStore.setActiveSlot(slotId)}
      data-testid={`slot-${slotId}`}
      data-active={active}
      className="relative min-h-0 min-w-0"
    >
      {slot.symbol === null ? (
        <EmptySlot slotId={slotId} picker={picker} />
      ) : stale ? (
        <StaleSlot
          slotId={slotId}
          symbol={slot.symbol}
          resolution={staleResolution ? slot.resolution : null}
          stillArchivedAt={staleResolution ? (allowedResolutions ?? []) : []}
          picker={picker}
        />
      ) : (
        <Chart
          source={marketData}
          indicatorSource={indicators}
          symbol={slot.symbol}
          resolution={slot.resolution}
          resolutions={allowedResolutions}
          onResolutionChange={(resolution) => gridStore.setSlotResolution(slotId, resolution)}
          initialIndicatorSelections={slot.indicators}
          onIndicatorSelectionsChange={(next) => gridStore.setSlotIndicators(slotId, next)}
          focusRequest={focusRequest}
          onFocusRequestSettled={() => gridStore.clearFocusRequest(slotId)}
          onVisibleRangeChange={(range) => gridStore.setVisibleRange(slotId, range)}
          drawings={drawings ?? undefined}
          headerLeft={
            <SymbolField
              label={`Symbol for slot ${slotId}`}
              value={slot.symbol}
              symbols={picker.symbols}
              status={picker.status}
              error={picker.error}
              onRetry={picker.onRetry}
              onChange={(symbol) => {
                if (symbol) gridStore.setSlotSymbol(slotId, symbol);
                else gridStore.clearSlotSymbol(slotId);
              }}
            />
          }
        />
      )}

      {/* An overlay rather than an `outline` on the slot: an outline paints with the box's
          own background, so the chart's opaque `<section>` covered it and only an empty
          slot ever showed the mark. Last child and `z-10` puts it over the chart and its
          loading veil, still under the indicator popover at `z-20`. */}
      {active && (
        <span
          aria-hidden
          // `active-mark-`, not `slot-`: the layout tests count slots with
          // getAllByTestId(/^slot-/), which a second id per slot would inflate.
          data-testid={`active-mark-${slotId}`}
          className="pointer-events-none absolute inset-0 z-10 border-2 border-primary"
        />
      )}
    </div>
  );
}

function EmptySlot({ slotId, picker }: { slotId: SlotId; picker: PickerSource }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 bg-panel">
      <p className="text-sm text-ink-muted">Pick an instrument for this slot.</p>
      <SlotPicker slotId={slotId} picker={picker} />
    </div>
  );
}

/** The picker as every place but the chart header uses it: nothing selected
 *  yet, and choosing sets the slot. */
function SlotPicker({ slotId, picker }: { slotId: SlotId; picker: PickerSource }) {
  return (
    <SymbolField
      label={`Symbol for slot ${slotId}`}
      value={null}
      symbols={picker.symbols}
      status={picker.status}
      error={picker.error}
      onRetry={picker.onRetry}
      onChange={(symbol) => {
        if (symbol) gridStore.setSlotSymbol(slotId, symbol);
      }}
    />
  );
}

/** A slot whose remembered pair stopped being archived between sessions, recognized rather than left looping on a
 *  subscription the archive keeps refusing. `stillArchivedAt` carries what is left, so switching is one click. */
function StaleSlot({
  slotId,
  symbol,
  resolution,
  stillArchivedAt,
  picker,
}: {
  slotId: SlotId;
  symbol: string;
  resolution: Resolution | null;
  stillArchivedAt: readonly Resolution[];
  picker: PickerSource;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 bg-panel px-4 text-center">
      <p className="text-sm text-ink-muted">
        <span className="font-semibold text-ink">{symbol}</span>
        {resolution === null ? (
          <> is no longer archived.</>
        ) : (
          <>
            {" "}
            is no longer archived at{" "}
            <span className="font-semibold text-ink">{RESOLUTION_LABEL[resolution]}</span>.
          </>
        )}
      </p>

      {stillArchivedAt.length > 0 ? (
        <>
          <p className="text-xs text-ink-muted">Still collected at:</p>
          <div className="flex flex-wrap justify-center gap-1">
            {stillArchivedAt.map((r) => (
              <Button
                size="xs"
                key={r}
                onClick={() => gridStore.setSlotResolution(slotId, r)}
              >
                {RESOLUTION_LABEL[r]}
              </Button>
            ))}
          </div>
        </>
      ) : (
        <p className="text-xs text-ink-muted">
          Add it again in the{" "}
          <Link to="/instruments" className="text-ink underline">
            Instruments
          </Link>{" "}
          tab, or pick a different instrument below.
        </p>
      )}

      <SlotPicker slotId={slotId} picker={picker} />
    </div>
  );
}
