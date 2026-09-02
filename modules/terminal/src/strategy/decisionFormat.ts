import type { ReasonKind } from "./strategyApi";

/**
 * What the row, the dialog and the reports table say the same way. The kind of refusal is a badge because the three
 * have three answers: fetch history, read the strategy, change the limit.
 */

export const KIND_LABEL: Record<ReasonKind, string> = {
  strategy: "strategia",
  coverage: "brak danych",
  limit: "limit",
};

/** `coverage` is the one that wants attention: it is answered by doing something to the
 *  archive. The other two are the system deciding, which is not a warning. */
export const KIND_TONE: Record<ReasonKind, string> = {
  strategy: "kind-ordinary",
  coverage: "kind-missing",
  limit: "kind-limit",
};

export function formatBar(at: Date): string {
  return at.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Two decimal places and a sign, so a level lines up with the one above it. */
export function formatLevel(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}
