import { useMemo, useState } from "react";
import { resolveEndpoints } from "../data/config";
import { youtubeIdentity } from "../data/marketData";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { usePrompts } from "./usePrompts";
import { createYoutubeApi, type Prompt, type YoutubeApi } from "./youtubeApi";

/**
 * What a model is told to look for in a film. The operator writes, edits and — alone — deletes: the agent only chooses one by
 * name. New words are a new version, and a reading says which version made it, so editing here never rewrites what was
 * already said. The seeded prompt is edited like any other and has no delete: there is always a prompt to read by.
 */

const INPUT = "rounded border border-border bg-sunken px-2 py-1 text-ink";

export function PromptsView({ api }: { api?: YoutubeApi } = {}) {
  const client = useMemo(
    () => api ?? createYoutubeApi(resolveEndpoints().youtubeHttp, youtubeIdentity),
    [api],
  );
  const list = usePrompts(client);
  const [editing, setEditing] = useState<Prompt | "new" | null>(null);
  const [removing, setRemoving] = useState<Prompt | null>(null);

  const { prompts, maxChars, ceiling } = list.value;

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold text-ink">Prompty</h1>
        <Button tone="primary" size="xs" onClick={() => setEditing("new")}>
          Nowy prompt
        </Button>
        <span className="text-xs text-ink-faint">
          {prompts.length}/{ceiling || "—"} promptów · analiza filmów z archiwum YouTube
        </span>
      </header>
      {list.error !== null && <UnreachableNotice onRetry={list.reload}>{list.error}</UnreachableNotice>}
      <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {prompts.map((prompt) => (
          <li key={prompt.id} className="flex flex-col gap-2 rounded border border-border bg-panel px-3 py-2">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-ink">{prompt.name}</span>
              <span className="text-xs text-ink-faint">v{prompt.version}</span>
              {prompt.seeded && (
                <span className="rounded bg-raised px-1 text-[11px] text-ink-muted" title="zawsze jest co najmniej jeden prompt">
                  domyślny
                </span>
              )}
              <span className="ml-auto flex gap-2">
                <Button size="xs" tone="muted" onClick={() => setEditing(prompt)}>
                  Edytuj
                </Button>
                {!prompt.seeded && (
                  <Button size="xs" tone="critical" onClick={() => setRemoving(prompt)}>
                    Usuń
                  </Button>
                )}
              </span>
            </div>
            <p className="line-clamp-3 whitespace-pre-wrap text-xs text-ink-secondary">{prompt.body}</p>
            <p className="text-xs text-ink-faint">{usage(prompt)}</p>
          </li>
        ))}
      </ul>

      {editing !== null && (
        <PromptDialog
          client={client}
          prompt={editing === "new" ? null : editing}
          maxChars={maxChars}
          onClose={() => setEditing(null)}
          onDone={list.reload}
        />
      )}
      {removing !== null && (
        <ConfirmDialog
          title="Usuń prompt"
          confirmLabel="Usuń"
          busyLabel="Usuwam…"
          tone="danger"
          fallbackError="nie udało się usunąć promptu"
          onConfirm={async () => {
            await client.deletePrompt(removing.id, new AbortController().signal);
            list.reload();
          }}
          onClose={() => setRemoving(null)}
        >
          <p className="text-xs text-ink-secondary">
            <span className="text-ink">{removing.name}</span> znika z listy wyboru. Odczyty, które powstały tym promptem,
            zostają i dalej niosą jego nazwę.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}

/** Who reads by a prompt, in words — "nieużywany" is a fact worth saying, because it is what makes a prompt deletable. */
function usage(prompt: Prompt): string {
  const parts = [
    ...(prompt.channels.length > 0 ? [`kanały: ${prompt.channels.join(", ")}`] : []),
    ...(prompt.topics.length > 0 ? [`tematy: ${prompt.topics.join(", ")}`] : []),
  ];
  return parts.length === 0 ? "nieużywany przez żaden kanał ani temat" : parts.join(" · ");
}

function PromptDialog({
  client,
  prompt,
  maxChars,
  onClose,
  onDone,
}: {
  client: YoutubeApi;
  prompt: Prompt | null;
  maxChars: number;
  onClose(): void;
  onDone(): void;
}) {
  const [name, setName] = useState(prompt?.name ?? "");
  const [body, setBody] = useState(prompt?.body ?? "");
  const changed = prompt === null || name.trim() !== prompt.name || body.trim() !== prompt.body.trim();

  return (
    <ConfirmDialog
      title={prompt === null ? "Nowy prompt" : `Edytuj prompt: ${prompt.name}`}
      confirmLabel="Zapisz"
      busyLabel="Zapisuję…"
      confirmDisabled={name.trim() === "" || body.trim() === "" || !changed}
      fallbackError="nie udało się zapisać promptu"
      onConfirm={async () => {
        const signal = new AbortController().signal;
        if (prompt === null) await client.createPrompt({ name: name.trim(), body: body.trim() }, signal);
        else
          await client.updatePrompt(
            prompt.id,
            {
              ...(name.trim() === prompt.name ? {} : { name: name.trim() }),
              ...(body.trim() === prompt.body.trim() ? {} : { body: body.trim() }),
            },
            signal,
          );
        onDone();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Nazwa</span>
          <input className={INPUT} value={name} autoFocus onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Co model ma znaleźć w filmie i jak ułożyć tekst</span>
          <textarea
            className={`${INPUT} min-h-48 font-mono text-xs`}
            value={body}
            maxLength={maxChars || undefined}
            onChange={(e) => setBody(e.target.value)}
          />
          <span className="text-ink-faint">
            {body.length}/{maxChars || "—"} znaków.{" "}
            {prompt !== null && "Nowa treść to nowa wersja; dotychczasowe odczyty zostają jak były."}
          </span>
        </label>
        <p className="text-xs text-ink-faint">
          Prompt nie zmienia tego, czym jest transkrypcja (dana obca) ani kształtu odpowiedzi — streszczenie, tekst i ocena
          wpływu 1–10 — to zostaje w kodzie.
        </p>
      </div>
    </ConfirmDialog>
  );
}
