import { bandFor, formatProbability } from "./probability";

/**
 * Magnitude against a known maximum, so the mark is a bar on a track the width of the whole 0..1 scale. The hue
 * follows the value, never the outcome — a colour per outcome is a rainbow nobody can rank. No price, no bar.
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
