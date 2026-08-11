## Verdict

Wdrożone: `market-data` liczy 63 wskaźniki z własnego jądra na `numpy`, publikuje je jako
katalog (`GET /indicators`) i liczy na żądanie (`POST /indicators/{symbol}`) w czterech
kształtach wyjścia — `lines`, `markers`, `zones`, `levels`. Rozgrzewka jest progiem tłumienia
wyliczanym per rodzina, serwer sam rozszerza okno odczytu wstecz i mówi w odpowiedzi, dokąd
sięgnął (`warmup_from`, `settled`). Terminal buduje wybierak wyłącznie z katalogu, rysuje
nakładki, osobne panele oscylatorów, markery, promienie, strefy i histogram profilu, zapisuje
zestaw per slot siatki i dopytuje o ogon serii dopiero po zamknięciu świecy. Etapy 1–6 zamknięte,
grupa 7 domknięta poza 7.4 i 7.6.

Świadomie niedokończone: **7.4** — ręczny przebieg całego stosu należy do operatora; scenariusze
przygotowane w `docs/wskazniki-testy-lokalne.html` i to one, a nie ten plik, są zapisem tego
przebiegu. **7.6** — pull request po 7.4.

Ta sesja była przeglądem domknięcia 7.1–7.3 i znalazła pięć rzeczy, z których cztery były błędami
poza zakresem samej zmiany, a jedna — brak `tzdata` — jest błędem produkcyjnym tej zmiany. Wszystkie
naprawione, szczegóły w Findings.

## Verified

- `cd modules/market-data && uv run pytest -q` → `993 passed, 7 skipped`
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `cd modules/market-data && uv run pyright` → `0 errors, 0 warnings, 0 informations`
- `cd modules/terminal && pnpm test` → `373 passed` (25 plików)
- `cd modules/terminal && pnpm lint` → czysto
- `cd modules/terminal && pnpm typecheck` → czysto
- `cd modules/terminal && pnpm contract:check` → `Contract is up to date.`
- `openspec validate add-technical-indicators --strict` → `Change 'add-technical-indicators' is valid`

