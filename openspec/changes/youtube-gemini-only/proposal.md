## Why

Od włączenia na produkcji napisy YouTube (`direct`) nie przyniosły ani jednej transkrypcji: YouTube odmawia
każdemu adresowi Azure, więc każdy film i tak przepisuje Gemini. Łańcuch „napisy, potem Gemini” utrzymywał
dostawcę, który z produkcji nie działa, osobny odpoczynek dla niego, wybór języka napisów, zależność
`youtube-transcript-api` i komunikat o blokadzie, który operator brał za awarię. Operator zdecydował
(13 października 2026): tylko Gemini, reszta do usunięcia. Koszt zmierzony tego dnia: ok. 0,07 USD za film
30-minutowy na `gemini-3.1-flash-lite`.

## What Changes

- **Jeden dostawca transkrypcji**: `YOUTUBE_TRANSCRIBER` = `gemini` albo `sim`. Usunięte: `direct`
  (`youtube-transcript-api` i zależność), łańcuch dostawców (`TranscriptChain`, `ChainAnswer`, `Deferred`,
  flaga `listens`), wybór języka napisów (`TRANSCRIPT_LANGUAGES`), dzienny sufit napisów
  (`DAILY_TRANSCRIPT_UNITS`), odpoczynek napisów (`PROVIDER_COOLDOWN_MINUTES`).
- **Odpoczynek Gemini** po odmowie: `YOUTUBE_TRANSCRIBER_COOLDOWN_MINUTES` (15) — dawny
  `LISTENER_COOLDOWN_MINUTES` pod nazwą bez łańcucha.
- **Symulacja**: jeden `SimTranscriber`, który słyszy `speech` filmu ze scenariusza; tryby napisów
  (od razu / po czasie / nigdy) i ich koszt w kredytach znikają. Transmisja w symulacji dostaje długość,
  gdy się kończy, jak w Data API.
- **Ustawienia wycofane** są nazywane przy starcie przez `scripts/dev.py` (`RETIRED_SETTINGS`).
- **Produkcja**: Terraform ustawia `YOUTUBE_TRANSCRIBER=gemini`; `YOUTUBE_TRANSCRIPT_PROVIDERS=gemini`
  zostaje na czas przejścia (stary obraz go wymaga, nowy go ignoruje) i znika w kolejnym apply.

Bez zmian: kontrakt REST i ekran (dostawca transkrypcji nadal ma rolę `transcripts`), schemat bazy,
Gemini, sufit w sekundach filmu, ponowienia i `gave_up`.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-transcripts`: jeden dostawca zamiast łańcucha; usunięte wymaganie o języku napisów.
- `youtube-data-simulation`: symulowany jest jeden dostawca transkrypcji.

Obie zdolności powstały w `add-youtube-archive` i zmieniły się w `youtube-transcripts-through-gemini` (obie
zmergowane, niezarchiwizowane) — **ta zmiana MUST zostać zarchiwizowana po nich**.

Pominięte: `design.md` (decyzja jest operatora i opisana wyżej) i `review.md` (zmiana tylko usuwa; testy
pętli przepisane na jednego dostawcę).

## Impact

- `modules/workbench/youtube_data`: `providers/` (usunięte `chain.py`, `direct.py`), `config.py`,
  `budget.py`, `ingest.py`, `views.py`, `sim/`; testy; `pyproject.toml` bez `youtube-transcript-api`.
- `infra/app-service.tf`: `YOUTUBE_TRANSCRIBER`.
- `scripts/dev.py`: wycofane ustawienia.
- `docs/youtube-jak-dziala.html`, README pakietu, `.env.example`.
