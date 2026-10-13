/**
 * What the screen says about a film and about the archive, as functions of the data — so the sentences are tested as text and
 * not reached through the DOM. Polish, like the social tab.
 */

import type { AlertRule, ArchiveState, Film, ProviderState, Sentiment } from "./youtubeApi";

/** Where a film is on its road, in words. A film with a reading is said to be read; one without says why not. */
export function stateLabel(film: Film): string {
  if (film.liveStatus === "live") return "trwa transmisja — czeka na koniec";
  switch (film.state) {
    case "discovered":
      return "czeka na transkrypcję";
    case "no_transcript":
      return `brak napisów (próba ${film.attempts}) — zapytamy ponownie`;
    case "transcribed":
      return "ma napisy, czeka na odczyt";
    case "analysed":
    case "notified":
    case "quiet":
      return film.reading === null ? "odczyt niedostępny" : "odczytany";
    case "gave_up":
      return `porzucony: brak napisów po ${film.attempts} próbach`;
    case "skipped":
      return `pominięty: ${film.skipReason ?? "bez podania powodu"}`;
  }
}

export const SENTIMENT_LABEL: Record<Sentiment, string> = {
  bullish: "wzrost",
  bearish: "spadek",
  neutral: "neutralnie",
};

export const SENTIMENT_ARROW: Record<Sentiment, string> = {
  bullish: "▲",
  bearish: "▼",
  neutral: "▬",
};

export const ALERT_RULE_LABEL: Record<AlertRule, string> = {
  always: "zawsze",
  threshold: "od progu wpływu",
  never: "nigdy",
};

export const ALERT_RULES: AlertRule[] = ["always", "threshold", "never"];

/** `12:34` for a film under an hour or `1 h 02 min`, or nothing where the source could not say — a feed does not. */
export function duration(seconds: number | null): string | null {
  if (seconds === null) return null;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${Math.max(minutes, 1)} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

/** What one provider has spent of its day, in the provider's own unit. */
export function usageLine(provider: ProviderState): string {
  return `${provider.name}: ${provider.spentToday}/${provider.ceiling} ${provider.unit}`;
}

/** Every reason the list may be empty or thin that is not "nothing happened", each a sentence. Empty when the archive is
 *  simply working — the list then speaks for itself. */
export function warnings(state: ArchiveState, now: Date = new Date()): string[] {
  const found: string[] = [];
  if (state.stale) {
    const age = state.loopAgeSeconds === null ? "" : ` (od ${Math.round(state.loopAgeSeconds / 60)} min)`;
    found.push(`Pętla archiwum nie ukończyła przebiegu od dłuższego czasu${age}. Pusta lista nie znaczy, że nic nie opublikowano.`);
  }
  // A captions provider refused from the cloud every time is not news while another one delivers the words: the usage
  // line still shows it, and the films are not waiting. The note is for when nobody who could answer is letting us in.
  const transcripts = state.providers.filter((provider) => provider.role === "transcripts");
  const someoneDelivers = transcripts.some((provider) => !provider.blocked && !provider.exhausted);
  for (const provider of state.providers) {
    if (provider.blocked && !(provider.role === "transcripts" && someoneDelivers)) {
      found.push(
        `Dostawca „${provider.name}" odmówił${provider.blockedReason ? ` (${provider.blockedReason})` : ""}. ` +
          "To chwilowe — film zostaje w kolejce i zostanie ponowiony za kilkanaście minut.",
      );
    }
    if (provider.exhausted) {
      found.push(
        `Dzienny limit „${provider.name}" (${provider.ceiling} ${provider.unit}) wyczerpany — praca wraca o północy UTC ` +
          `(${nextMidnightUtc(now)}).`,
      );
    }
  }
  if (!state.modelConfigured) {
    found.push("Model nie jest skonfigurowany — odczyty nie powstają. Filmy są odkrywane i transkrybowane dalej.");
  }
  return found;
}

function nextMidnightUtc(now: Date): string {
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
  return next.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}
