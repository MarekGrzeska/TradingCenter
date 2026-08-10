import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { archive, instruments } from "../data/marketData";
import { Autocomplete } from "../ui/Autocomplete";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { assetClassSource, instrumentInClassSource } from "../ui/autocompleteSources";
import { RESOLUTIONS } from "../data/types";
import type {
  AssetClass,
  Instrument,
  JobEstimate,
  PairEstimate,
  PairRequest,
  Resolution,
  TrackedPair,
  TrackPairsResult,
} from "../data/types";
import { formatBytes, formatInstant } from "./format";
import { RESOLUTION_ABBR } from "./resolutionAbbr";

/**
 * Adding instruments as a decision made once, not one blind click per pair
 * (proposal.md, "Dodawanie instrumentów przestaje być formularzem"). The wizard only
 * collects what to collect and starts nothing itself: committing opens the acceptance
 * dialog, the only thing that calls `trackPairs`.
 *
 * A date earlier than the provider's history is not validated here — it means
 * "everything available" and is clipped server-side, not a client-side error.
 */

function asDateInput(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function todayDateInput(): string {
  return asDateInput(new Date());
}

/** The start of the current year — year to date.
 *
 *  Deliberately not "everything available": at `MINUTE` a decade is around a hundred
 *  chunks per pair, so every operator who never touched this field would commit hundreds
 *  of gateway requests without deciding to. Deep history stays one edit away.
 *
 *  A round boundary rather than a rolling window, so the same instrument added twice in
 *  a month asks for the same range both times. It is shallow in January, which is the
 *  safe direction for a default that costs provider requests. */
function defaultCollectFromInput(): string {
  return `${new Date().getUTCFullYear()}-01-01`;
}

function dateInputToEpochSeconds(value: string): number {
  return Math.floor(new Date(`${value}T00:00:00Z`).getTime() / 1000);
}

/** Identifies one prospective job — everything the acceptance dialog prices. */
function requestKey(pairs: PairRequest[], collectFromInput: string): string {
  return `${collectFromInput}|${pairs.map((p) => `${p.symbol}:${p.resolution}`).join(",")}`;
}

export function AddInstrumentWizard({
  existingPairs,
  onCollected,
}: {
  existingPairs: TrackedPair[];
  onCollected(): void;
}) {
  const [assetClass, setAssetClass] = useState<AssetClass | null>(null);
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const [resolutions, setResolutions] = useState<ReadonlySet<Resolution>>(new Set());
  // Lazy: computed once at mount, not on every render.
  const [collectFromInput, setCollectFromInput] = useState(defaultCollectFromInput);
  const [pending, setPending] = useState<PairRequest[] | null>(null);

  // Disabled rather than omitted while no class is chosen — the instrument
  // step only makes sense after the first one, so it stays visible and says
  // so instead of appearing once a class is picked.
  const instrumentSource = useMemo(
    () => (assetClass ? instrumentInClassSource(instruments, assetClass) : async () => ({ options: [] })),
    [assetClass],
  );

  function changeAssetClass(next: AssetClass | null) {
    setAssetClass(next);
    // Any change to the class — not just clearing it — invalidates whatever
    // instrument was chosen under the old one (terminal-data-manager spec,
    // "Zmiana klasy po wybraniu instrumentu").
    setInstrument(null);
  }

  function toggleResolution(resolution: Resolution) {
    setResolutions((current) => {
      const next = new Set(current);
      if (next.has(resolution)) next.delete(resolution);
      else next.add(resolution);
      return next;
    });
  }

  const missing =
    instrument === null
      ? "Choose an instrument to continue."
      : resolutions.size === 0
        ? "Choose at least one resolution to continue."
        : null;

  function review() {
    if (!instrument || resolutions.size === 0) return;
    const pairs: PairRequest[] = RESOLUTIONS.filter((r) => resolutions.has(r)).map((resolution) => ({
      symbol: instrument.symbol,
      resolution,
    }));
    setPending(pairs);
  }

  function afterAccepted() {
    setPending(null);
    setAssetClass(null);
    setInstrument(null);
    setResolutions(new Set());
    setCollectFromInput(defaultCollectFromInput());
    onCollected();
  }

  return (
    <div className="shrink-0 border-b border-border px-4 py-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Asset class" className="w-48">
          <Autocomplete<AssetClass>
            value={assetClass}
            onChange={changeAssetClass}
            source={assetClassSource(instruments)}
            getOptionId={(c) => c}
            getOptionLabel={(c) => c}
            ariaLabel="Asset class"
            placeholder="Asset class…"
          />
        </Field>

        <Field label="Instrument" className="w-64">
          <Autocomplete<Instrument>
            value={instrument}
            onChange={setInstrument}
            source={instrumentSource}
            getOptionId={(i) => i.symbol}
            getOptionLabel={(i) => i.symbol}
            renderOption={(i) => <InstrumentOption instrument={i} />}
            ariaLabel="Instrument"
            placeholder={assetClass ? "Instrument…" : "Choose an asset class first"}
            disabled={assetClass === null}
            countLabel={(n) => `${n} instrument${n === 1 ? "" : "s"} in ${assetClass}`}
          />
        </Field>

        <Field label="Resolutions">
          <div className="flex flex-wrap gap-1">
            {RESOLUTIONS.map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={resolutions.has(r)}
                onClick={() => toggleResolution(r)}
                className={`rounded border px-2 py-1 text-xs ${
                  resolutions.has(r)
                    ? "border-accent bg-panel-strong text-ink"
                    : "border-border text-ink-muted hover:text-ink"
                }`}
              >
                {RESOLUTION_ABBR[r]}
              </button>
            ))}
          </div>
        </Field>

        <Field label="History from">
          <input
            type="date"
            aria-label="History from"
            value={collectFromInput}
            max={todayDateInput()}
            onChange={(e) => setCollectFromInput(e.target.value)}
            className="rounded border border-border bg-panel-strong px-2 py-1 text-xs text-ink"
          />
        </Field>

        <button
          type="button"
          disabled={missing !== null}
          onClick={review}
          className="rounded border border-border px-3 py-1.5 text-xs text-ink hover:bg-panel-strong disabled:opacity-40"
        >
          Review and add
        </button>
      </div>

      {missing && <p className="mt-2 text-xs text-ink-muted">{missing}</p>}

      {pending && (
        // Keyed on the request, so a different one is structurally a different
        // dialog: the price is fetched once per mount, and a dialog that
        // re-rendered with new pairs would otherwise show the old estimate
        // above a button that accepts the new ones.
        <AcceptanceDialog
          key={requestKey(pending, collectFromInput)}
          pairs={pending}
          collectFrom={dateInputToEpochSeconds(collectFromInput)}
          existingPairs={existingPairs}
          onClose={() => setPending(null)}
          onAccepted={afterAccepted}
        />
      )}
    </div>
  );
}

