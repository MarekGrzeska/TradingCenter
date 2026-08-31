import { useMemo, useState } from "react";
import { UnreachableNotice } from "../../ui/UnreachableNotice";
import { agentApi, type AgentApi, type AgentUsageAggregate } from "../agentApi";
import { agentChatStore, type AgentChatStore } from "../agentChatStore";
import { defaultDateRangeInputs, toUsageRange, type DateRangeInputs } from "./dateRange";
import { pageOf, type Page } from "./pagination";
import { useUsage, type UsageState } from "./useUsage";
import { todayInWarsaw } from "../../ui/formatTime";
import { Button } from "../../ui/Button";

/**
 * What conversations have cost, before the Azure invoice says so. Every number is the module's own — the strings
 * stay strings the whole way to the `$` prefix, so there is no arithmetic here to get wrong.
 */
export function AgentCostView({
  api = agentApi,
  chatStore = agentChatStore,
}: {
  api?: AgentApi;
  chatStore?: AgentChatStore;
} = {}) {
  const [inputs, setInputs] = useState<DateRangeInputs>(defaultDateRangeInputs);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `inputs`'s identity changes every render; its two fields are the real dependency.
  const range = useMemo(() => toUsageRange(inputs), [inputs.from, inputs.to]);
  const usage = useUsage(api, range);

  function openConversation(sessionId: number): void {
    // `GET /usage` publishes only the three aggregates, not a per-call breakdown. Opening the conversation
    // is what answers that: each agent reply in the transcript is one call.
    chatStore.openSession(sessionId);
    chatStore.setExpanded(true);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 border-b border-border pb-3">
        <DateRangeControls inputs={inputs} onChange={setInputs} />
        {usage.status === "ready" && usage.summary && (
          // The one place the range's total lives: a sum scattered across three tables is not an answer
          // to the question this section exists for.
          <span className="ml-auto text-sm">
            <span className="text-ink-muted">Total cost </span>
            <span className="font-semibold text-ink">${usage.summary.totalCost}</span>
          </span>
        )}
      </div>
      <div className="max-h-[60vh] overflow-auto">
        <UsageBody usage={usage} onOpenConversation={openConversation} />
      </div>
    </div>
  );
}

function DateRangeControls({
  inputs,
  onChange,
}: {
  inputs: DateRangeInputs;
  onChange: (next: DateRangeInputs) => void;
}) {
  const today = todayInWarsaw();
  return (
    <div className="flex items-center gap-2 text-xs">
      <label htmlFor="agent-cost-from" className="text-ink-muted">
        From
      </label>
      <input
        id="agent-cost-from"
        type="date"
        value={inputs.from}
        max={inputs.to}
        onChange={(event) => onChange({ ...inputs, from: event.target.value })}
        className="rounded border border-border bg-sunken px-2 py-1 text-ink"
      />
      <label htmlFor="agent-cost-to" className="text-ink-muted">
        To
      </label>
      <input
        id="agent-cost-to"
        type="date"
        value={inputs.to}
        min={inputs.from}
        max={today}
        onChange={(event) => onChange({ ...inputs, to: event.target.value })}
        className="rounded border border-border bg-sunken px-2 py-1 text-ink"
      />
    </div>
  );
}

function UsageBody({
  usage,
  onOpenConversation,
}: {
  usage: UsageState;
  onOpenConversation: (sessionId: number) => void;
}) {
  if (usage.status === "loading") {
    return <p className="text-sm text-ink-muted">Reading usage…</p>;
  }

  if (usage.status === "unreachable") {
    return (
      <UnreachableNotice onRetry={usage.reload}>
        the agent module is not reachable, so usage for this range is unknown — this is
        not a zero. {usage.error}
      </UnreachableNotice>
    );
  }

  const { summary } = usage;
  if (!summary) return null; // "ready" always carries one; this is here for the type checker.

  const nothingUsed =
    summary.byModel.length === 0 && summary.bySession.length === 0 && summary.byDay.length === 0;

  if (nothingUsed) {
    return <p className="text-sm text-ink-muted">Nothing was used in this range.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <AggregateTable title="By model" keyLabel="Model" rows={summary.byModel} />
      <AggregateTable
        title="By conversation"
        keyLabel="Conversation"
        rows={summary.bySession}
        renderKey={(key) => `#${key}`}
        onRowOpen={(row) => onOpenConversation(Number(row.key))}
        openLabel="Open"
      />
      <AggregateTable title="By day" keyLabel="Day" rows={summary.byDay} />
    </div>
  );
}

