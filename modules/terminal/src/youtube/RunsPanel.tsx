import { useState } from "react";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { dayRange, runOutcomeLabel, runSummary } from "./present";
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
  // Days as `<input type=date>` gives them; empty is an open end.
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const reversed = from !== "" && to !== "" && from > to;
  const narrowed = from !== "" || to !== "";
  const topics = useRead({
    key: ["youtube", "topics"],
    read: (signal) => client.topics(signal),
    initial: NO_TOPICS,
    fallbackMessage: "nie udało się wczytać tematów",
  });
  const list = useRead({
    key: ["youtube", "topic-runs", topicId ?? "all", from, to],
    read: (signal) => client.topicRuns({ topicId, ...dayRange(from, to) }, signal),
    initial: NO_RUNS,
    fallbackMessage: "nie udało się wczytać historii wyszukiwań",
    pollMs: POLL_MS,
    // A range that ends before it starts is said here, not sent to be refused.
    enabled: !reversed,
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
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
        </label>
        <label className="flex items-center gap-2 text-xs text-ink-secondary">
          Od
          <input
            type="date"
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            value={from}
            max={to === "" ? undefined : to}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-ink-secondary">
          Do
          <input
            type="date"
            className="rounded border border-border bg-sunken px-2 py-1 text-ink"
            value={to}
            min={from === "" ? undefined : from}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        {narrowed && (
          <Button
            size="xs"
            tone="muted"
            onClick={() => {
              setFrom("");
              setTo("");
            }}
          >
            Wyczyść dni
          </Button>
        )}
        {list.value.retentionDays > 0 && (
          <span className="text-xs text-ink-faint">przebiegi z ostatnich {list.value.retentionDays} dni</span>
        )}
      </div>

      {reversed && <p className="text-sm text-warning">Dzień początkowy jest po końcowym — zakres jest pusty.</p>}

      {list.error !== null && <UnreachableNotice onRetry={list.reload}>{list.error}</UnreachableNotice>}
      {!reversed && list.status === "ready" && list.value.runs.length === 0 && (
        <p className="text-sm text-ink-muted">
          {narrowed
            ? `W wybranych dniach nie było przebiegów${topicId === undefined ? "" : " tego tematu"}. Wyczyść dni, żeby zobaczyć całą historię.`
            : topicId !== undefined
              ? "Ten temat nie ma jeszcze przebiegów w historii."
              : "Nie było jeszcze żadnego przebiegu wyszukiwania. Tematy szukają w swoim odstępie — pierwszy wpis pojawi się sam."}
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
