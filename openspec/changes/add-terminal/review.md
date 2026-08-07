## Verdict

Terminal działa przeciw żywemu `capital-gateway`: powłoka z rejestrem zakładek, reużywalny wykres
świecowy, siatka slotów z presetami i trwałością, wyszukiwarka instrumentów. Wszystko, co spec
obiecuje, jest zaimplementowane; pięć błędów wyszło dopiero z uruchomienia w przeglądarce i
zostało naprawionych przed tym przeglądem.

Świadomie niekompletne: **przeglądarkowe zachowania, których jsdom nie oddaje** — dopasowanie
rozmiaru przez `ResizeObserver` i odczyt spod kursora nie mają testów jednostkowych i były
sprawdzane ręcznie. Świadomie wycofane: **źródło mock** (zadania 3.6 i 3.8) — zbudowane, a potem
usunięte na życzenie; `MarketDataSource` został jako szew pod bazę świec, nie jako wybór w UI.

Czego czytelnik za rok nie powinien wziąć za przeoczenie: interfejs z jedną implementacją to nie
nadmiarowa abstrakcja, tylko miejsce wejścia dla bazy świec — i jedyna rzecz, która sprawia, że
`terminal-market-data` da się spełnić bez przepisywania wykresu.

## Verified

Uruchomione w `modules/terminal`, na commicie `8a069b4`:

| Komenda | Wynik |
|---|---|
| `pnpm typecheck` (`tsc -b --noEmit`) | czysto, bez wyjścia |
| `pnpm lint` (`eslint .`) | czysto, zero ostrzeżeń |
| `pnpm test` (`vitest run`) | **100 passed**, 10 plików, 6,3 s |
| `pnpm build` (`tsc -b && vite build`) | `dist/` 408,75 kB (gzip 130,80 kB), 1,56 s |

Poza tym, przeciw **realnemu gatewayowi na koncie demo**, przez `scripts/dev.ps1` i sterowaną
przeglądarkę (Chromium, playwright-core):

- Siatka `2x2` i `3x2` rysują realne świece — US100 ~29 620, GOLD ~4 338, BTCUSD ~64 885,
  EURUSD ~1,156, SILVER ~63,28, UK100 ~10 892. Zero błędów w konsoli.
- `GET /instruments/US100/history?resolution=MINUTE_5&bars=3` → `"ts":"2026-08-07T16:20:00Z"`.
  Strefa czasowa potwierdzona na żywej odpowiedzi, nie wyczytana z kodu (zadanie 2.5).
- Świeca w budowie rusza wykresem: OHLC ostatniej świecy US100 zmieniło się w ciągu 45 s bez
  świecy zamkniętej po drodze.
- Sześć różnych par w `3x2` → **sześć gniazd jednocześnie, szczyt sześć**. Zejście na `2x2`
  zamyka gniazda zniknionych slotów.
- Po naprawie odczytu w nagłówku: sześć różnych odczytów próbkowanych co 5 s przez 30 s wewnątrz
  jednej świecy — otwarcie stałe, maksimum i minimum rozszerzają się, zamknięcie się rusza.

## Findings

Pass 1 — przegląd dwunastu commitów od punktu odgałęzienia. Wszystkie poniższe były znalezione i
naprawione w trakcie; żadne nie zostaje otwarte.

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `src/chart/Chart.tsx:203` (przed naprawą) | Odczyt OHLC w nagłówku czytał `barsRef` w trakcie renderu. Dopóki świeca się formuje, żaden inny stan komponentu się nie zmienia, więc React nie miał powodu przerysować — nagłówek zamarzał na wartościach z otwarcia świecy, podczas gdy canvas dalej się ruszał. Widoczne na każdym zrzucie jako `O=H=L=C`. Operator czytał cenę sprzed minut jako bieżącą. | **FIXED** `8a069b4` |
| High | `src/chart/Chart.tsx:199` (przed naprawą) | Przełączenie źródła nie czyściło serii. Świece poprzedniego źródła zostawały na ekranie pod etykietą nowego przez czas głębokiego odczytu — nie nieaktualny wykres, tylko zły. | **FIXED** `532d373` |
| Medium | `src/chart/Chart.tsx:183` (przed naprawą) | `applyHistory` robiło `setData` zamiast scalać. Subskrypcja startuje przed odczytem, więc świeca w budowie normalnie przychodzi pierwsza — i znikała aż do następnego ticku, co przy `DAY` oznacza godziny. | **FIXED** `8257bf0` |
| Medium | `src/data/config.ts:54` (przed naprawą) | `resolveGatewayEndpoints` rzucało `TypeError` przy nieustawionych zmiennych środowiskowych zamiast wpaść w `/api` + `/ws`. Świeży klon bez `.env` wywracał budowę źródła. | **FIXED** `28e0ee8` |
| Medium | `scripts/dev.ps1` (przed naprawą) | Health check pytał `localhost`, a uvicorn słucha na `127.0.0.1`; na Windows `localhost` bywa rozwiązywane najpierw na `::1`. Do tego terminal startował równolegle z gatewayem i walił w proxy, zanim tamten odpowiedział — ściana `ECONNREFUSED`. Skrypt nie pokazywał nic przez czas oczekiwania, więc wyglądał na zawieszony. | **FIXED** `bb7df44` |
| Low | `src/data/types.ts`, `src/data/socketHub.ts` | Martwy kod po usunięciu mocka: `FIXED_RESOLUTION_SECONDS` bez konsumenta i `HubEntry.refused` zapisywane, nigdy nieczytane. | **FIXED** `8a069b4` |
| Low | `modules/terminal/index.html` | Brak favikony — 404 w konsoli przy każdym załadowaniu. | **FIXED** `f98bf5b` |