/** Rows per page. Enough that a normal week of days or conversations needs no paging at
 *  all, small enough that a busy month does not push the third table off the screen. */
const PAGE_SIZE = 10;

function AggregateTable({
  title,
  keyLabel,
  rows,
  renderKey,
  onRowOpen,
  openLabel,
}: {
  title: string;
  keyLabel: string;
  rows: AgentUsageAggregate[];
  renderKey?: (key: string) => string;
  onRowOpen?: (row: AgentUsageAggregate) => void;
  openLabel?: string;
}) {
  const [requestedPage, setRequestedPage] = useState(0);
  const page = pageOf(rows, requestedPage, PAGE_SIZE);

  if (rows.length === 0) return null;

  return (
    <section>
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-secondary">{title}</h2>
      {/* `table-fixed` with the same colgroup in all three, and every table carrying the action column
          whether or not it has an action: three `table-auto` tables size their own columns from their own
          content, so the numbers in one do not land under the numbers in the next. */}
      <table className="w-full table-fixed text-sm">
        <colgroup>
          <col />
          <col className="w-28" />
          <col className="w-28" />
          <col className="w-40" />
          <col className="w-20" />
        </colgroup>
        <thead className="border-b border-secondary-line text-left text-[11px] uppercase tracking-wide text-secondary">
          <tr>
            <th className="px-2 py-1.5 font-normal">{keyLabel}</th>
            <th className="px-2 py-1.5 text-right font-normal">Input tokens</th>
            <th className="px-2 py-1.5 text-right font-normal">Output tokens</th>
            <th className="px-2 py-1.5 text-right font-normal">Cost</th>
            <th className="px-2 py-1.5" />
          </tr>
        </thead>
        <tbody>
          {page.rows.map((row) => (
            <tr key={row.key} className="border-t border-border">
              <td className="truncate px-2 py-1.5 font-semibold text-ink">
                {renderKey ? renderKey(row.key) : row.key}
              </td>
              <td className="px-2 py-1.5 text-right text-ink-secondary">
                {row.inputTokens.toLocaleString()}
              </td>
              <td className="px-2 py-1.5 text-right text-ink-secondary">
                {row.outputTokens.toLocaleString()}
              </td>
              <td className="px-2 py-1.5 text-right text-ink-secondary">${row.cost}</td>
              <td className="px-2 py-1.5 text-right">
                {onRowOpen && (
                  <Button
                    tone="muted"
                    size="xs"
                    onClick={() => onRowOpen(row)}
                  >
                    {openLabel}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination label={title} page={page} onPage={setRequestedPage} />
    </section>
  );
}

/**
 * Absent entirely below one page — a table of three models does not need to say it is
 * showing three of three.
 */
function Pagination({
  label,
  page,
  onPage,
}: {
  label: string;
  page: Page<AgentUsageAggregate>;
  onPage: (index: number) => void;
}) {
  if (page.count <= 1) return null;

  return (
    <div className="mt-1 flex items-center gap-2 px-2 text-[11px] text-ink-muted">
      <span>
        {page.firstRow}–{page.lastRow} of {page.total}
      </span>
      <div className="ml-auto flex items-center gap-1">
        <Button
          size="xs"
          onClick={() => onPage(page.index - 1)}
          disabled={page.index === 0}
          aria-label={`${label}: previous page`}
        >
          Prev
        </Button>
        <span aria-current="page">
          {page.index + 1} / {page.count}
        </span>
        <Button
          size="xs"
          onClick={() => onPage(page.index + 1)}
          disabled={page.index === page.count - 1}
          aria-label={`${label}: next page`}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
