## Verdict

Wdrożone: `IndicatorResultOut` niesie `error`, a odpowiedź, w której część wskaźników się nie
policzyła, jest odpowiedzią (`200`), nie odmową. Granica biegnie po tym, czyj to problem —
brakująca seria wraca przy swoim wpisie, pomyłka wołającego dalej odmawia całości i dalej jest
`422`. Terminal rysuje policzone, nazywa nieudane po identyfikatorze w plakietce i toaście,
i nie odznacza niczego za operatora.

Wszystkie 31 zadań zamknięte, łącznie z ręcznym przebiegiem 6.3 na działającym stosie —
na parze, która naprawdę nie ma serii drobnej, a nie na atrapie.

Jedna rzecz do wiedzenia przy scalaniu: ta zmiana stoi na `add-technical-indicators` i nie da
się jej zarchiwizować wcześniej — obie dotykane zdolności istnieją dziś wyłącznie w delcie
tamtej, niezarchiwizowanej zmiany.

## Verified

- `cd modules/market-data && uv run pytest -q` → `1003 passed, 7 skipped`
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `cd modules/market-data && uv run pyright` → `0 errors, 0 warnings, 0 informations`
- `cd modules/terminal && pnpm test` → `408 passed` (29 plików)
- `cd modules/terminal && pnpm lint` → czysto
- `cd modules/terminal && pnpm typecheck` → czysto
- `cd modules/terminal && pnpm contract:check` → `Contract is up to date.`
- `openspec validate indicator-result-names-its-own-failure --strict` → `is valid`

### Przebieg ręczny (zadanie 6.3)

Moduł wystawiony na porcie zapasowym, przeciw prawdziwemu archiwum deweloperskiemu. `US100` ma
zebraną serię `MINUTE_5`, `SILVER` nie ma żadnej drobnej — czyli dokładnie ten przypadek, od
którego ta zmiana się zaczęła, bez ustawiania czegokolwiek pod test.

| Żądanie | Wynik |
|---|---|
| `SILVER`: `ema` + `session_range_london` + `time_profile` | `200`; `ema` z liniami, obie pozostałe z nazwaną przyczyną i bez kształtu |
| `SILVER`: `htf_levels_week` + `time_profile` | `200`; poziomy tygodniowe policzone (seria tygodniowa jest), profil z przyczyną |
| `SILVER`: `ema` + `nie_ma_takiego` | `422`, `unknown indicator: 'nie_ma_takiego'` |
| `SILVER`: `atr` + `ema(period=999999)` | `422`, `parameter 'period' = 999999.0 is outside [2, 5000]` |
| `US100`: `ema` + `session_range_london` + `time_profile` | `200`, wszystkie trzy policzone — regresja w drugą stronę: częściowa odpowiedź nie stała się nową normą |

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | `market_data/routers/indicators.py:400` | Pierwsza wersja wybierała serię do sprawdzenia przez `FINE_RESOLUTION if entry.needs_minute_series else entry.higher_resolution`. Dziś żaden wpis nie chce obu naraz, ale `if/else` czyta się tak, jakby to była gwarancja. Pierwszy wpis, który zechce obu, miałby zignorowany brak serii grubszej, policzyłby się przeciw pustemu `htf_periods` i odpowiedział pustym `levels` — czyli „policzono, nic nie znaleziono", dokładnie tym twierdzeniem, którego ta zmiana ma nie dopuszczać. Znalezione przy przeglądzie własnego diffu. Naprawione: sprawdzane są obie serie. | fixed |
| — | — | Poza tym nic nie przetrwało weryfikacji. | — |

Rozważone i świadomie zostawione bez zmian:

- **Komunikat o brakującej serii drobnej mówi „none could be derived from MINUTE either" także
  wtedy, gdy wykres jest sam w rozdzielczości minutowej, a w oknie po prostu nie ma świec.** Zdanie
  jest wtedy nadal prawdziwe, a stan — wykres bez ani jednej świecy — i tak jest widoczny wprost.
- **`missing_series` jest kluczowane rozdzielczością, nie wpisem.** To jest ta decyzja z
  `design.md`: trzy okna sesji i profil czytają tę samą serię i mają dostać ten sam powód,
  z jednego odczytu. Test 3.7 pilnuje, że odczyt zostaje jeden.

## Deviations from design.md

Brak. Wszystkie pięć decyzji wdrożone tak, jak zapisane, łącznie z `200` zamiast `207` i polem
na istniejącym wyniku zamiast osobnej listy porażek.

