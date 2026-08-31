/** Where the archive answers. A relative path needs no expansion — `fetch("/polymarket-api/events")`
 *  already resolves against the page origin — so this only trims the trailing slash callers join onto. */
export function archiveBase(
  raw: string | undefined = import.meta.env.VITE_POLYMARKET_HTTP as string | undefined,
): string {
  return (raw?.trim() || "/polymarket-api").replace(/\/+$/, "");
}