Świadomie zostawione, z uzasadnieniem:

- `socketHub.ts:202` — dociąganie luki bierze sztywne 50 świec zamiast liczyć długość przerwy.
  Świece scalają się po znaczniku czasu, więc nadmiar jest nieszkodliwy, a niedomiar zasypie
  następna świeca zamknięta. Liczenie okresu wymagałoby tablicy długości okresów, której ten moduł
  celowo nie ma (`DAY` nie ma stałej długości).
- `gatewaySource.ts:123` — `fetchRecent` tworzy `AbortController`, którego nigdy nie przerywa.
  Wywoływane wyłącznie z huba po wznowieniu; żądanie i tak jest krótkie.

## Spec coverage

Pass 2 — każdy wymóg i scenariusz z `specs/**/*.md` tej zmiany.

### terminal-shell

| Requirement / Scenario | Proven by |
|---|---|
| Zakładki są adresowalne / Przejście między zakładkami | `src/App.test.tsx::switching tabs updates both the content and the address` |
| … / Odświeżenie strony | `src/App.test.tsx::loading an address directly shows that tab, not the default` |
| … / Nieznany adres | `src/App.test.tsx::shows a way back to the default tab for an unknown address` |
| Rejestr zakładek jest otwarty / Dołożenie zakładki | **GAP** — strukturalne (routing i pasek wyprowadzane z `TABS`), bez testu |
| … / Zakładka jeszcze niezaimplementowana | `src/App.test.tsx::shows an explicit placeholder for a not-yet-implemented tab, other tabs unaffected` |
| Motyw jest ciemny i wyprowadzony z tokenów / Zmiana wartości tokenu | **GAP** — bez testu; `chart/theme.ts` czyta te same CSS variables co Tailwind, sprawdzone wzrokowo |
| Stan źródła danych jest widoczny globalnie / Źródło odpowiada | `src/App.test.tsx::names the source and reports it reachable once it answers` |
| … / Źródło nie odpowiada | **GAP** w powłoce; gałąź danych pokryta `src/data/gatewaySource.test.ts::rejects with unreachable when the gateway can't be reached` |
| … / Awaria pojedynczego widoku | **GAP** — `ViewErrorBoundary` bez testu |

### terminal-market-data

| Requirement / Scenario | Proven by |
|---|---|
| Źródło wymienne za jednym interfejsem / Dołożenie kolejnego źródła | **GAP** — strukturalne; każdy widok zależy od `MarketDataSource`, nie od implementacji |
| … / Jedna instancja na całą aplikację | **GAP** — strukturalne (`marketData.ts` to jedna instancja modułu); skutek zmierzony w przeglądarce (6 gniazd na 6 par) |
| Znaczniki czasu sprowadzone do jednej postaci / Historia styka się ze strumieniem | `src/data/time.test.ts::parses a UTC-marked gateway timestamp to the correct epoch second`, `src/data/gatewaySource.test.ts::converts ISO timestamps to epoch seconds and marks bars settled`, `src/chart/Chart.test.tsx::updates the last candle in place rather than appending a second one` |
| … / Świeca ze strumienia wyprzedza historię | `src/data/merge.test.ts::appends when a new period opens`, `src/chart/Chart.test.tsx::appends when a new period opens` |
| Jedno połączenie na parę / Dwa sloty na tę samą parę | `src/data/socketHub.test.ts::shares one socket between subscribers to the same pair`, `src/grid/GridView.test.tsx::shares one connection between two slots on the same pair, and frees it with the last` |
| … / Ostatni odbiorca odchodzi | `src/data/socketHub.test.ts::closes the socket only once the last subscriber leaves` |
| … / Sześć różnych par naraz | `src/grid/GridView.test.tsx::opens at most one connection per pair for a full 3x2 of distinct pairs` |
| Zerwane połączenie wraca samo / Połączenie pada | `src/data/socketHub.test.ts::reconnects on an unexpected drop with growing backoff, and reopens the socket` |
| … / Połączenie wraca | `src/data/socketHub.test.ts::backfills the gap from fetchRecent once a reconnect succeeds` |
| Świeca w budowie oznaczona jako niepewna / Świeca się zamyka | `src/data/merge.test.ts::closes a forming candle by replacing it with the settled one` |
| Zapytanie nazywa swoją porażkę / Nieznany symbol | `src/data/gatewaySource.test.ts::maps a 404 to a not-found MarketDataError naming the symbol` |
| … / Źródło nieosiągalne | `src/data/gatewaySource.test.ts::maps a network failure to unreachable, not a raw fetch error` |