Wszystko na Windows 11, z Dockerem — testy `db` weszły same, nie zostały pominięte. Testy `live`
poza przebiegiem, zgodnie z regułą.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **High** | `modules/market-data/pyproject.toml` | Brak zależności `tzdata`. `catalogue/zones.py` (wtedy jeszcze `catalogue.py:1758`) woła `ZoneInfo(tz_name)` **w czasie importu modułu**, budując wpisy `session_range_*`. `zoneinfo` czyta bazę stref systemu operacyjnego i sięga po pakiet `tzdata` dopiero, gdy jej nie ma — a nie ma jej ani na Windows (nigdy jej nie ma), ani w `python:3.12-slim-bookworm`, czyli w obrazie z `Dockerfile`. Skutek nie jest nieudanym żądaniem, tylko modułem, który się nie importuje: `zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key Europe/London'`. Lokalnie wywracało to zbiórkę wszystkich 10 plików testowych; na wdrożeniu wywróciłoby start kontenera. Naprawione: `tzdata>=2024.1` w `[project.dependencies]` (nie w `dev` — potrzebuje jej runtime), `uv lock`. | fixed |
| **Medium** | `.gitattributes` (nie istniał) | `pnpm contract:check` porównuje `src/data/contract.generated.ts` bajt w bajt z generacją. Generator pisze LF, a `core.autocrlf=true` — domyślne na Windows — wydaje przy checkoutcie CRLF. Na czystym klonie check raportuje nieaktualny kontrakt na maszynie, na której nic nie jest nieaktualne; `git diff` przy tym milczy, bo normalizuje. Naprawione: `.gitattributes` przypinający ten jeden plik do `eol=lf`. | fixed |
| **Medium** | `modules/market-data/tests/test_ingest.py:993` | `test_the_supervisor_reports_what_each_fill_did` przestał przechodzić 11 sierpnia. Świece fixture'u stoją względem stałego `NOW = 2026-08-07 12:00`, a `track()` bez jawnego `collect_from` wylicza podłogę z **realnego** zegara (`now − 5000 minut`). Gdy zegar ścienny minął `NOW + 5000 minut`, podłoga przeszła nad fixture'ami i `backfill.py:184` odfiltrował całą partię — `written == 0` zamiast `4`. Test z terminem ważności jest gorszy niż test, który nie przechodzi, bo psuje się bez związku ze zmianą, która akurat trwa. Naprawione: jawny `collect_from=NOW - 1h`. Poza zakresem tej zmiany (`ingest/` nietknięte na tej gałęzi). | fixed |
| **Medium** | `modules/terminal/src/test/setup.ts` | Cztery testy w `CollectionHistoryView`, `AddInstrumentWizard` i `InstrumentsView` nie przechodziły lokalnie i przechodziły w CI. `toLocaleString()` bez argumentu bierze locale z systemu, a Node na Windows ignoruje `LANG` i `LC_ALL` — na polskiej maszynie `12431` to `12 431` (twarda spacja), a asercje pinują `12,431`. Widoki idą za locale operatora celowo, więc naprawione po stronie testów: domyślne locale przypięte do `en-US` w setupie, nie w komponentach. Poza zakresem tej zmiany. | fixed |
| **Low** | `modules/market-data/tests/test_openapi.py:115` | `test_the_document_prints_with_no_environment_at_all` uruchamia podproces z `env={"PATH": "/usr/bin:/bin"}`. Na Windows brak `SystemRoot` zabija inicjalizację winsocka w `import _overlapped` (`WinError 10106`), którego pętla proactora asyncio wciąga przy imporcie aplikacji — test padał z powodu, którego nie testuje. Naprawione: `SystemRoot` przenoszony tylko na Windows, z komentarzem, że to nie jest jedna ze zmiennych pod testem. Poza zakresem tej zmiany. | fixed |
| **Low** | `market_data/contract.py`, `market_data/routers/indicators.py` | Polskie słowa w opisach publikowanych na drucie: `description=` pól kontraktu i `summary`/`description` obu tras jechały do dokumentu OpenAPI, a stamtąd do `contract.generated.ts` — czyli do dokumentacji, którą czyta każdy konsument. `CLAUDE.md` mówi jasno: polski jest w artefaktach OpenSpec, angielski w kodzie. Naprawione (12 miejsc) i kontrakt przegenerowany. | fixed |
| **Low** | `modules/market-data/README.md` | To samo w sekcji dodanej w 7.1 — siedem wystąpień „wskaźnik/wskaźniki" w angielskiej prozie README modułu. Naprawione. | fixed |
| **Low** | `openspec/changes/add-technical-indicators/design.md` | Nagłówek `## Decisions rozstrzygnięte w etapie strefy/profilu/na żywo` łamał konwencję (proza polska, **struktura** angielska) i stawiał drugą sekcję „Decisions" po `## Open Questions`, przez co dwie rozstrzygnięte decyzje czytały się jak podsekcje pytań otwartych. Naprawione: nagłówek zdjęty, oba `###` wpięte na koniec istniejącego `## Decisions`, przed `## Risks / Trade-offs`. | fixed |
| **Low** | `CLAUDE.md` | „The whole stack: `./scripts/dev.sh`" — a podstawową platformą deweloperską tego repozytorium jest Windows i istnieje `scripts/dev.ps1` z własną flagą `-NoTerminal`. Naprawione: obie ścieżki wymienione. | fixed |
| **Low** | kod i testy, 23 pliki | Ten sam wyciek języka co wyżej, ale w komentarzach, docstringach i **nazwach testów** (`catalogue.py`, `kernel.py`, `Chart.tsx`, `Chart.test.tsx`, `types.ts` i dalej). Nazwy testów są w tym gorsze od komentarzy, bo wychodzą w wyniku `pnpm test`. Naprawione osobnym commitem: 106 wystąpień rodziny „wskaźnik" plus dziewięć polskich banerów sekcji i jeden blok komentarza w całości po polsku (`catalogue.py`, „poziomy z wyższego interwału"). **Cytaty zostają polskie** — tytuły wymagań ze specyfikacji („Wskaźnik liczy się z jednej serii świec"), nazwy sekcji `docs/wskazniki-plan-wdrozenia.html` i cytaty z `design.md` są cytatem z polskiego dokumentu, nie prozą do przetłumaczenia. Po zamiataniu zostały 2 miejsca z polskim poza cudzysłowem i oba to też cytaty (jedno w backtickach). | fixed |

## Deviations from design.md

- **Opóźnienie dopytywania nie zostało zmierzone.** `design.md` w pierwotnej wersji obiecywał wybór
  między dopytaniem po zamknięciu świecy a subskrypcją wskaźników „po zmierzeniu opóźnienia na
  działającym stosie". Pomiaru nie było — nie było działającego stosu w trakcie zmiany. Wybrano
  dopytanie, na podstawie brzmienia zadania 6.1 i tego, że jest to prostsza z dwóch dróg mieszczących
  się w tym samym kontrakcie. Zapisane wprost w `design.md`; przejście na subskrypcję nie rusza
  kontraktu. To jest jedyne miejsce, w którym ta zmiana obiecała pomiar i go nie dostarczyła.
- **Szerokość kubełka profilu rozstrzygnięta bez pomiaru porównawczego.** `design.md` zapowiadał
  rozstrzygnięcie „na danych" między ułamkiem ATR a wielokrotnością kroku instrumentu. Wybrano ułamek
  ATR argumentem konstrukcyjnym, nie pomiarem: moduł nie ma tabeli kroków per instrument (`Candle` nie
  niesie tego pola), więc druga droga wymagałaby osobnej zmiany kontraktu. Rozstrzygnięcie zapisane.
- **Zadanie 1.20 rozszerzone poza pierwotny podział.** Odczyt wartości wskaźnika pod kursorem obok
  OHLC wszedł już w E0, a nie dopiero w 2.15 — odnotowane w `tasks.md` przy samym zadaniu.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-indicators: Wskaźnik jest czystą funkcją świec** | |
| Dwa identyczne odczyty · Odczyt po restarcie modułu | `tests/test_indicators_kernel.py::TestDeterminism`, `TestGoldenFile` (pliki wzorcowe `sma`/`ema`/`atr`), `tests/test_indicators_catalogue.py::TestCatalogueGoldenFile::test_default_params_match_the_committed_snapshot` |
| **market-data-indicators: Rozgrzewka jest wyliczona, jawna i niezależna od punktu startu** | |
| Ten sam okres w dwóch różnych zakresach | `tests/test_indicators_catalogue.py::TestStartIndependence::test_tail_matches_regardless_of_where_the_read_started` (parametryzowany po **wszystkich** wpisach z tłumieniem) |
| Archiwum płytsze niż rozgrzewka | `tests/test_indicators_router.py::test_reads_further_back_than_from_for_warmup`; `settled` w odpowiedzi |
| Okresy przed rozgrzewką | `tests/test_indicators_kernel.py::TestWarmupNaN` |
| **market-data-indicators: Katalog wystarcza do zbudowania wybieraka** | |
| Konsument buduje listę | `tests/test_indicators_router.py::test_catalogue_lists_entries_with_everything_a_picker_needs`; po stronie terminala `Chart.test.tsx` „Chart — wskaźniki" |
| Wyszukiwanie po nazwie potocznej | `aliases` w `IndicatorCatalogueEntryOut`; `range_gap` niesie „Fair Value Gap" jako alias |
| Nowy wskaźnik w istniejącym kształcie | `tests/test_indicators_catalogue.py::TestCatalogueMatchesKernel` — każdy wpis liczony, klucze wyjścia równe deklarowanym |
| **market-data-indicators: Katalog mierzy, a nie orzeka** | |
| Miara zamiast rozstrzygnięcia · Próg podany w żądaniu | `tests/test_indicators_catalogue.py::TestCatalogueBoundary::test_no_param_is_boolean`, `::test_output_values_are_not_boolean`; `params` powtórzone w `IndicatorResultOut` |
| **market-data-indicators: Wskaźnik liczy się z jednej serii świec** | |
| Katalog bez wolumenu · Świeca z wolumenem od źródła | `TestCatalogueBoundary::test_no_entry_reads_volume`, `::test_no_entry_takes_a_second_instrument`, `tests/test_indicators_router.py::test_catalogue_carries_no_volume_entry` |
| **market-data-indicators: Jedno żądanie liczy wiele wskaźników na wspólnej osi czasu** | |
| Kilka wskaźników naraz · Ten sam wskaźnik z różnymi parametrami | `tests/test_indicators_router.py::test_computes_a_line_indicator_over_the_requested_range` (wspólne `times`), `::test_the_response_names_its_side_and_algorithm_version` |
| **market-data-indicators: Wynik ma jeden z czterech kształtów** | |
| Strefa wciąż otwarta | `tests/test_indicators_zones.py::TestSessionRange::test_window_still_forming_stays_open`, `TestRangeGap::test_touched_without_being_filled_stays_open` |
| Kształt zapowiedziany w katalogu | walidator `IndicatorResultOut._exactly_one_shape`; `test_indicators_router.py::test_swing_points_are_returned_as_markers`, `::test_level_clusters_are_returned_with_a_count`, `::test_range_gap_is_returned_with_direction_and_bounds` |
| **market-data-indicators: Odpowiedź niesie to, czego archiwum nie pokrywa** | |
| Zakres z niepokrytym odcinkiem · Seria pochodna | `tests/test_indicators_router.py::test_uncovered_stretch_is_carried_into_the_response`, `::test_the_response_names_its_side_and_algorithm_version` (`derived`, `price_side`) |
| **market-data-indicators: Obliczenie obejmuje wyłącznie świece zamknięte** | |
| Bieżący okres | archiwum nie przechowuje świecy w budowie (`store.write_candles` odrzuca `forming`); po stronie terminala `Chart.test.tsx` „requeries once a candle closes" |
| **market-data-indicators: Zbyt duże żądanie zostaje odrzucone** | |
| Żądanie ponad sufit · Zakres odwrócony | `tests/test_indicators_router.py::test_request_above_the_ceiling_is_refused`, `::test_a_range_that_ends_before_it_starts_is_refused`, `::test_a_wide_request_hiding_a_bigger_minute_read_is_refused` |
| **market-data-indicators: Zmiana wzoru jest widoczna w odpowiedzi** | |
| Porównanie dwóch odpowiedzi | `algorithm_version` w `IndicatorsOut`; `TestCatalogueGoldenFile` zamienia cichą zmianę wzoru w diff w tym samym commicie |
| **market-data-indicators: Punkt zwrotny potwierdza się z opóźnieniem i już się nie zmienia** | |
| Świeży skrajny punkt · Powtórny odczyt | `tests/test_indicators_structure.py::TestSwingPoints::test_too_short_a_series_confirms_nothing`, `::test_stays_the_same_on_a_longer_read`, `TestLastSwing::test_steps_at_confirmation_not_at_the_extreme` |
| **market-data-indicators: Poziomy z wyższego interwału pochodzą z zamkniętego okresu** | |
| Poziomy poprzedniego dnia na wykresie minutowym · Brak serii | `tests/test_indicators_router.py::test_htf_levels_day_reads_the_previous_closed_day`, `::test_htf_levels_refused_without_the_day_series` |
| **market-data-indicators: Przerwa w handlu nie jest luką cenową** | |
| Weekend · Luka wewnątrz sesji | `tests/test_indicators_zones.py::TestRangeGap::test_skip_session_gaps_suppresses_a_gap_spanning_a_market_close`, `tests/test_indicators_router.py::test_friday_to_sunday_gap_is_not_reported_as_a_price_gap`, `TestRangeGap::test_bullish_gap_between_bar_before_and_bar_after` |
| **market-data-indicators: Okno sesji liczy się w zadanej strefie czasowej** | |
| Okno po zmianie czasu | `tests/test_indicators_zones.py::TestSessionRange::test_recognises_the_same_local_hours_across_a_dst_change`, `::test_two_consecutive_days_never_merge_into_one_zone` |
| **market-data-indicators: Profil czasowy liczy się z serii minutowej** | |
| Profil pod wykresem czterogodzinnym · Para bez serii minutowej | `tests/test_indicators_router.py::test_time_profile_computes_from_the_minute_series_at_day_resolution`, `::test_time_profile_refused_without_a_minute_series`, `tests/test_indicators_profile.py::TestTimeProfile::test_point_of_control_matches_a_hand_recount` |
| **terminal-chart: Operator wybiera wskaźniki z tego, co oferuje źródło** | |
| Lista pochodzi ze źródła · Wskaźnik dołożony po stronie źródła · Parametr poza zakresem | `Chart.test.tsx` „Chart — wskaźniki": `offers no picker at all without an indicator source`, `makes an own-pane wskaźnik … selectable`, `keeps an own-pane markers/levels/zones wskaźnik unselectable`; walidacja parametru w `IndicatorPicker.tsx` |
| **terminal-chart: Wskaźnik rysuje się tam, gdzie należy** | |
| Nakładka i oscylator · Wspólna oś czasu · Nakładka poza skalą ceny | `draws an own-pane wskaźnik in a pane of its own`, `deselecting one of two own-pane wskaźniki leaves the other's pane intact`, `draws the catalogue's reference levels (RSI's 30/70)` |
| **terminal-chart: Wskaźnik bez wartości nie jest rysowany jako zero** | |
| Okres przed rozgrzewką · Za płytka historia | `says when a value is not settled yet, without hiding it` |
| **terminal-chart: Wykres podaje wartości wskaźników spod kursora** | |
| Kursor nad świecą · Kursor poza serią | `shows an own-pane wskaźnik's value under the cursor beside OHLC` |
| **terminal-chart: Strefy i poziomy rysują się jako obszary, nie jako linie serii** | |
| Strefa otwarta · Poziom z wyższego interwału · Wiele stref naraz | `ZonePrimitive.test.ts` (w tym ograniczenie kosztu klatki widocznym zakresem), `RayPrimitive.test.ts`, `TimeProfilePrimitive.test.ts`, `Chart.test.tsx` „zones / zone primitive", „levels / ray primitive", „time profile / histogram primitive" |
| **terminal-chart: Wskaźniki znikają razem z serią, której dotyczą** | |
| Zmiana rozdzielczości · Wybór wskaźników po zmianie symbolu | `clears a non-lines primitive (a zone) on a symbol change too, not just wskaźnik lines` |
| **terminal-chart: Wykres mówi, gdy wskaźników nie da się policzyć** | |
| Odczyt wskaźników zawiódł · Odmowa z powodu sufitu | plakietka `indicators unavailable` + `Retry` w `Chart.tsx`; `useIndicators.ts` |
| **terminal-grid: Slot ma własny instrument i własny interwał** | |
| Różne wskaźniki w dwóch slotach · Powrót z zapisanymi wskaźnikami · Zapamiętany wskaźnik zniknął z katalogu | `GridView.test.tsx`, `gridStore.test.ts`; plakietka `N saved indicators unavailable` w `Chart.tsx` |

## Gaps

- **7.4 nie jest przejściem, tylko planem.** `docs/wskazniki-testy-lokalne.html` opisuje 24 scenariusze
  (20 na ekranie, 4 na samym module) — nikt ich jeszcze nie wykonał. Do zrobienia przed 7.6.
- **`session_range_*` to okno zegarowe, nie kalendarz sesji.** Godziny są parametrem, strefa czasowa
  jest wpisana w `id`. Instrument handlowany w innych godzinach dostanie okno, o które poprosił —
  moduł nie wie, i nie udaje, że wie, kiedy naprawdę handluje się danym instrumentem.
- **`time_profile` liczy udział czasu, nie wolumenu**, i każda świeca minutowa zasila dokładnie jeden
  kubełek wybrany po cenie typowej `(H+L+C)/3` — nie rozbija własnego zakresu H–L na wiele kubełków,
  jak robi to typowy TPO. Prostsze i ręcznie sprawdzalne (5.5), ale to jest inny odczyt niż ten,
  którego ktoś znający TPO z platformy może się spodziewać.
- **Wskaźniki zależne od stanu i wysunięte w przyszłość zostają poza systemem** — Parabolic SAR,
  SuperTrend, ZigZag, Renko, Kagi, Ichimoku, Alligator. Świadomie, z powodem zapisanym w `design.md`;
  wracają dopiero, gdy pojawi się kalendarz sesji i osobna kategoria kotwiczonych wyników.
