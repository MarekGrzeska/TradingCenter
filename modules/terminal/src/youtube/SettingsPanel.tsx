import { useEffect, useState } from "react";
import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import type { LoopSettings, YoutubeApi } from "./youtubeApi";

/**
 * How often the loop passes, and what a topic added without limits of its own gets. Saved in the archive's database, so a
 * change needs no restart: the loop reads the interval after every pass and a wait in progress is cut or stretched to it.
 * Topics already on the list keep their own limits — these are the defaults for the next one.
 */

const INPUT = "w-28 rounded border border-border bg-sunken px-2 py-1 text-ink";

const NONE: LoopSettings = {
  pollIntervalMinutes: 0,
  topicIntervalMinutes: 0,
  topicMaxVideos: 0,
  saved: false,
  pollIntervalRange: [0, 0],
  topicIntervalRange: [0, 0],
  topicMaxVideosRange: [0, 0],
};

export function SettingsPanel({ client }: { client: YoutubeApi }) {
  const read = useRead<LoopSettings>({
    key: ["youtube", "settings"],
    read: (signal) => client.settings(signal),
    initial: NONE,
    fallbackMessage: "nie udało się wczytać ustawień",
  });
  const standing = read.value;
  const [poll, setPoll] = useState("");
  const [interval, setInterval] = useState("");
  const [max, setMax] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // What the form shows follows what is saved: after a save, and after the first answer.
  useEffect(() => {
    if (read.status !== "ready") return;
    setPoll(String(standing.pollIntervalMinutes));
    setInterval(String(standing.topicIntervalMinutes));
    setMax(String(standing.topicMaxVideos));
  }, [read.status, standing]);

  const changed =
    poll.trim() !== String(standing.pollIntervalMinutes) ||
    interval.trim() !== String(standing.topicIntervalMinutes) ||
    max.trim() !== String(standing.topicMaxVideos);

  async function save() {
    setFailure(null);
    setBusy(true);
    try {
      await client.updateSettings(
        {
          pollIntervalMinutes: wholeNumber(poll, "co ile minut przebieg pętli"),
          topicIntervalMinutes: wholeNumber(interval, "co ile minut szukać tematu"),
          topicMaxVideos: wholeNumber(max, "ile filmów z wyszukiwania"),
        },
        new AbortController().signal,
      );
      read.reload();
    } catch (cause: unknown) {
      setFailure(cause instanceof Error ? cause.message : "nie udało się zapisać ustawień");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      {read.error !== null && <UnreachableNotice onRetry={read.reload}>{read.error}</UnreachableNotice>}
      {read.status === "ready" && !standing.saved && (
        <p className="text-xs text-ink-faint">Nic jeszcze nie zapisano — obowiązują wartości z konfiguracji workbencha.</p>
      )}

      <fieldset className="flex flex-col gap-2 rounded border border-border bg-panel px-3 py-2">
        <legend className="px-1 text-xs text-ink-secondary">Pętla</legend>
        <label className="flex items-center gap-3 text-xs">
          <input className={INPUT} inputMode="numeric" value={poll} onChange={(e) => setPoll(e.target.value)} />
          <span className="text-ink-secondary">minut między przebiegami</span>
          <span className="text-ink-faint">{range(standing.pollIntervalRange, "min")}</span>
        </label>
        <p className="text-xs text-ink-faint">
          Co przebieg: sprawdzenie każdego kanału, transkrypcje, odczyty i ogłoszenia. Każdy kanał kosztuje jednostkę dziennego
          limitu źródła przy każdym przebiegu, więc krótszy odstęp zużywa limit szybciej.
        </p>
      </fieldset>

      <fieldset className="flex flex-col gap-2 rounded border border-border bg-panel px-3 py-2">
        <legend className="px-1 text-xs text-ink-secondary">Nowy temat bez własnych granic</legend>
        <label className="flex items-center gap-3 text-xs">
          <input className={INPUT} inputMode="numeric" value={interval} onChange={(e) => setInterval(e.target.value)} />
          <span className="text-ink-secondary">minut między wyszukiwaniami tematu</span>
          <span className="text-ink-faint">{range(standing.topicIntervalRange, "min")}</span>
        </label>
        <label className="flex items-center gap-3 text-xs">
          <input className={INPUT} inputMode="numeric" value={max} onChange={(e) => setMax(e.target.value)} />
          <span className="text-ink-secondary">filmów z jednego wyszukiwania</span>
          <span className="text-ink-faint">{range(standing.topicMaxVideosRange, "")}</span>
        </label>
        <p className="text-xs text-ink-faint">
          Dotyczy tematów dopisywanych od teraz — przez ciebie i przez agenta. Tematy już na liście zachowują swoje wartości.
          Wyniki trafiają do zakładki Kandydaci; każde wyszukiwanie kosztuje sto jednostek dziennego limitu źródła.
        </p>
      </fieldset>

      {failure !== null && (
        <p role="alert" className="text-sm text-critical">
          {failure}
        </p>
      )}
      <div>
        <Button tone="primary" size="sm" disabled={busy || !changed || read.status !== "ready"} onClick={() => void save()}>
          {busy ? "Zapisuję…" : "Zapisz"}
        </Button>
      </div>
    </div>
  );
}

function range([low, high]: readonly [number, number], unit: string): string {
  return high === 0 ? "" : `${low}–${high}${unit === "" ? "" : ` ${unit}`}`;
}

function wholeNumber(text: string, field: string): number {
  const value = Number(text.trim());
  if (text.trim() === "" || !Number.isInteger(value)) {
    throw new Error(`pole „${field}" musi być liczbą całkowitą`);
  }
  return value;
}