### terminal-chart

| Requirement / Scenario | Proven by |
|---|---|
| Wykres sterowany symbolem i rozdzielczością / Ten sam komponent w dwóch miejscach | **GAP** — strukturalne; ten sam `Chart` renderowany solo (`Chart.test.tsx`) i w slocie (`GridView.test.tsx`), bez testu porównującego |
| … / Zmiana symbolu | `src/chart/Chart.test.tsx::re-subscribes to the new symbol and drops the old subscription` |
| Rozdzielczość zmienia się bez przeładowania / Wybór innego interwału | częściowo: `src/chart/Chart.test.tsx::a late response from a superseded resolution never reaches the chart` (dowodzi ponownego odczytu), `src/grid/GridView.test.tsx::changes one slot's resolution without disturbing the others`. **Przepięcie subskrypcji na nową rozdzielczość nie jest asertowane** — jest dla symbolu |
| … / Szybka zmiana kilku rozdzielczości pod rząd | `src/chart/Chart.test.tsx::a late response from a superseded resolution never reaches the chart` |
| Świeca na żywo dokłada się do historii / Ruch wewnątrz bieżącej świecy | `src/chart/Chart.test.tsx::updates the last candle in place rather than appending a second one` |
| … / Otwarcie nowego okresu | `src/chart/Chart.test.tsx::appends when a new period opens` |
| Świeca w budowie oznaczona na ekranie / Ostatnia świeca jeszcze się nie zamknęła | `src/chart/Chart.test.tsx::flags a forming candle and drops the flag once it settles` |
| … / Świeca się zamyka | ten sam test |
| Wykres mówi, w jakim jest stanie / Trwa zaciąganie historii | `src/chart/Chart.test.tsx::says it is loading before the history lands` |
| … / Odczyt się nie powiódł | `src/chart/Chart.test.tsx::names a failed read and retries it on demand` |
| … / Instrument nie ma świec | `src/chart/Chart.test.tsx::states an empty series rather than showing a blank pane` |
| … / Strumień zerwany | `src/chart/Chart.test.tsx::marks the data stale when the stream drops, instead of showing a frozen candle silently` |
| Wykres podaje wartości spod kursora / Kursor nad świecą | **GAP** — najechanie kursorem nietestowane (crosshair biblioteki jest zaślepiony). Świeżość odczytu pokryta `src/chart/Chart.test.tsx::follows the forming candle as it moves within one period` |
| … / Świeca bez wolumenu | `src/chart/Chart.test.tsx::shows a missing volume as unavailable, never as zero` |
| Wykres sprząta po sobie / Slot znika po zmianie układu | `src/chart/Chart.test.tsx::tears down the chart and the subscription on unmount`, `src/grid/GridView.test.tsx::shares one connection between two slots on the same pair, and frees it with the last` |
| … / Zmiana rozmiaru okna | **GAP** — `ResizeObserver` jest w jsdom zaślepiony; sprawdzone wyłącznie w przeglądarce |

### terminal-grid

