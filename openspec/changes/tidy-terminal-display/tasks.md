## 1. market-data: liczba świec i objętość

- [x] 1.1 Przenieś `ESTIMATED_BYTES_PER_CANDLE` z `market_data/jobs/plan.py` do
  `market_data/models.py` i zaimportuj ją z powrotem w `plan.py` — jedna stała, dwóch czytelników
- [x] 1.2 Dopisz `count(c.period_start) AS candle_count` do `_SELECT_STATUS` w `tracking.py`
  (**nie** `count(*)` — przy `LEFT JOIN` dałoby 1 dla pary bez świec) i przenieś liczbę do
  `TrackedPairStatus`
- [x] 1.3 Dodaj `candle_count` i `estimated_bytes` do `TrackedPairOut` w `contract.py`, licząc
  objętość ze stałej z 1.1; zadbaj, żeby `TrackedPairOut.of()` (para świeżo dodana) dawała zera,
  a nie `None`
- [x] 1.4 Test integracyjny (`-m db`): para z zebranymi świecami podaje ich liczbę, para bez świec
  podaje zero, a nie jeden
- [x] 1.5 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright`

## 2. Kontrakt dociera do terminala

- [x] 2.1 `pnpm contract:generate` w `modules/terminal` — `src/data/contract.generated.ts` nigdy
  ręcznie
- [x] 2.2 `TrackedPair` w `src/data/types.ts` dostaje `candleCount: number` i
  `estimatedBytes: number`
- [x] 2.3 `mapTrackedPair` w `src/data/archive.ts` przepisuje obie liczby ze snake_case
- [x] 2.4 `pnpm contract:check` przechodzi, `pnpm typecheck` przechodzi

## 3. Instruments: rozwinięcie mówi, ile danych jest

- [x] 3.1 `IntervalCoverage` dalej woła `archive.coverage`, ale renderuje z niej wyłącznie
  ostrzeżenie o lukach, gdy `coverage.ranges.length > 1` — usuń zakres „Covered from … to …",
  informację o końcu historii u providera, stan „Reading coverage…" i napis
  „Nothing verified yet for this interval"; gdy `ranges.length <= 1`, rozwinięcie nie pokazuje nic
  o pokryciu
- [x] 3.2 Usuń z rozwinięcia etykietę stanu zbierania (`COLLECTION_LABEL`) i wiersz `newest: …`
- [x] 3.3 W rozwinięciu pokaż dla każdego interwału: liczbę świec, objętość przez `formatBytes`
  i moment początku danych; interwał bez świec MUST być nazwany wprost, a nie pokazany jako `0`
- [x] 3.4 Zostaw przycisk `Delete` per interwał wraz z jego dialogiem — bez zmian
- [x] 3.5 Usuń kolumnę `Data since` z tabeli: nagłówek, `DataSinceCell`, `DataSinceOf`, pole
  `dataSince` z `InstrumentGroup`. `earliestData` dla dialogu skasowania całego instrumentu policz
  wprost z `group.pairs`
- [x] 3.6 Gdy odczyt listy par zawodzi, rozwinięcie mówi, że objętość jest nieznana — zero
  MUST NOT być odpowiedzią na brak odpowiedzi
- [x] 3.7 `InstrumentsView.test.tsx`: usuń test „shows coverage for every resolution" (pełny zakres
  już się nie pokazuje) i test o `newest:`; zostaw i dostosuj test „names the gaps when coverage
  is more than one stretch" do nowego, węższego napisu bez zakresu dat; dopisz test, że pokrycie
  ciągłe (`ranges.length === 1`) nie pokazuje nic, oraz testy na liczbę świec, objętość, interwał
  bez danych i moment początku przy interwale

## 4. Wykres: mniej napisów

- [x] 4.1 Usuń znacznik `forming` z nagłówka `Chart.tsx` wraz z `lastIsForming`; `Bar.forming`
  i `latestBar` zostają — pierwsze niesie dane, drugie rysuje linię ceny
- [x] 4.2 Usuń wolumen z `OhlcReadout` (pole `V` i jego `title`); `Bar.volume` w typach zostaje
- [x] 4.3 Zrównaj pola wyboru w nagłówku: `SymbolField` dostaje `text-xs` zamiast
  `text-sm font-semibold`, tak jak pole interwału
- [x] 4.4 `Chart.test.tsx`: usuń asercje na `forming` i na wolumen, dopisz asercję, że wolumen
  nie jest pokazywany nawet gdy świeca go niesie

## 5. Nazwy interwałów w jednym miejscu

- [x] 5.1 Przenieś `RESOLUTION_ABBR` do `src/ui/resolutionLabel.ts` z wartościami `m1`, `m5`,
  `m15`, `m30`, `h1`, `h4`, `day`, `week`
- [x] 5.2 Pole wyboru interwału w `Chart.tsx` renderuje etykietę zamiast surowego `MINUTE_5`
- [x] 5.3 Przełącz na nowy plik `InstrumentsView.tsx`, `AddInstrumentWizard.tsx`
  i `CollectionHistoryView.tsx`; usuń `src/instruments/resolutionAbbr.ts`
- [x] 5.4 `grep -rn "MINUTE_\|HOUR_" src --include=*.tsx` nie pokazuje niczego, co trafia na ekran
  (znaleziony jest tylko komentarz w kodzie w `GridView.tsx`; dodatkowo zaktualizowano
  `GridView.tsx` — nagłówek slotu wygasłego i przyciski `stillArchivedAt` — oraz FeedOverlay
  w `Chart.tsx`, które grep dla `RESOLUTION_ABBR` nie znalazł, bo renderowały gołe `resolution`)

## 6. Polska strefa czasowa

- [x] 6.1 `src/ui/formatTime.ts`: `formatInstant` na `Intl.DateTimeFormat` z
  `timeZone: "Europe/Warsaw"`, `timeZoneName: "short"` i jawnymi polami daty (`dateStyle`
  **nie łączy się** z `timeZoneName`); przenieś tam też `formatBytes` i usuń
  `src/instruments/format.ts`
- [x] 6.2 Testy `formatTime`: ta sama chwila latem daje `CEST`, zimą `CET`, a wynik nie zależy od
  `TZ` procesu
- [x] 6.3 `Chart.tsx`: czas świecy w `OhlcReadout` przez `formatInstant` zamiast `toISOString()`
- [x] 6.4 `Chart.tsx`: `localization.timeFormatter` i `timeScale.tickMarkFormatter` karmione
  formaterami z `formatTime.ts` (`formatCrosshairTime`, `formatTickMark`); znaczniki `bar.time`
  MUST NOT są przesuwane — pozostają nietknięte, zmienia się tylko etykieta
- [x] 6.5 `AddInstrumentWizard.tsx`: `todayInWarsaw()` zamiast `todayDateInput()`/UTC dla `max`
  i dla domyślnego roku, `warsawMidnightEpochSeconds()` zamiast `dateInputToEpochSeconds()` —
  wybrany dzień znaczy północ warszawską
- [x] 6.6 Zaktualizuj asercje w testach, które trzymają napisy z `UTC`

## 7. Zakładki

- [x] 7.1 Usuń wpisy `positions`, `orders`, `account` z `TABS`
- [x] 7.2 Usuń `TabStatus`, `ComingSoonTab` i pole `status`; `TabDefinition` zostaje jednym
  kształtem z `Component`
- [x] 7.3 Usuń `src/app/ComingSoon.tsx` i rozgałęzienie w `App.tsx`
- [x] 7.4 `App.test.tsx`: test klikający `Account` zastąp testem, że `/account` trafia na stronę
  nieznanej zakładki

## 8. Domknięcie

- [x] 8.1 `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm contract:check` w `modules/terminal`
  (+ `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright` w
  `market-data`) — czysto poza dwiema znanymi, sprzed tego changea usterkami środowiska
  (locale maszyny, `WinError 10106`), opisanymi w `review.md`
- [x] 8.2 `./scripts/dev.ps1` i przejście po zakładkach: rozwinięcie instrumentu, wykres, historia
  dociągania — daty polskie, nazwy interwałów jednakowe. Wykonane przez operatora na Windows;
  przy okazji naprawione trzy rzeczy w samych skryptach — patrz `review.md`, „Znalezione przy
  uruchamianiu stacku"
- [x] 8.3 `openspec validate tidy-terminal-display --strict`
- [x] 8.4 `review.md` — bez niego archiwizacja nie przejdzie przez hook
