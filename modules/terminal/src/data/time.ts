/**
 * REST candles carry an ISO string, the WebSocket carries epoch seconds. Everything
 * downstream of a source deals in epoch seconds, so the conversion happens here, once.
 *
 * `Date.parse` is safe on the path that actually fires: capital-gateway appends `Z`
 * whenever the provider's UTC field is present, which it is on every request this
 * terminal makes. The fallback is provider-local time left unmarked on purpose, and its
 * ambiguity is inherited rather than guessed at.
 */
export function parseIsoToEpochSeconds(iso: string): number {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) {
    throw new RangeError(`not a parseable timestamp: ${JSON.stringify(iso)}`);
  }
  return Math.floor(ms / 1000);
}
