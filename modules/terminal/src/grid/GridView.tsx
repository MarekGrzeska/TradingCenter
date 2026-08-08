import { useMemo, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { Chart } from "../chart/Chart";
import { archive, marketData } from "../data/marketData";
import type { Resolution, TrackedPair } from "../data/types";
import { useTrackedPairs } from "../instruments/useTrackedPairs";
import { gridStore } from "./gridStore";
import { SymbolField } from "./SymbolField";
import { LAYOUTS, LAYOUT_IDS, visibleSlotIds, type SlotId } from "./model";

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
  const config = useSyncExternalStore(gridStore.subscribe, gridStore.getSnapshot);
  // Read once and shared by every slot, rather than one poll per slot — six
  // slots asking independently would be six requests for the same list.
  const archived = useTrackedPairs(archive);
  const resolutionsBySymbol = useMemo(
    () => groupResolutionsBySymbol(archived.pairs),
    [archived.pairs],
  );

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
          <Slot
            key={slotId}
            slotId={slotId}
            active={config.activeSlot === slotId}
            archivedStatus={archived.status}
            resolutionsBySymbol={resolutionsBySymbol}
          />
        ))}
      </div>
    </div>
  );
}

function Slot({
  slotId,
  active,
  archivedStatus,
  resolutionsBySymbol,
}: {
  slotId: SlotId;
  active: boolean;
  archivedStatus: ReturnType<typeof useTrackedPairs>["status"];
  resolutionsBySymbol: Map<string, Resolution[]>;
}) {
  const config = useSyncExternalStore(gridStore.subscribe, gridStore.getSnapshot);
  const slot = config.slots[slotId];
  const allowedResolutions = slot.symbol ? resolutionsBySymbol.get(slot.symbol) : undefined;

  // Only a definite "no" — a fetch that actually finished and came back
  // without this pair — counts as stale. `unreachable` must never read as
  // "no longer archived": the slot keeps showing what it already had
  // (terminal-grid spec, "Listy archiwizowanych nie da się odczytać").
  //
  // The resolution counts as much as the symbol. A slot remembering US100
  // `MINUTE_5` after only `HOUR_4` was left archived for US100 would otherwise
  // chart a pair nobody collects while its own selector — narrowed to the
  // archived ones — displayed a different resolution entirely, each
  // contradicting the other.
  const answered = slot.symbol !== null && archivedStatus === "ready";
  const staleSymbol = answered && allowedResolutions === undefined;
  const staleResolution =
    answered && allowedResolutions !== undefined && !allowedResolutions.includes(slot.resolution);
  const stale = staleSymbol || staleResolution;

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
      ) : stale ? (
        <StaleSlot
          slotId={slotId}
          symbol={slot.symbol}
          resolution={staleResolution ? slot.resolution : null}
          stillArchivedAt={staleResolution ? (allowedResolutions ?? []) : []}
        />
      ) : (
        <Chart
          source={marketData}
          symbol={slot.symbol}
          resolution={slot.resolution}
          resolutions={allowedResolutions}
          onResolutionChange={(resolution) => gridStore.setSlotResolution(slotId, resolution)}
          headerLeft={
            <SymbolField
              label={`Symbol for slot ${slotId}`}
              value={{ symbol: slot.symbol, resolutions: allowedResolutions ?? [] }}
              onChange={(instrument) => {
                if (instrument) gridStore.setSlotSymbol(slotId, instrument.symbol);
                else gridStore.clearSlotSymbol(slotId);
              }}
            />
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
        onChange={(instrument) => {
          if (instrument) gridStore.setSlotSymbol(slotId, instrument.symbol);
        }}
      />
    </div>
  );
}

/** A slot whose remembered pair stopped being archived between sessions —
 *  recognized rather than left to loop on a subscription the archive will
 *  keep refusing (terminal-grid spec, "Slot zapamiętany traci ważność, gdy
 *  instrument przestaje być archiwizowany").
 *
 *  `resolution` is set only when the symbol is still archived and it is this
 *  resolution that is gone; then `stillArchivedAt` carries the ones that are
 *  left, so switching is one click rather than a re-pick. */
function StaleSlot({
  slotId,
  symbol,
  resolution,
  stillArchivedAt,
}: {
  slotId: SlotId;
  symbol: string;
  resolution: Resolution | null;
  stillArchivedAt: readonly Resolution[];
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
            <span className="font-semibold text-ink">{resolution}</span>.
          </>
        )}
      </p>

      {stillArchivedAt.length > 0 ? (
        <>
          <p className="text-xs text-ink-muted">Still collected at:</p>
          <div className="flex flex-wrap justify-center gap-1">
            {stillArchivedAt.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => gridStore.setSlotResolution(slotId, r)}
                className="rounded border border-border px-2 py-0.5 text-xs text-ink hover:bg-panel-strong"
              >
                {r}
              </button>
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

      <SymbolField
        label={`Symbol for slot ${slotId}`}
        value={null}
        onChange={(instrument) => {
          if (instrument) gridStore.setSlotSymbol(slotId, instrument.symbol);
        }}
      />
    </div>
  );
}