| Requirement / Scenario | Proven by |
|---|---|
| Układ siatki wybiera operator / Wybór układu | `src/grid/GridView.test.tsx::renders exactly as many slots as the layout calls for` |
| … / Przejście na mniejszy układ | `src/grid/GridView.test.tsx::keeps a hidden slot's instrument when shrinking and re-expanding`, `src/grid/gridStore.test.ts::keeps hidden slots' configuration when shrinking the layout` |
| Slot ma własny instrument i interwał / Ten sam instrument w kilku interwałach | częściowo: `src/grid/GridView.test.tsx::changes one slot's resolution without disturbing the others` dowodzi niezależności slotów, ale nie ustawia tego samego symbolu w dwóch interwałach |
| … / Slot pusty | `src/grid/GridView.test.tsx::invites a choice in an empty slot instead of drawing an empty chart` |
| Konfiguracja przeżywa sesję / Powrót do terminala | `src/grid/GridView.test.tsx::persists layout and slots across a remount`, `src/grid/gridStore.test.ts::restores a previously saved config` |
| … / Zapisany stan jest nieczytelny | `src/grid/gridStore.test.ts::falls back to defaults on an unreadable saved config rather than refusing to start`, `::falls back to defaults on a structurally wrong saved config`, `::survives a storage that throws (private-mode Safari)`, `parseGridConfig::rejects %s` (7 przypadków) |
| … / Zapisany symbol jest nieznany źródłu | **GAP** — realizowane przez nakładkę błędu wykresu (`not-found` nazywa symbol), ale bez testu w kontekście siatki |
| Slot wskazuje, czego dotyczy / Zmiana instrumentu w slocie | `src/grid/GridView.test.tsx::changes one slot's instrument without disturbing the others` |
| … / Który slot jest aktywny | `src/grid/GridView.test.tsx::marks the slot the operator is acting on` |

### terminal-instruments

| Requirement / Scenario | Proven by |
|---|---|
| Instrumenty wyszukuje się po frazie / Wyszukiwanie po frazie | `src/instruments/InstrumentsView.test.tsx::shows symbol, name, class and tradeability for each hit` |
| … / Fraza bez wyników | `src/instruments/InstrumentsView.test.tsx::distinguishes no matches from a failed search` |
| … / Wyszukiwanie zawodzi | ten sam test |
| … / Pisanie w polu wyszukiwania | `src/instruments/InstrumentsView.test.tsx::does not issue a request per keystroke`, `::a slow answer to an earlier query never overwrites the current one` |
| Wynik trafia do slotu / Wstawienie instrumentu do slotu | `src/instruments/InstrumentsView.test.tsx::puts the chosen instrument in the active slot and shows the chart` |
| … / Instrument nie jest handlowalny | `src/instruments/InstrumentsView.test.tsx::charts a non-tradeable instrument, flagging that it cannot be traded` |
| Katalog mówi, gdy jest niepełny / Katalog ucięty | `src/instruments/InstrumentsView.test.tsx::warns when the catalogue came back truncated` |
| … / Katalog kompletny | `src/instruments/InstrumentsView.test.tsx::reports the count without a warning when complete` |

## Gaps

Dziewięć scenariuszy bez testu. Trzy grupy, różne powody i różna waga:

**Nietestowalne w jsdom — sprawdzone w przeglądarce, nie w suicie.**

- `terminal-chart` / Zmiana rozmiaru okna — `ResizeObserver` jest zaślepiony w `test/setup.ts`.
- `terminal-chart` / Kursor nad świecą — crosshair należy do zaślepionej biblioteki.

To jest cena decyzji „nie testujemy, jak wygląda wykres" z `design.md`. Zamknięcie ich wymaga
testu przeglądarkowego (Playwright), którego ten moduł nie ma; skrypty użyte do weryfikacji żyły
w katalogu tymczasowym i nie zostały w repo.

**Strukturalne — spełnione przez kształt kodu, nie przez asercję.**

- `terminal-shell` / Dołożenie zakładki — routing i pasek wyprowadzane z jednego `TABS`.
- `terminal-shell` / Zmiana wartości tokenu — jeden zestaw CSS variables dla UI i wykresu.
- `terminal-market-data` / Dołożenie kolejnego źródła oraz Jedna instancja na całą aplikację.
- `terminal-chart` / Ten sam komponent w dwóch miejscach.

Test dodałby tu niewiele ponad to, co wymusza typ — poza „Jedną instancją", której skutek został
zmierzony w przeglądarce (sześć gniazd na sześć par).

**Prawdziwe luki — dałoby się przetestować, nie zostało.**

- `terminal-shell` / Awaria pojedynczego widoku — `ViewErrorBoundary` nie ma żadnego testu, a jest
  klasowym komponentem z własnym stanem i resetem przez `key`. Najbardziej wart uzupełnienia.
- `terminal-shell` / Źródło nie odpowiada — gałąź `unreachable` wskaźnika w pasku górnym.
- `terminal-grid` / Zapisany symbol jest nieznany źródłu — izolacja błędu do jednego slotu.
- `terminal-chart` / Wybór innego interwału — przepięcie subskrypcji na nową **rozdzielczość**
  (dla symbolu jest asertowane, dla rozdzielczości nie).
