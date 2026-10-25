/** The cost model as a form holds it — text the operator types — and as the package reads it. */

import type { Costs } from "./strategiesApi";

export interface CostFields {
  spread: string;
  slippage: string;
  overnightLong: string;
  overnightShort: string;
  rolloverHour: string;
}

export const EMPTY_COSTS: CostFields = { spread: "", slippage: "", overnightLong: "", overnightShort: "", rolloverHour: "22" };

export function fieldsOf(costs: Costs): CostFields {
  return {
    spread: Array.isArray(costs.spread) ? costs.spread.join(" ") : String(costs.spread),
    slippage: String(costs.slippage),
    overnightLong: String(costs.overnight_long),
    overnightShort: String(costs.overnight_short),
    rolloverHour: String(costs.rollover_hour),
  };
}

/** The fields as the package reads them: one spread, or 24 separated by spaces — one per UTC hour. */
export function costsOf(fields: CostFields): Costs {
  const spreads = fields.spread.trim().split(/[\s;]+/).filter(Boolean).map(Number);
  return {
    spread: spreads.length === 1 ? spreads[0] : spreads,
    slippage: Number(fields.slippage),
    overnight_long: Number(fields.overnightLong),
    overnight_short: Number(fields.overnightShort),
    rollover_hour: Number(fields.rolloverHour),
  };
}
