/**
 * REST candles carry an ISO string, the WebSocket epoch seconds; everything downstream deals in seconds.
 * `Date.parse` is safe here because capital-gateway appends `Z` whenever the provider's UTC field is present.
 */
export function parseIsoToEpochSeconds(iso: string): number {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) {
    throw new RangeError(`not a parseable timestamp: ${JSON.stringify(iso)}`);
  }
  return Math.floor(ms / 1000);
}
