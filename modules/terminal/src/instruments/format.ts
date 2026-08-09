/** UTC to the minute — the archive keys candles on an instant, and a local
 *  rendering of one invites comparing it against a period start that is not
 *  in the same zone. */
export function formatInstant(epochSeconds: number): string {
  return `${new Date(epochSeconds * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** An approximation, same as the number it describes (`market-data-jobs`
 *  spec, "Zlecenie da się wycenić przed jego uruchomieniem") — one decimal is
 *  enough precision for a number the operator is not meant to trust exactly. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
