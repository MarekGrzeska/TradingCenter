/** What a phone shows first. One screen holds four or five rows, so the order is the whole of what the
 *  operator sees of an event that holds 128 markets. */

import type { Market, Outcome, TrackedEvent } from "./api";

/** The outcome a market is read by: the one the provider lists first, which for a binary market is
 *  "Yes" and for a candidate market is that candidate. Never the highest-priced one — the row would
 *  change identity as prices moved, and a list that reorders under the thumb cannot be scanned. */
export function leadingOutcome(market: Market): Outcome | undefined {
  return market.outcomes[0];
}

/** A market's own price for ordering, or `null` when nothing has been collected for it yet. */
export function leadingPrice(market: Market): number | null {
  return leadingOutcome(market)?.price ?? null;
}

/**
 * Open markets over resolved ones, then by the leading outcome's probability descending, then by id.
 * A market with no price sorts last inside its group rather than first: absence is not a zero, and a
 * row that says nothing does not belong at the top of a screen this small.
 */
export function marketsForDisplay(markets: Market[]): Market[] {
  return [...markets].sort((a, b) => {
    const resolved = Number(a.resolvedOutcome !== null) - Number(b.resolvedOutcome !== null);
    if (resolved !== 0) return resolved;

    const pa = leadingPrice(a);
    const pb = leadingPrice(b);
    if (pa !== null && pb !== null && pa !== pb) return pb - pa;
    if (pa !== null && pb === null) return -1;
    if (pa === null && pb !== null) return 1;

    return a.id - b.id;
  });
}

/** The one line a collapsed card carries: the event's leading market once the list is in display
 *  order, so the card and the list it opens agree about what comes first. */
export function headlineMarket(event: TrackedEvent): Market | undefined {
  return marketsForDisplay(event.markets)[0];
}
