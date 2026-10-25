/**
 * What the editor offers as the operator types, built from `GET /language` and the document's own names — the terminal
 * carries no list of the language's functions (`terminal-strategies`). After `@` it offers the intervals, each with the
 * terminal's name beside the language's (`terminal-shell`), and the instruments the archive collects.
 */

import { RESOLUTION_LABEL } from "../ui/resolutionLabel";
import type { Resolution } from "../data/types";
import type { Language } from "./strategiesApi";

export interface Offer {
  label: string;
  detail: string;
  kind: "function" | "variable" | "constant" | "keyword" | "type";
}

export function offersAfterAt(language: Language, symbols: readonly string[]): Offer[] {
  return [
    ...language.resolutions.map((r) => ({
      label: r,
      detail: RESOLUTION_LABEL[r as Resolution] ?? r,
      kind: "type" as const,
    })),
    ...symbols.map((s) => ({ label: s, detail: "instrument", kind: "constant" as const })),
  ];
}

export function offersInFormula(language: Language, document: unknown): Offer[] {
  const offers: Offer[] = [
    ...language.functions.map((f) => ({ label: f.name, detail: f.signature, kind: "function" as const })),
    ...(language.indicators ?? []).map((i) => ({ label: i.id, detail: i.signature, kind: "function" as const })),
    ...Object.entries({ ...language.series, ...language.time, ...language.position, ...language.history }).map(
      ([name, description]) => ({ label: name, detail: description, kind: "variable" as const }),
    ),
    ...Object.keys(language.constants).map((name) => ({ label: name, detail: "constant", kind: "constant" as const })),
    ...Object.entries(language.sessions).map(([name, hours]) => ({ label: name, detail: hours, kind: "constant" as const })),
  ];
  const doc = (document ?? {}) as { let?: Record<string, unknown>; params?: Record<string, unknown> };
  for (const name of Object.keys(doc.let ?? {})) offers.push({ label: name, detail: "let", kind: "variable" });
  for (const name of Object.keys(doc.params ?? {})) offers.push({ label: `p.${name}`, detail: "parameter", kind: "variable" });
  return offers;
}

export function offersForKeys(language: Language): Offer[] {
  return language.sections.map((s) => ({ label: s, detail: "section", kind: "keyword" as const }));
}
