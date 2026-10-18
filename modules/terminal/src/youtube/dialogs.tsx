import { useState } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import type { YoutubeApi } from "./youtubeApi";

/**
 * The four questions this tab asks the operator. A refusal from the module — a ceiling, a channel that does not exist, a
 * limit out of range — stays in the dialog with its reason: it is an answer to what was asked, not a failure of the screen.
 */

const INPUT = "rounded border border-border bg-sunken px-2 py-1 text-ink";

export function FollowChannelDialog({
  client,
  onClose,
  onDone,
}: {
  client: YoutubeApi;
  onClose(): void;
  onDone(): void;
}) {
  const [reference, setReference] = useState("");
  const [already, setAlready] = useState<string | null>(null);

  if (already !== null) {
    return (
      <ConfirmDialog
        title="Kanał już jest na liście"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          <span className="text-ink">{already}</span> jest już obserwowany. Nic nie zmieniono.
        </p>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Obserwuj kanał"
      confirmLabel="Obserwuj"
      busyLabel="Pytam YouTube…"
      confirmDisabled={reference.trim() === ""}
      fallbackError="nie udało się dodać kanału"
      closeOnSuccess={false}
      onConfirm={async () => {
        const result = await client.followChannel(reference.trim(), new AbortController().signal);
        onDone();
        if (!result.created) {
          setAlready(result.channel.title);
          return;
        }
        onClose();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Adres kanału, @uchwyt albo identyfikator</span>
          <input
            className={INPUT}
            value={reference}
            autoFocus
            placeholder="@nazwa lub https://www.youtube.com/channel/UC…"
            onChange={(e) => setReference(e.target.value)}
          />
        </label>
      </div>
    </ConfirmDialog>
  );
}

export function AddTopicDialog({
  client,
  onClose,
  onDone,
}: {
  client: YoutubeApi;
  onClose(): void;
  onDone(): void;
}) {
  const [phrase, setPhrase] = useState("");
  const [interval, setInterval] = useState("");
  const [max, setMax] = useState("");

  return (
    <ConfirmDialog
      title="Dodaj temat"
      confirmLabel="Dodaj"
      busyLabel="Dodaję…"
      confirmDisabled={phrase.trim() === ""}
      fallbackError="nie udało się dodać tematu"
      onConfirm={async () => {
        await client.addTopic(
          {
            phrase: phrase.trim(),
            ...(interval.trim() === "" ? {} : { intervalMinutes: wholeNumber(interval, "co ile minut") }),
            ...(max.trim() === "" ? {} : { maxVideosPerRun: wholeNumber(max, "ile filmów") }),
          },
          new AbortController().signal,
        );
        onDone();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-ink-secondary">Fraza do wyszukiwania</span>
          <input
            className={INPUT}
            value={phrase}
            autoFocus
            placeholder="gold price outlook"
            onChange={(e) => setPhrase(e.target.value)}
          />
        </label>
        <div className="flex gap-3">
          <label className="flex flex-1 flex-col gap-1 text-xs">
            <span className="text-ink-secondary">Co ile minut (opcjonalnie)</span>
            <input className={INPUT} inputMode="numeric" value={interval} onChange={(e) => setInterval(e.target.value)} />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs">
            <span className="text-ink-secondary">Filmów na wyszukanie (opcjonalnie)</span>
            <input className={INPUT} inputMode="numeric" value={max} onChange={(e) => setMax(e.target.value)} />
          </label>
        </div>
        <p className="text-xs text-ink-faint">
          Każde wyszukiwanie zużywa dzienny limit źródła (sto jednostek z dziesięciu tysięcy klucza YouTube). Puste pola
          biorą wartości z ustawień.
        </p>
      </div>
    </ConfirmDialog>
  );
}

export function AnalyseDialog({
  client,
  onClose,
  onDone,
}: {
  client: YoutubeApi;
  onClose(): void;
  onDone(): void;
}) {
  const [reference, setReference] = useState("");
  const [queued, setQueued] = useState<string | null>(null);

  if (queued !== null) {
    return (
      <ConfirmDialog
        title="Film w kolejce"
        confirmLabel="Zamknij"
        busyLabel="Zamykam…"
        cancelLabel={null}
        onConfirm={onClose}
        onClose={onClose}
      >
        <p className="text-xs text-ink-secondary">
          <span className="text-ink">{queued}</span> czeka na transkrypcję i odczyt. Pojawi się na liście po najbliższym
          przebiegu pętli.
        </p>
      </ConfirmDialog>
    );
  }

  return (
    <ConfirmDialog
      title="Przeanalizuj film"
      confirmLabel="Dodaj do kolejki"
      busyLabel="Pytam YouTube…"
      confirmDisabled={reference.trim() === ""}
      fallbackError="nie udało się dodać filmu"
      closeOnSuccess={false}
      onConfirm={async () => {
        const result = await client.analyse(reference.trim(), new AbortController().signal);
        onDone();
        setQueued(result.created ? result.title : `${result.title} (już w archiwum)`);
      }}
      onClose={onClose}
    >
      <label className="flex flex-col gap-1 text-xs">
        <span className="text-ink-secondary">Adres filmu albo jego identyfikator</span>
        <input
          className={INPUT}
          value={reference}
          autoFocus
          placeholder="https://www.youtube.com/watch?v=…"
          onChange={(e) => setReference(e.target.value)}
        />
        <span className="text-ink-faint">Kosztuje jednostkę dziennego limitu źródła. Nie wysyła powiadomienia.</span>
      </label>
    </ConfirmDialog>
  );
}

export function RemoveDialog({
  what,
  name,
  onRemove,
  onClose,
  onDone,
}: {
  what: "kanał" | "temat";
  name: string;
  onRemove(): Promise<void>;
  onClose(): void;
  onDone(): void;
}) {
  return (
    <ConfirmDialog
      title={`Zdejmij ${what} z listy`}
      confirmLabel="Zdejmij"
      busyLabel="Zdejmuję…"
      tone="danger"
      fallbackError={`nie udało się zdjąć ${what === "kanał" ? "kanału" : "tematu"}`}
      onConfirm={async () => {
        await onRemove();
        onDone();
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-2 text-xs">
        <p className="text-ink-secondary">
          <span className="text-ink">{name}</span> przestaje być obserwowany.
        </p>
        <p className="text-ink-secondary">
          Filmy i odczyty, które już zebrano, <strong className="text-ink">zostają w archiwum</strong> — lista jest
          powodem, dla którego szukamy, nie tym, co przechowujemy. To jedyne miejsce, z którego coś schodzi z listy:
          agent może tylko dopisywać.
        </p>
      </div>
    </ConfirmDialog>
  );
}

/** `Number("abc")` is `NaN`, which JSON writes as `null` — and `null` takes the setting's default, so a typo would pass
 *  as a choice. */
function wholeNumber(text: string, field: string): number {
  const value = Number(text.trim());
  if (!Number.isInteger(value)) {
    throw new Error(`pole „${field}" musi być liczbą całkowitą`);
  }
  return value;
}
