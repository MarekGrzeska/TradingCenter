import type { StepResult } from "./stepResult";

/** A step's decision and summary first, the whole JSON result underneath. */
export function StepOutput({ result }: { result: StepResult }) {
  return (
    <div className="flex flex-col gap-1" data-testid="step-output">
      <div className="text-sm text-ink">
        <span className="mr-2 rounded border border-border px-1 text-xs uppercase">{result.decision}</span>
        {result.summary}
      </div>
      <pre className="max-h-64 overflow-auto rounded border border-border bg-panel-strong p-2 font-mono text-xs text-ink-muted">
        {result.full}
      </pre>
    </div>
  );
}
