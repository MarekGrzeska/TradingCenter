import { formatProbability } from "./probability";

/**
 * A probability, drawn as well as written.
 *
 * The job of this number is **magnitude against a known maximum** — a probability lives on
 * 0..1 and nothing else — so the mark is a bar anchored at zero on a track the width of the
 * whole scale. That is what makes two outcomes comparable at a glance without reading two
 * numbers, which is the thing a column of percentages does not give.
 *
 * **One hue for every bar, not a colour per outcome.** The bar encodes magnitude; identity
 * is carried by the name beside it. A palette here would be colour doing a job the label
 * already does, and would make a market of eight outcomes a rainbow nobody can rank.
 *
 * The fill is the terminal's own accent on its recessive surface, and the check that applies
 * to a single magnitude fill — contrast against the surface — passes at ≥3:1 (dataviz
 * skill's validator, dark mode, surface `--color-panel`). The lightness-band check that file
 * also runs is scoped to categorical palettes and has nothing to say about one hue.
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

  return (
    <span
      role="meter"
      aria-valuenow={price}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuetext={label}
      title={at ? `${label} — read ${at.toISOString()}` : label}
      className="inline-block h-1.5 w-24 overflow-hidden rounded-full bg-raised"
    >
      {/* Anchored at zero and rounded on the value end, so length is the only thing that
          reads as quantity. */}
      <span
        className={`block h-full rounded-r-full ${stale ? "bg-primary-dim" : "bg-primary"}`}
        style={{ width: `${percent}%` }}
      />
    </span>
  );
}
