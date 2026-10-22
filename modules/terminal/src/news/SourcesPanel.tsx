import { formatInstant } from "../ui/formatTime";
import { formatDuration, STATUS_TEXT } from "./delay";
import type { NewsSource } from "./newsApi";

/** Which feed to trust in a race: its status, and the median and 90th percentile of both bounds over the day. */

const STATUS_CLASS = {
  ok: "text-ink-muted",
  pending: "text-ink-faint",
  failing: "text-warning",
  stale: "text-critical",
} as const;

function figures(f: { medianSeconds: number | null; p90Seconds: number | null }): string {
  return f.medianSeconds === null
    ? "—"
    : `${formatDuration(f.medianSeconds)} / ${formatDuration(f.p90Seconds)}`;
}

export function SourcesPanel({ sources }: { sources: NewsSource[] }) {
  return (
    <div className="overflow-x-auto rounded border border-border bg-panel">
      <table className="w-full text-left text-xs">
        <caption className="px-3 py-2 text-left text-ink-faint">
          Źródła: ostatnia doba, mediana / 90. percentyl
        </caption>
        <thead className="text-ink-faint">
          <tr>
            <th className="px-3 py-1 font-normal">źródło</th>
            <th className="px-3 py-1 font-normal">stan</th>
            <th className="px-3 py-1 font-normal">ostatnie pobranie</th>
            <th className="px-3 py-1 text-right font-normal">newsów</th>
            <th className="px-3 py-1 font-normal" title="ile spóźnił się sam feed">
              spóźnienie feedu
            </th>
            <th className="px-3 py-1 font-normal" title="od publikacji do zobaczenia u nas">
              czekaliśmy
            </th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.source} className="border-t border-border">
              <td className="px-3 py-1 text-ink">
                {source.publisher} <span className="text-ink-faint">{source.source}</span>
              </td>
              <td className={`px-3 py-1 ${STATUS_CLASS[source.status]}`}>
                {STATUS_TEXT[source.status]}
                {source.lastFailure !== null && source.status !== "ok" && (
                  <span className="block text-ink-faint">{source.lastFailure}</span>
                )}
              </td>
              <td className="px-3 py-1 tabular-nums text-ink-muted">
                {source.lastSuccessAt === null
                  ? "nigdy"
                  : formatInstant(Math.floor(source.lastSuccessAt.getTime() / 1000))}
              </td>
              <td className="px-3 py-1 text-right tabular-nums text-ink-muted">
                {source.items24h}
                {source.unmeasured24h > 0 && (
                  <span className="text-ink-faint" title="bez pomiaru opóźnienia">
                    {" "}
                    ({source.unmeasured24h})
                  </span>
                )}
              </td>
              <td className="px-3 py-1 tabular-nums text-ink-muted">{figures(source.feed)}</td>
              <td className="px-3 py-1 tabular-nums text-ink-muted">{figures(source.waited)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
