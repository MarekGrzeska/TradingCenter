import { useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { DefinitionDialog } from "./DefinitionDialog";
import type { Definition, Revision, Strategy, StrategyApi, Watch } from "./strategyApi";

/**
 * The rules somebody wrote, and which revision each watch is actually computing.
 *
 * **A coded entry is named as one and has no edit control.** Greyed-out buttons with no
 * explanation read as a fault; saying "kod w obrazie" says it is a decision. The rule of a
 * coded entry lives in the repository under that id, which is where somebody changes it
 * (`terminal-strategy-configurator`, "Konfigurator nie obiecuje wykonania ani nie udaje
 * edycji kodu").
 *
 * **A newer revision does not move a running watch**, and this panel says so where it would
 * otherwise be discovered: a watch pinned to revision 2 next to a definition at revision 4
 * is the ordinary state, not a fault.
 */

const NO_DEFINITIONS: Definition[] = [];
const NO_REVISIONS: Revision[] = [];

export function DefinitionsPanel({
  client,
  strategies,
  watches,
  onChanged,
}: {
  client: StrategyApi;
  /** The whole catalogue — both kinds — so the coded entries can be named as such. */
  strategies: Strategy[];
  watches: Watch[];
  onChanged(): void;
}) {
  const [writing, setWriting] = useState(false);
  const [revising, setRevising] = useState<{ definition: Definition; from: Revision } | null>(
    null,
  );

  const definitions = useRead<Definition[]>({
    key: ["strategy", "definitions"],
    read: (signal) => client.listDefinitions(signal),
    initial: NO_DEFINITIONS,
    fallbackMessage: "nie udało się odczytać reguł",
  });

  const coded = strategies.filter((one) => one.source === "code");

  async function reviseFrom(definition: Definition) {
    const revisions = await client.listRevisions(
      definition.strategyId,
      new AbortController().signal,
    );
    const newest = (revisions.length > 0 ? revisions : NO_REVISIONS)[0];
    if (newest !== undefined) setRevising({ definition, from: newest });
  }

  return (
    <section className="flex flex-col gap-2" data-testid="definitions">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-xs font-semibold text-ink-secondary">Reguły</h2>
        <span className="text-xs text-ink-faint">
          zapis tworzy rewizję i niczego nie uruchamia
        </span>
        <Button size="xs" className="ml-auto" onClick={() => setWriting(true)}>
          Nowa reguła
        </Button>
      </header>

      {definitions.error !== null && (
        <p className="text-xs text-warning">{definitions.error}</p>
      )}

      {definitions.status === "ready" && definitions.value.length === 0 && (
        <p className="text-xs text-ink-muted">
          Żadnej wyklikanej reguły. Wpisy poniżej są kodem w obrazie — ich reguła jest
          w repozytorium pod tym samym identyfikatorem.
        </p>
      )}

      <ul className="flex flex-col gap-1">
        {definitions.value.map((definition) => {
          const pinned = watches.filter(
            (watch) => watch.strategyId === definition.strategyId,
          );
          const behind = pinned.filter((watch) => watch.strategyRevisionId !== null);
          return (
            <li
              key={definition.id}
              className="flex flex-wrap items-center gap-2 rounded border border-border px-2 py-1 text-xs"
            >
              <span className="text-ink">{definition.name}</span>
              <span className="text-ink-faint">{definition.strategyId}</span>
              <span className="text-ink-secondary">rewizja {definition.latestVersion}</span>
              {behind.length > 0 && (
                <span className="text-ink-faint">
                  {behind.length === 1 ? "obserwacja liczy" : "obserwacje liczą"} przypiętą
                  rewizję — przejście na nowszą to osobny ruch
                </span>
              )}
              <Button
                size="xs"
                tone="muted"
                className="ml-auto"
                onClick={() => void reviseFrom(definition)}
              >
                Nowa rewizja
              </Button>
            </li>
          );
        })}

        {coded.map((entry) => (
          <li
            key={entry.id}
            className="flex flex-wrap items-center gap-2 rounded border border-border px-2 py-1 text-xs opacity-80"
            data-testid="coded-entry"
          >
            <span className="text-ink">{entry.name}</span>
            <span className="text-ink-faint">{entry.id}</span>
            {/* Said, not implied by a missing button: this one is code, and that is a
                decision rather than something that failed to load. */}
            <span className="text-ink-secondary">kod w obrazie</span>
            <span className="ml-auto text-ink-faint">reguła w repozytorium, nie tutaj</span>
          </li>
        ))}
      </ul>

      {writing && (
        <DefinitionDialog
          client={client}
          onClose={() => setWriting(false)}
          onSaved={() => {
            setWriting(false);
            definitions.reload();
            onChanged();
          }}
        />
      )}

      {revising !== null && (
        <DefinitionDialog
          client={client}
          existing={revising.definition}
          startFrom={revising.from.definition}
          onClose={() => setRevising(null)}
          onSaved={() => {
            setRevising(null);
            definitions.reload();
            onChanged();
          }}
        />
      )}
    </section>
  );
}
