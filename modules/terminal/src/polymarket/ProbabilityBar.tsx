import { bandFor, formatProbability } from "./probability";

/**
 * A probability, drawn as well as written.
 *
 * The job of this number is **magnitude against a known maximum** — a probability lives on
 * 0..1 and nothing else — so the mark is a bar anchored at zero on a track the width of the
 * whole scale. That is what makes two outcomes comparable at a glance without reading two
 * numbers, which is the thing a column of percentages does not give.
 *
 * **The hue follows the value, not the outcome.** It is the same variable the length
 * encodes, said twice on purpose: a column of bars is scanned rather than read, and a colour
 * says which end of the scale a row sits at before anything has been measured. What it must
 * never be is a colour per outcome — that would be a rainbow nobody can rank, with hue doing
 * a job the label beside it already does.
 *
 * The five bands were stepped by the dataviz skill's validator rather than by eye; the
 * reasoning and the numbers are on `BANDS` in `probability.ts`, next to the values.
 *
 * **No price draws no bar.** A zero-length fill is a bar that says "zero", and zero is a
 * claim about the market where the truth is that nothing has been collected — the same
 * distinction the windows make, one layer down.
 */
export function ProbabilityBar({
  price,
  stale = false,
  at,
}: {
  price: number | null;
  /** Older than twice the sampling tick. Dimmed rather than hidden: it is still the last
   *  thing known, and the age beside it says so in words. */
  stale?: boolean;
  at?: Date | null;
}) {
  if (price === null) {
    return (
      <span className="inline-block h-1.5 w-24 rounded-full bg-raised/40" aria-hidden />
    );
  }

  const percent = Math.max(0, Math.min(1, price)) * 100;
  const label = formatProbability(price) ?? "";
  const band = bandFor(price)!;

  return (
    <span
      role="meter"
      aria-valuenow={price}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuetext={`${label} · ${band.reading}`}
      title={`${label} · ${band.reading}${at ? ` — read ${at.toISOString()}` : ""}`}
      className="inline-block h-1.5 w-24 overflow-hidden rounded-full bg-raised"
    >
      {/* Anchored at zero and rounded on the value end, so length is the only thing that
          reads as quantity. */}
      <span
        className="block h-full rounded-r-full"
        style={{
          width: `${percent}%`,
          background: band.fill,
          // Dimmed rather than recoloured: a stale reading is still that band's value, and
          // moving it to another hue would say the market had moved.
          opacity: stale ? 0.45 : 1,
        }}
      />
    </span>
  );
}