/** One suggested instrument, with everything the operator judges it on:
 *  symbol, name, class, whether it can be traded, and the current spread where
 *  the gateway reports one (terminal-instruments spec, "Instrumenty wyszukuje
 *  się po frazie"). Not tradeable is worth saying and is not disqualifying —
 *  the archive collects it and the chart draws it either way. */
function InstrumentOption({ instrument }: { instrument: Instrument }) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="font-semibold text-ink">{instrument.symbol}</span>
      <span className="text-ink-secondary">{instrument.name}</span>
      <span className="text-ink-muted">{instrument.assetClass}</span>
      {instrument.bid !== null && instrument.ask !== null && (
        <span className="text-ink-muted">
          {instrument.bid} / {instrument.ask}
        </span>
      )}
      {!instrument.tradeable && (
        <span className="text-warning" title="Not tradeable; it can still be collected and charted.">
          not tradeable
        </span>
      )}
    </span>
  );
}

function Field({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`flex flex-col gap-1 text-xs text-ink-muted ${className}`}>
      <span>{label}</span>
      {children}
    </div>
  );
}

// --- acceptance dialog ---

function isAlreadyCollected(existing: TrackedPair[], symbol: string, resolution: Resolution): boolean {
  return existing.some((pair) => pair.symbol === symbol && pair.resolution === resolution);
}

