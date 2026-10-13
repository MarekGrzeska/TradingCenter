import { useState } from "react";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { messageOf, useRead } from "../data/query";
import { AddTopicDialog, FollowChannelDialog, RemoveDialog } from "./dialogs";
import { ALERT_RULES, ALERT_RULE_LABEL } from "./present";
import type { AlertRule, Channel, Topic, YoutubeApi } from "./youtubeApi";

/**
 * What is followed. The operator adds, changes the rule, pauses and — alone — takes off: the tools the agent holds add and
 * never remove, so this screen is the one door out.
 */

const SELECT = "rounded border border-border bg-sunken px-1 py-0.5 text-xs text-ink";
const POLL_MS = 60_000;

function RuleSelect({ value, disabled, onChange }: { value: AlertRule; disabled: boolean; onChange(rule: AlertRule): void }) {
  return (
    <select
      className={SELECT}
      value={value}
      disabled={disabled}
      aria-label="reguła powiadomień"
      onChange={(e) => onChange(e.target.value as AlertRule)}
    >
      {ALERT_RULES.map((rule) => (
        <option key={rule} value={rule}>
          {ALERT_RULE_LABEL[rule]}
        </option>
      ))}
    </select>
  );
}

function Origin({ by }: { by: "operator" | "agent" }) {
  return (
    <span className="rounded bg-raised px-1 text-[11px] text-ink-muted" title="kto dodał">
      {by === "agent" ? "agent" : "operator"}
    </span>
  );
}

export function ChannelsPanel({ client, onChanged }: { client: YoutubeApi; onChanged(): void }) {
  const list = useRead<{ channels: Channel[]; ceiling: number }>({
    key: ["youtube", "channels"],
    read: (signal) => client.channels(signal),
    initial: { channels: [], ceiling: 0 },
    fallbackMessage: "nie udało się wczytać kanałów",
    pollMs: POLL_MS,
  });
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Channel | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function change(channel: Channel, patch: { alertRule?: AlertRule; active?: boolean }) {
    setFailure(null);
    try {
      await client.setChannel(channel.channelId, patch, new AbortController().signal);
      list.reload();
      onChanged();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się zmienić kanału"));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <Button tone="primary" size="xs" onClick={() => setAdding(true)}>
          Obserwuj kanał
        </Button>
        <span className="text-xs text-ink-faint">
          {list.value.channels.length}/{list.value.ceiling || "—"} kanałów
        </span>
      </div>
      {list.error !== null && <UnreachableNotice onRetry={list.reload}>{list.error}</UnreachableNotice>}
      {failure !== null && <p className="text-sm text-critical">{failure}</p>}
      {list.status === "ready" && list.value.channels.length === 0 && (
        <p className="text-sm text-ink-muted">Nie obserwujesz jeszcze żadnego kanału.</p>
      )}
      <ul className="flex flex-col gap-1">
        {list.value.channels.map((channel) => (
          <li
            key={channel.channelId}
            className="flex flex-wrap items-center gap-3 rounded border border-border bg-panel px-3 py-2"
          >
            <span className="min-w-0 flex-1">
              <span className="text-sm text-ink">{channel.title}</span>{" "}
              <span className="text-xs text-ink-faint">{channel.handle ?? channel.channelId}</span>{" "}
              <Origin by={channel.addedBy} />
              {!channel.active && <span className="ml-2 text-xs text-warning">wstrzymany</span>}
              <span className="block text-xs text-ink-faint">
                ostatnio sprawdzony: {channel.lastDiscoveryAt?.toLocaleString("pl-PL") ?? "jeszcze nie"}
              </span>
            </span>
            <RuleSelect
              value={channel.alertRule}
              disabled={false}
              onChange={(alertRule) => void change(channel, { alertRule })}
            />
            <Button size="xs" tone="muted" onClick={() => void change(channel, { active: !channel.active })}>
              {channel.active ? "Wstrzymaj" : "Wznów"}
            </Button>
            <Button size="xs" tone="critical" onClick={() => setRemoving(channel)}>
              Zdejmij
            </Button>
          </li>
        ))}
      </ul>

      {adding && (
        <FollowChannelDialog
          client={client}
          onClose={() => setAdding(false)}
          onDone={() => {
            list.reload();
            onChanged();
          }}
        />
      )}
      {removing !== null && (
        <RemoveDialog
          what="kanał"
          name={removing.title}
          onRemove={() => client.unfollowChannel(removing.channelId, new AbortController().signal)}
          onClose={() => setRemoving(null)}
          onDone={() => {
            list.reload();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

export function TopicsPanel({ client, onChanged }: { client: YoutubeApi; onChanged(): void }) {
  const list = useRead<{ topics: Topic[]; ceiling: number }>({
    key: ["youtube", "topics"],
    read: (signal) => client.topics(signal),
    initial: { topics: [], ceiling: 0 },
    fallbackMessage: "nie udało się wczytać tematów",
    pollMs: POLL_MS,
  });
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Topic | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function change(topic: Topic, patch: { alertRule?: AlertRule; active?: boolean }) {
    setFailure(null);
    try {
      await client.setTopic(topic.id, patch, new AbortController().signal);
      list.reload();
      onChanged();
    } catch (cause: unknown) {
      setFailure(messageOf(cause, "nie udało się zmienić tematu"));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <Button tone="primary" size="xs" onClick={() => setAdding(true)}>
          Dodaj temat
        </Button>
        <span className="text-xs text-ink-faint">
          {list.value.topics.length}/{list.value.ceiling || "—"} tematów
        </span>
      </div>
      {list.error !== null && <UnreachableNotice onRetry={list.reload}>{list.error}</UnreachableNotice>}
      {failure !== null && <p className="text-sm text-critical">{failure}</p>}
      {list.status === "ready" && list.value.topics.length === 0 && (
        <p className="text-sm text-ink-muted">Nie ma jeszcze żadnego tematu.</p>
      )}
      <ul className="flex flex-col gap-1">
        {list.value.topics.map((topic) => (
          <li key={topic.id} className="flex flex-wrap items-center gap-3 rounded border border-border bg-panel px-3 py-2">
            <span className="min-w-0 flex-1">
              <span className="text-sm text-ink">{topic.phrase}</span> <Origin by={topic.addedBy} />
              {!topic.active && <span className="ml-2 text-xs text-warning">wstrzymany</span>}
              <span className="block text-xs text-ink-faint">
                co {topic.intervalMinutes} min · do {topic.maxVideosPerRun} filmów · ostatnio:{" "}
                {topic.lastRunAt?.toLocaleString("pl-PL") ?? "jeszcze nie szukano"}
              </span>
            </span>
            <RuleSelect
              value={topic.alertRule}
              disabled={false}
              onChange={(alertRule) => void change(topic, { alertRule })}
            />
            <Button size="xs" tone="muted" onClick={() => void change(topic, { active: !topic.active })}>
              {topic.active ? "Wstrzymaj" : "Wznów"}
            </Button>
            <Button size="xs" tone="critical" onClick={() => setRemoving(topic)}>
              Zdejmij
            </Button>
          </li>
        ))}
      </ul>

      {adding && (
        <AddTopicDialog
          client={client}
          onClose={() => setAdding(false)}
          onDone={() => {
            list.reload();
            onChanged();
          }}
        />
      )}
      {removing !== null && (
        <RemoveDialog
          what="temat"
          name={removing.phrase}
          onRemove={() => client.removeTopic(removing.id, new AbortController().signal)}
          onClose={() => setRemoving(null)}
          onDone={() => {
            list.reload();
            onChanged();
          }}
        />
      )}
    </div>
  );
}
