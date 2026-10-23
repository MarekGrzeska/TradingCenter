import { useState } from "react";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { useRead } from "../data/query";
import { runOutcomeLabel, runSummary } from "./present";
import type { Topic, TopicRun, YoutubeApi } from "./youtubeApi";

/**
 * How the topics' searches went, newest first. A search that found nothing and one that never happened are the same empty list
 * on the candidates' side; here each is a row, and one that failed says why.
 */

const POLL_MS = 60_000;
const NO_RUNS: { runs: TopicRun[]; retentionDays: number } = { runs: [], retentionDays: 0 };
const NO_TOPICS: { topics: Topic[]; ceiling: number } = { topics: [], ceiling: 0 };

const TONE: Record<TopicRun["outcome"], string> = {
  found: "bg-raised text-ink",
  nothing_new: "bg-raised text-ink-muted",
  failed: "bg-critical-soft text-critical",
  skipped: "bg-warning-soft text-warning",
};

export function RunsPanel({ client }: { client: YoutubeApi }) {
  const [topicId, setTopicId] = useState<number | undefined>(undefined);
  const topics = useRead({
    key: ["youtube", "topics"],
    read: (signal) => client.topics(signal),
    initial: NO_TOPICS,
    fallbackMessage: "nie udało się wczytać tematów",
  });
  const list = useRead({
    key: ["youtube", "topic-runs", topicId ?? "all"],
    read: (signal) => client.topicRuns({ topicId }, signal),
    initial: NO_RUNS,
    fallbackMessage: "nie udało się wczytać historii wyszukiwań",
    pollMs: POLL_MS,
  });

  return (
    <div className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-xs text-ink-secondary">
        Temat
        <select
          className="rounded border border-border bg-sunken px-2 py-1 text-ink"
          value={topicId ?? ""}
          onChange={(event) => setTopicId(event.target.value === "" ? undefined : Number(event.target.value))}
        >
          <option value="">wszystkie</option>
          {topics.value.topics.map((topic) => (
            <option key={topic.id} value={topic.id}>
              {topic.phrase}
            </option>
          ))}
        </select>
        {list.value.retentionDays > 0 && (
          <span className="text-ink-faint">przebiegi z ostatnich {list.value.retentionDays} dni</span>
        )}
      </label>

      {list.error !== null && <UnreachableNotice onRetry={list.reload}>{list.error}</UnreachableNotice>}
      {list.status === "ready" && list.value.runs.length === 0 && (
        <p className="text-sm text-ink-muted">
          Nie było jeszcze żadnego przebiegu wyszukiwania. Tematy szukają w swoim odstępie — pierwszy wpis pojawi się sam.
        </p>
      )}
      <ul className="flex flex-col gap-1">
        {list.value.runs.map((run) => (
          <li key={run.id} className="flex flex-wrap items-baseline gap-3 rounded border border-border bg-panel px-3 py-2">
            <span className="text-xs tabular-nums text-ink-faint">{run.ranAt.toLocaleString("pl-PL")}</span>
            <span className="text-sm text-ink">{run.phrase}</span>
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${TONE[run.outcome]}`}>
              {runOutcomeLabel(run.outcome)}
            </span>
            <span className="min-w-0 flex-1 text-xs text-ink-secondary">{runSummary(run)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