function AcceptanceDialog({
  pairs,
  collectFrom,
  existingPairs,
  onClose,
  onAccepted,
}: {
  pairs: PairRequest[];
  collectFrom: number;
  existingPairs: TrackedPair[];
  onClose(): void;
  onAccepted(): void;
}) {
  const [estimate, setEstimate] = useState<JobEstimate | null>(null);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [result, setResult] = useState<TrackPairsResult | null>(null);

  // One mount per request — the caller keys this component on it — so the
  // request is fixed for this dialog's whole lifetime. Held in a ref only
  // because `pairs` is a fresh array every render: listing it as a dependency
  // would re-price on every render rather than once.
  const requestRef = useRef({ pairs, collectFrom });
  requestRef.current = { pairs, collectFrom };

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setEstimate(null);
    setEstimateError(null);

    archive
      .estimateJob(requestRef.current.pairs, requestRef.current.collectFrom, controller.signal)
      .then((priced) => {
        if (!cancelled) setEstimate(priced);
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setEstimateError(cause instanceof Error ? cause.message : "could not price this job");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const accept = useCallback(async () => {
    const outcome = await archive.trackPairs(
      requestRef.current.pairs,
      requestRef.current.collectFrom,
      new AbortController().signal,
    );
    setResult(outcome);
  }, []);

  // Accepting does not close this: what came back is the answer to the question,
  // and refusals in particular have to be read where the decision was made. So
  // the same dialog stays, with a result inside it and nothing left to cancel.
  if (result) {
    const accepted = result.results.filter((r) => r.refused === null);
    return (
      <ConfirmDialog
        title={accepted.length > 0 ? "Collecting started" : "Nothing was added"}
        confirmLabel="Done"
        busyLabel="Done"
        cancelLabel={null}
        onConfirm={() => {}}
        onClose={onAccepted}
      >
        <ResultSummary result={result} />
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Confirm collection"
      confirmLabel="Start collecting"
      busyLabel="Starting…"
      confirmDisabled={!estimate || estimateError !== null}
      fallbackError="could not start collecting"
      // What comes back is not just "it worked": the archive may have refused
      // some of the pairs, and that has to be read where the decision was made
      // rather than vanish with the dialog.
      closeOnSuccess={false}
      onConfirm={accept}
      onClose={onClose}
    >
      {estimateError && (
        <p className="mt-3 text-critical">
          Could not price this job: {estimateError}. Nothing has been added.
        </p>
      )}
      {!estimateError && !estimate && <p className="mt-3 text-ink-muted">Pricing…</p>}
      {estimate && <EstimateTable estimate={estimate} existingPairs={existingPairs} />}
    </ConfirmDialog>
  );
}

function EstimateTable({
  estimate,
  existingPairs,
}: {
  estimate: JobEstimate;
  existingPairs: TrackedPair[];
}) {
  return (
    <>
      <table className="mt-3 w-full text-xs">
        <thead className="text-left text-ink-muted">
          <tr>
            <th className="px-2 py-1 font-normal">Symbol</th>
            <th className="px-2 py-1 font-normal">Resolution</th>
            <th className="px-2 py-1 font-normal">Range</th>
            <th className="px-2 py-1 text-right font-normal">Candles</th>
            <th className="px-2 py-1 text-right font-normal">Size</th>
          </tr>
        </thead>
        <tbody>
          {estimate.pairs.map((pair) => (
            <EstimateRow
              key={`${pair.symbol}|${pair.resolution}`}
              pair={pair}
              alreadyCollected={isAlreadyCollected(existingPairs, pair.symbol, pair.resolution)}
            />
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-right text-xs text-ink-secondary">
        Total: {estimate.totalEstimatedCandles.toLocaleString()} candles,{" "}
        {formatBytes(estimate.totalEstimatedBytes)}
      </p>
      {/* Said plainly, because the operator is deciding on cost from it: these are
          calendar periods, so any market shut for part of the range yields fewer
          candles than this. High rather than low is the safe direction to be wrong in
          (design.md, "Wycena liczy kawałki, a nie osobną formułę"). */}
      <p className="mt-1 text-xs text-ink-muted">
        These are estimates. Candles are counted as calendar periods, so a market closed
        for part of the range — weekends, holidays — will collect fewer than shown.
      </p>
    </>
  );
}

function EstimateRow({ pair, alreadyCollected }: { pair: PairEstimate; alreadyCollected: boolean }) {
  if (pair.unknown) {
    return (
      <tr className="border-t border-border">
        <td className="px-2 py-1.5 font-semibold text-ink">{pair.symbol}</td>
        <td className="px-2 py-1.5 text-ink-secondary">{pair.resolution}</td>
        <td colSpan={3} className="px-2 py-1.5 text-critical">
          not offered by the gateway
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-t border-border">
      <td className="px-2 py-1.5 font-semibold text-ink">
        {pair.symbol}
        {alreadyCollected && (
          <span className="ml-2 rounded border border-border px-1 text-[10px] font-normal text-ink-muted">
            already collecting
          </span>
        )}
      </td>
      <td className="px-2 py-1.5 text-ink-secondary">{pair.resolution}</td>
      <td className="px-2 py-1.5 text-ink-secondary">
        {pair.effectiveFrom === null ? "—" : formatInstant(pair.effectiveFrom)} → now
        {pair.clipped && <span className="ml-1 text-warning">(clipped)</span>}
      </td>
      <td className="px-2 py-1.5 text-right text-ink-secondary">
        {pair.estimatedCandles.toLocaleString()}
      </td>
      <td className="px-2 py-1.5 text-right text-ink-secondary">{formatBytes(pair.estimatedBytes)}</td>
    </tr>
  );
}

function ResultSummary({ result }: { result: TrackPairsResult }) {
  const accepted = result.results.filter((r) => r.refused === null);
  const refused = result.results.filter((r) => r.refused !== null);

  return (
    <div>
      {accepted.length > 0 && (
        <div className="mt-3">
          <p className="text-ink">Now archiving:</p>
          <ul className="mt-1 list-disc pl-5 text-ink-secondary">
            {accepted.map((r) => (
              <li key={`${r.symbol}|${r.resolution}`}>
                {r.symbol} {r.resolution}
              </li>
            ))}
          </ul>
          {result.jobId !== null && (
            <p className="mt-2 text-ink-secondary">
              Track its progress in the{" "}
              <Link to="/data-history" className="text-ink underline">
                Data History
              </Link>{" "}
              tab.
            </p>
          )}
        </div>
      )}

      {refused.length > 0 && (
        <div className="mt-3">
          <p className="text-critical">Refused:</p>
          <ul className="mt-1 list-disc pl-5 text-critical">
            {refused.map((r) => (
              <li key={`${r.symbol}|${r.resolution}`}>
                {r.symbol} {r.resolution}: {r.refused}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
