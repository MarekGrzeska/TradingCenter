/**
 * The one seam capital-gateway leaves deliberate: REST candles carry `ts` as an
 * ISO string, the WebSocket carries `time` as epoch seconds already. Everything
 * downstream of a source implementation deals only in epoch seconds — this is
 * where the ISO side gets converted, once.
 *
 * capital-gateway's mapper (`mapping.py::_candle_ts`) appends `Z` whenever the
 * provider's UTC field (`snapshotTimeUTC`) is present, which is the field it
 * reads on every request this terminal makes. The fallback — provider-local
 * `snapshotTime`, left unmarked on purpose so it isn't mistaken for UTC — only
 * fires when the provider omits the UTC field entirely; it has not been observed
 * in practice (task 2.5). `Date.parse` is timezone-safe on the `Z`-suffixed path
 * and merely inherits that fallback's ambiguity on the other, rather than
 * inventing a worse one by guessing.
 */
export function parseIsoToEpochSeconds(iso: string): number {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) {
    throw new RangeError(`not a parseable timestamp: ${JSON.stringify(iso)}`);
  }
  return Math.floor(ms / 1000);
}
