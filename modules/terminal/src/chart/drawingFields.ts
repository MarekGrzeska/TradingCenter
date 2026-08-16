import type { AgentChartDrawing } from "../agent/agentApi";

/** The prices a shape has, by the role each plays — the same roles `PatchDrawingIn`
 *  accepts, so an edited field maps to its patch without a second table anywhere. */
export type PriceRole = "price" | "top" | "bottom" | "aPrice" | "bPrice";

export interface PriceField {
  role: PriceRole;
  label: string;
  value: number;
}

export function priceFields(drawing: AgentChartDrawing): PriceField[] {
  const geometry = drawing.geometry;
  if (geometry.kind === "level") return [{ role: "price", label: "Price", value: geometry.price }];
  if (geometry.kind === "zone") {
    return [
      { role: "top", label: "Top", value: geometry.top },
      { role: "bottom", label: "Bottom", value: geometry.bottom },
    ];
  }
  return [
    { role: "aPrice", label: "From", value: geometry.a.price },
    { role: "bPrice", label: "To", value: geometry.b.price },
  ];
}

export function shapeLabel(drawing: AgentChartDrawing): string {
  return drawing.geometry.kind === "trendline" ? "trend line" : drawing.geometry.kind;
}

/** The prices as one line, for a row's or a card's own summary — `priceFields` in
 *  reading order. */
export function priceSummary(drawing: AgentChartDrawing): string {
  return priceFields(drawing)
    .map((field) => field.value)
    .join(" – ");
}
