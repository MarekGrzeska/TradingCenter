/** A step's result is JSON, not prose: its decision and summary first, the whole of it underneath (`terminal-teams`,
 *  "Przebieg pokazuje stan i wynik kroku"). `null` for anything that is not a step's result — an agent's prose. */
export function readStepOutput(output: string | null): { decision: string; summary: string; full: string } | null {
  if (!output) return null;
  try {
    const data: unknown = JSON.parse(output);
    if (typeof data !== "object" || data === null || !("decision" in data)) return null;
    const record = data as Record<string, unknown>;
    return {
      decision: String(record.decision),
      summary: typeof record.summary === "string" ? record.summary : "",
      full: JSON.stringify(data, null, 2),
    };
  } catch {
    return null;
  }
}

export type StepResult = NonNullable<ReturnType<typeof readStepOutput>>;
