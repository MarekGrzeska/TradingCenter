/**
 * Page arithmetic for the cost tables, kept out of the component so the awkward part —
 * what happens to the page you are on when the rows underneath change — is something a
 * test can state rather than something a render has to survive.
 *
 * The page is derived, never stored clamped: a range change can shrink a table from forty
 * rows to two while state still says "page 4", and correcting that with an effect means
 * one render showing an empty table first.
 */

export interface Page<T> {
  rows: T[];
  /** Zero-based, already clamped into range — use this to render, not the raw state. */
  index: number;
  count: number;
  /** One-based and inclusive, for "showing 11–20 of 57". Both 0 when there are no rows. */
  firstRow: number;
  lastRow: number;
  total: number;
}

export function pageOf<T>(rows: readonly T[], requested: number, size: number): Page<T> {
  const total = rows.length;
  const count = Math.max(1, Math.ceil(total / size));
  const index = Math.min(Math.max(requested, 0), count - 1);
  const start = index * size;
  const page = rows.slice(start, start + size);
  return {
    rows: page,
    index,
    count,
    firstRow: total === 0 ? 0 : start + 1,
    lastRow: start + page.length,
    total,
  };
}