Jedna rzecz zrobiona przy okazji, poza zakresem: sekcja „Indicators" w `modules/market-data/
README.md` miała jeszcze cztery polskie słowa w angielskiej prozie. Poprzedni commit zamiatający
język twierdził, że naprawił siedem wystąpień; naprawił trzy. Poprawione razem z zadaniem 6.1,
które i tak dotykało tego akapitu.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-indicators: Wynik ma jeden z czterech kształtów** (MODIFIED) | |
| Strefa wciąż otwarta · Kształt zapowiedziany w katalogu | `tests/test_indicators_zones.py::TestSessionRange::test_window_still_forming_stays_open`, `tests/test_indicators_router.py::test_range_gap_is_returned_with_direction_and_bounds` (bez zmian) |
| Wynik bez kształtu, za to z przyczyną | `tests/test_indicators_router.py::TestResultShapeOrError::test_a_reason_alone_is_a_whole_result` |
| Pusto policzony a niepoliczalny | `::TestResultShapeOrError::test_a_shape_and_a_reason_together_are_refused` — kombinacji, która zatarłaby różnicę, nie da się zbudować; plus `::test_neither_a_shape_nor_a_reason_is_still_refused` |
| **market-data-indicators: Poziomy z wyższego interwału pochodzą z zamkniętego okresu** (MODIFIED) | |
| Poziomy poprzedniego dnia na wykresie minutowym | `tests/test_indicators_router.py::test_htf_levels_day_reads_the_previous_closed_day` (bez zmian) |
| Brak serii w wymaganej rozdzielczości | `::test_htf_levels_names_the_missing_day_series_in_its_own_result` — przepisany z odmowy całości na wynik z przyczyną, wraz z asercją, że `levels` jest `null`, a nie pustą listą |
| **market-data-indicators: Profil czasowy liczy się z serii minutowej** (MODIFIED) | |
| Profil pod wykresem czterogodzinnym | `::test_time_profile_computes_from_the_minute_series_at_day_resolution` (bez zmian) |
| Para bez serii minutowej | `::test_time_profile_names_the_missing_minute_series_in_its_own_result` |
| **market-data-indicators: Brakująca seria nie unieważnia policzonych wskaźników** (ADDED) | |
| Jeden wskaźnik bez serii, reszta policzona | `::TestPartialAnswer::test_a_missing_series_leaves_the_rest_computed`; ręcznie — `SILVER` z `ema` |
| Wszystkie zamówione wskaźniki bez serii | `::TestPartialAnswer::test_every_indicator_failing_is_still_an_answer` — plus asercja, że oba identyfikatory są obecne, bo konsument, który zamówił dwa i dostał jeden wiersz, nie wie który |
| Nieznany identyfikator obok policzalnych wskaźników | `::TestPartialAnswer::test_an_unknown_id_still_refuses_the_whole_request`; ręcznie |
| Parametr poza zakresem obok policzalnych wskaźników | `::TestPartialAnswer::test_a_parameter_out_of_range_still_refuses_the_whole_request`; ręcznie |
| Powtórzenie tego samego żądania | `::TestPartialAnswer::test_the_same_request_twice_gives_the_same_reasons` — porównanie całych ciał odpowiedzi, nie samych statusów |
| **terminal-chart: Wykres mówi, gdy wskaźników nie da się policzyć** (MODIFIED) | |
| Odczyt wskaźników zawiódł · Odmowa z powodu sufitu | `Chart.test.tsx` „a failed compute leaves the candles alone and offers a retry", „raises the reason as a toast" (bez zmian) |
| Część wskaźników policzona, część z przyczyną | `Chart.test.tsx` „draws the ones that computed and names the one that did not" |
| Nieudany wskaźnik zostaje wybrany | „keeps it selected — the operator chose it and the archive may yet hold the series", w tym sprawdzenie, co trafia do slotu siatki |
| Brakująca seria zostaje zebrana | „draws it on the next read that succeeds, without being picked again" — dopytanie po zamknięciu świecy, bez dotykania wyboru |
| (poza scenariuszami, z treści wymagania) | „leaves no empty primitive behind for the one that could not be computed" — pusty prymityw strefy byłby terminalem rysującym „policzono, nic nie ma" nad wynikiem mówiącym coś przeciwnego |

## Gaps

- **Nie ma testu, że dwa sloty padające z różnych powodów mówią osobno.** Klucz toasta zawiera
  symbol i rozdzielczość, więc z konstrukcji tak jest, a `toastStore.test.ts` pokrywa samo
  rozróżnianie kluczy — ale nie ma testu przez dwa wykresy naraz.
- **Sufit dla serii drobnej zostaje odmową całego żądania**, mimo że dotyczy tych samych wpisów
  co brak serii. Jest sufitem, a sufity są po stronie kształtu żądania — zapisane w `design.md`,
  potwierdzone testem 2.4, ale to jest miejsce, w którym granica z tej zmiany wygląda niespójnie,
  dopóki nie przeczyta się dlaczego.
- **`settled` i `error` dalej dwa pola o pokrewnym brzmieniu.** Opis każdego mówi wprost, czym nie
  jest to drugie, ale nic tego nie wymusza — konsument może uznać `settled: false` za porażkę.
- **Nic nie liczy, jak często odpowiedź jest częściowa.** Wskaźnik niedziałający od tygodni jest
  widoczny tylko dla kogoś, kto patrzy na ten wykres. Metryka byłaby osobną zmianą, po stronie
  `telemetry.py`.
