## Verdict

Wszystko z propozycji weszło: agent dostał jedno narzędzie zapisujące, ograniczone do
aktywnego slotu terminala, sprawdzane przed zapisem przeciw katalogowi i zbieranym parom
przez `market-mcp`, odmawiane ze zdaniem, co poprawić, i zapisywane w całości albo wcale.
Polecenie jest numerowane i deklaratywne, terminal czyta je po turze i po wejściu na
stronę, stosuje do aktywnego slotu w jego granicach, i mówi operatorowi, że to agent
zmienił wykres. Migawka tego, co terminal rysuje, jedzie w żądaniu tury i nigdzie się nie
zapisuje. Ślad wywołania odróżnia narzędzie modułu od narzędzia serwera.

Ten przegląd naprawił czternaście rzeczy znalezionych w pierwszym przebiegu code review —
cztery w narzędziu i pętli tury po stronie `agent`, sześć w zastosowaniu polecenia i panelu
po stronie `terminal`, jedną migrację i jeden test — każda ze swoim testem blokującym
regresję. Jedna rzecz, którą pierwszy przebieg nazwał błędem, została po ponownym czytaniu
specyfikacji **cofnięta**: zobacz Findings, wiersz "rozważone i cofnięte". Zadania 8.2 i 9.3
zostają operatorowi — patrz Gaps.

## Verified

| Komenda | Wynik |
|---|---|
| `modules/agent`: `uv run pytest` | **203 passed** |
| `modules/agent`: `uv run pytest -m db` | **107 passed, 96 deselected** (testcontainers) |
| `modules/agent`: `uv run ruff check .` | `All checks passed!` |
| `modules/agent`: `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `modules/terminal`: `pnpm typecheck` | czysto |
| `modules/terminal`: `pnpm test` | 44 pliki, **576 testów, wszystkie zielone** |
| `modules/terminal`: `pnpm lint` | czysto (0 błędów, 0 ostrzeżeń) |
| `openspec validate add-agent-chart-control --strict` | valid |

Nie uruchamiane: `-m live` (z założenia, potrzebuje prawdziwej sesji Capital/OpenAI),
zadanie 8.2 (rozmowa w uruchomionym terminalu) i 9.3 (`alembic upgrade head` na bazie
deweloperskiej) — oba to kroki ręczne operatora, patrz Gaps. `pnpm contract:check` nie
dotyczy tej zmiany: `agent/contract.py` jest kontraktem pisanym ręcznie
(`agentApi.ts`'s own docstring, "Kontrakt terminala pisany ręcznie, bez generatora"), nie
generowanym z `market_data/contract.py`.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoki | `Chart.tsx` `assignLineColors` | Cykl auto-koloru pomijał każdy kolor wybrany ręcznie, więc wybór koloru dla jednej instancji przesuwał kolory instancji, których nikt nie tknął — wprost łamiąc inwariant `indicatorLines` z `theme.ts` ("indexed by how many indicator lines are already drawn — never by which one a line is"). Indeks cyklu jest teraz stały wg kolejności rysowania, nigdy wg tego, co zajęte ręcznie. | **FIXED**, test `Chart.test.tsx::"picking a colour for one instance never repaints another still on Auto"` |
| Wysoki | `agentChatStore.ts` `syncChartCommands` | Brak strażnika przed nakładającymi się wywołaniami — montowanie panelu, `setExpanded(true)` i `finishTurn` mogły odpalić je równocześnie, stosując to samo polecenie dwa razy. Dodany `chartSyncInFlight`, tym samym mechanizmem co `modelsInFlight`/`sessionsInFlight`. | **FIXED** |
| Średni | `agentChatStore.ts` `chartNotice` | Nigdy nie było czyszczone — zdanie sprzed dziesięciu pytań albo sprzed poprzedniej rozmowy wisiało nad kompozytorem, opisując wykres, którego już nie ma. Czyszczone teraz na początku nowej tury, przy otwarciu innej rozmowy i przy nowej rozmowie. | **FIXED** |
| Niski | `agentChatStore.ts` | Dokumentacja incydentu produkcyjnego z 13 sierpnia (`ensureLoaded`) i dokumentacja `syncChartCommands` zlały się w jeden blok nad złą funkcją. Rozdzielone, każda nad swoją. | **FIXED** |
| — (rozważone i cofnięte) | `agentChatStore.ts` `ensureLoaded` | Pierwszy przebieg nazwał błędem, że `syncChartCommands` odpala się przed strażnikiem `!state.expanded`, twierdząc, że zwinięty panel stosuje polecenie „bez zdania nigdzie". Specyfikacja `terminal-agent-chat` mówi wprost: terminal MUST czytać nowe polecenia **po wejściu na stronę**, bez warunku na stan panelu — właśnie po to, żeby polecenie sprzed zamknięcia karty nie przepadło. Zdanie trafia do `state.chartNotice` i tak, i pokazuje się, gdy operator otworzy panel — nic nie ginie. Poprawka cofnięta, zamiast niej krótki komentarz przy `ensureLoaded` tłumaczący, dlaczego strażnik stoi tam, gdzie stoi. | **Reverted** |
| Wysoki | `chartControl.ts` | Odrzucony symbol zabierał ze sobą interwał poprawny dla symbolu, który faktycznie zostaje na slocie — `resolutions` liczone było raz, z symbolu jeszcze przed odrzuceniem. Sprawdzenie interwału przeliczane teraz przeciw symbolowi, który naprawdę wyląduje na slocie. | **FIXED**, test `chartControl.test.ts::"does not let a rejected symbol veto a resolution the slot's own symbol collects"` |
| Wysoki | `agent/tools/chart.py` `_check_pair` | Polecenie z samym symbolem nie sprawdzało interwału, na którym wykres akurat stoi — narzędzie potwierdzało sukces, a terminal i tak odrzucał kombinację. Migawka wykresu (`ChartSnapshot`), którą `turn.py` już miał, jest teraz przekazywana do narzędzia i używana jako domyślny interwał do sprawdzenia, gdy polecenie go nie podaje. | **FIXED**, testy `test_chart_tool.py::test_a_symbol_only_command_is_checked_against_the_chart_s_current_interval` i `::test_a_symbol_only_command_is_accepted_when_the_current_interval_fits` |
| Wysoki | `agent/graph.py` `run_tools` | Wywołanie narzędzia lokalnego (`local(request.arguments)`) nie miało osłony wyjątków, w przeciwieństwie do gałęzi `tool_server.call` obok — awaria (np. połączenie z bazą zerwane w środku `record_chart_command`) uciekała do `turn.py`'s backstopu i kasowała cały tekst tury. Osłonięte teraz tak samo jak `ToolServer.call` osłania siebie, z wynikiem `UNAVAILABLE` zamiast wyjątkiem. | **FIXED**, test `test_graph.py::test_a_local_tool_that_raises_is_a_result_not_a_failed_turn` |
| Średni | `agent/tools/chart.py` `_check_indicators` | Zakładało słownikową kopertę z `list_indicators`, podczas gdy `_check_pair` obok broni się przed obiema (goła lista albo koperta). Ta sama osłona dołożona. | **FIXED** |
| Niski | `agent/tools/chart.py` `ChartTool.call` | `_check_pair` i `_check_indicators` czekały sekwencyjnie, mimo że żadne nie używa wyniku drugiego — każde polecenie z symbolem i wskaźnikami płaciło dwa okrążenia zamiast jednego. Uruchamiane teraz razem przez `asyncio.gather`, z `return_exceptions=True` i kolejnością sprawdzania zachowaną (odmowa pary dalej wygrywa, tak jak sekwencyjnie). | **FIXED** |
| Niski | `agent/migrations/versions/0004_chart_commands.py` | Indeks na `session_id` tworzony wprost pod komentarzem mówiącym, że drugiego indeksu nie ma celowo — żadne zapytanie nie filtruje po `session_id`. Usunięty. | **FIXED** |
| Niski | `agent/contract.py` `ToolCallOut.source` | Pole publikowane na drucie w każdym wywołaniu narzędzia, ale nieczytane przez terminal — spec `agent-tools` wymaga, żeby ślad wywołania **dało się** odróżnić, nie żeby był odróżniony w interfejsie, więc to nie było złamanie wymagania, ale niedokończenie go. Dopisane do `toolCall.ts`/`RawToolCall` i pokazywane w `ToolCallEntry.tsx` jako etykieta „module" — tylko dla wywołań własnych modułu, bo to one są wyjątkiem, nie serwer. | **FIXED**, testy `stream.test.ts::"names the module's own tool apart from a server one"` i `::"keeps a source it has no name for out of the two it does"` |
| Niski | `agent/tests/conftest.py` `db` | `DELETE FROM prompt_revisions WHERE id > 2` — liczba na sztywno, już raz edytowana przy poprzednim seedzie migracji. Zastąpiona odczytem `max(id)` zaraz po migracjach, w nowym fixture'ze sesyjnym `seeded_prompt_revision_max_id` — kolejny seed nie będzie wymagał edycji tego pliku. | **FIXED** |
| Wydajność | `Chart.tsx` `activeIndicatorReadout` | `drawnInstances` i `assignLineColors` liczone od nowa przy każdym ruchu krzyża — oba zależą tylko od selekcji, wyników i kolorów, które zmieniają się dużo rzadziej niż piksel pod myszką. Wyciągnięte do `useMemo` (`readoutAssignment`), licznik pozostawiony tylko dla taniego dopasowania słupka pod kursorem. | **FIXED** |

## Spec coverage

**`agent-chart-control` — Narzędzie ustawia zawartość aktywnego slotu (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Model pokazuje średnią | `test_chart_tool.py::test_a_full_set_is_recorded_as_one_command` |
| Model zmienia sam interwał | `test_chart_tool.py::test_one_field_alone_says_nothing_about_the_others` |
| Model podaje pełny zestaw wskaźników | `test_chart_tool.py::test_a_full_set_is_recorded_as_one_command` |

**`agent-chart-control` — Ustawienie jest zapisane i ponumerowane (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Polecenie przeżywa odświeżenie strony | `test_chart_command_store.py::test_indicators_survive_the_round_trip` |
| Dwie rozmowy, jeden ciąg | `test_chart_command_store.py::test_sequence_rises_across_sessions` |

**`agent-chart-control` — Konsument czyta tylko to, czego jeszcze nie zastosował (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Nic nowego od ostatniego odczytu | `test_chart_command_store.py::test_nothing_newer_than_the_cursor_is_nothing`; `test_chart_router.py::test_nothing_newer_than_the_cursor_answers_with_nothing` |
| Konsument wraca po przerwie | `test_chart_command_store.py::test_missed_commands_fold_into_one_answer`; `test_chart_router.py::test_a_consumer_coming_back_gets_everything_it_missed_as_one` |

**`agent-chart-control` — Odmowa narzędzia nazywa, co poprawić (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Symbol, którego archiwum nie zbiera | `test_chart_tool.py::test_a_symbol_the_archive_does_not_collect_is_refused_with_the_ones_it_does` |
| Parametr poza granicami katalogu | `test_chart_tool.py::test_a_parameter_out_of_range_names_the_range` |
| Odmowa nie zostawia śladu na wykresie | `test_chart_tool.py::test_an_unknown_indicator_is_refused_and_nothing_is_written` |
| Interwał niezbierany dla symbolu (zdanie wymagania) | `test_chart_tool.py::test_a_resolution_that_symbol_is_not_collected_in_is_refused` oraz — polecenie z samym symbolem przeciw bieżącemu interwałowi wykresu — `test_chart_tool.py::test_a_symbol_only_command_is_checked_against_the_chart_s_current_interval` |
| Kolor spoza palety | `test_chart_tool.py::test_a_colour_the_chart_cannot_draw_is_refused` |
| Brak serwera narzędzi (zdanie wymagania) | `test_chart_tool.py::test_without_a_tool_server_it_refuses_rather_than_writing_blind`; `::test_an_archive_that_does_not_answer_is_not_a_reason_to_guess` |

**`agent-tools` — Zestaw narzędzi pochodzi z serwera, nie z tego modułu (MODIFIED)**

| Requirement / Scenario | Proven by |
|---|---|
| Narzędzie własne modułu obok narzędzi serwera | `test_graph.py::test_both_kinds_of_tool_share_one_turn_and_one_ceiling` |
| Ślad wywołania mówi, kto wykonał (zdanie wymagania) | `stream.test.ts::"names the module's own tool apart from a server one"` |
| Brak serwera narzędzi | `test_chart_tool.py::test_without_a_tool_server_it_refuses_rather_than_writing_blind` |

**`agent-tools` — Agent zapisuje wyłącznie w widoku terminala (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Operator prosi o pokazanie wskaźnika | `test_graph.py::test_a_local_tool_runs_here_and_never_reaches_the_server` |
| Odmowa narzędzia własnego nie kończy tury (zdanie wymagania) | `test_graph.py::test_a_local_tool_refusing_is_a_result_the_model_can_act_on`; `::test_a_local_tool_that_raises_is_a_result_not_a_failed_turn` |
| Operator cofa to, co ustawił agent | `chartControl.test.ts::"does not apply the same command twice"` (usunięcie ręczne przeżywa kolejny odczyt) |

**`agent-chat` — Tura wie, co terminal właśnie rysuje (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Pytanie o to, co widać | `test_sessions_router.py::test_a_turn_carrying_a_chart_snapshot_hands_it_to_the_model` |
| Żądanie bez migawki | `test_sessions_router.py::test_a_turn_without_a_snapshot_runs_the_prompt_untouched` |
| Migawka nie trafia do transkryptu | `test_transcript_contract.py::test_a_message_on_the_wire_carries_exactly_these_fields` (pole migawki nie jest jednym z nich) |

**`terminal-grid` — Aktywny slot stosuje to, co ustawił agent (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Agent ustawia wskaźniki aktywnego slotu | `chartControl.test.ts::"applies the indicators the agent set to the active slot, and leaves the others alone"` |
| Ustawienie agenta przeżywa odświeżenie | `chartControl.test.ts::"asks from the cursor it was left with, across a reload"` |
| To samo polecenie nie stosuje się dwa razy | `chartControl.test.ts::"does not apply the same command twice"` |
| Agent zmienia symbol i interwał | `chartControl.test.ts::"applies symbol and interval the archive collects"` |
| Polecenie spoza granic pominięte (zdanie wymagania) | `chartControl.test.ts::"skips a symbol the archive does not collect rather than drawing an empty chart"`; `::"skips an interval that symbol is not collected in"`; `::"does not let a rejected symbol veto a resolution the slot's own symbol collects"` |

**`terminal-agent-chat` — Panel mówi, że wykres zmienił agent (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Agent zmienia wykres w trakcie rozmowy | `agentChatStore.test.ts::"says what the agent did to the chart, once the turn is over"` |
| Polecenie wydane przed zamknięciem karty | `chartControl.test.ts::"asks from the cursor it was left with, across a reload"` (kursor w `localStorage` przeżywa) |
| Odczyt poleceń zawiódł | `agentChatStore.test.ts::"keeps the conversation when the chart read fails"`; `chartControl.test.ts::"leaves the chart and the cursor alone when the read fails"` |

## Gaps

Żadnych otwartych. Oba braki, które ten dokument wcześniej wymieniał, zostały domknięte —
patrz addenda niżej.

## Addendum — 8.2 domknięte, i co ten ręczny test wykrył

Operator poprosił agenta w uruchomionym terminalu: „dodaj mi SMA 20/50/100/200 na wykresie
US100". **Za pierwszym razem nie zadziałało** — i to jest cała wartość tego zadania, bo
wykryło trzy błędy, których żaden test nie łapał, wszystkie poza zakresem samego
`set_chart`:

1. **`list_tracked_pairs` czytane nie z tego pola.** `ToolServer.call` sklejał bloki
   `content`, a SDK MCP dla narzędzia zwracającego gołą listę (`list[TrackedPairOut]`)
   tworzy **jeden blok na element**, nie jeden na tablicę (`_convert_to_content` rekurencyjnie
   wchodzi w listę). Przy dwóch i więcej śledzonych parach `json.loads` dostawał dwa
   dokumenty JSON pod rząd i wywracał się na „Extra data" — stąd `set_chart` odmawiał
   z „list_tracked_pairs answered something unreadable". Przy dokładnie jednej parze
   błąd byłby cichy: pojedynczy obiekt zamiast tablicy jednoelementowej, czyli
   `pairs.get("result", …)` → `[]` i każdy symbol odrzucony jako niezbierany.
   Poprawione na czytanie `structuredContent`, które SDK buduje z tej samej wartości
   zwrotnej **zanim** rozbije ją na bloki. Test: `test_tool_server.py::
   test_a_bare_list_return_reads_back_as_one_json_array`, przeciw prawdziwemu serwerowi
   FastMCP, nie atrapie.
2. **Polecenie docierało, ale wykres go nie pokazywał bez przeładowania strony.**
   `Chart.tsx` inicjalizował listę wskaźników z propsa leniwym `useState`, który wykonuje
   się **raz, przy montowaniu**. Zapis agenta idzie prosto do `gridStore` (z pominięciem
   callbacku, którym operator edytuje przez wybierak), więc komponent dostawał nowego
   propsa i nigdy go nie odczytywał. To jest dokładnie to, czemu miał zapobiegać scenariusz
   „Agent zmienia wykres w trakcie rozmowy → wykres pokazuje je **bez odświeżania strony**",
   a `chartControl.test.ts` tego nie łapał, bo kończy się na `gridStore`. Test:
   `Chart.test.tsx::"draws an indicator the slot gained from outside the picker, without
   remounting"`.
3. **Odczyt pod kursorem znikał i przestawiał układ.** Wskaźniki liczone są na zakresie
   z `redraw`, nie na każdym ticku, więc najświeższy słupek bywa o krok przed tym, co
   archiwum policzyło — odczyt szukał dokładnie tego czasu i pokazywał pustkę. Do tego
   siedział w `<header>`, więc zmiana jego wysokości szła przez `ResizeObserver`
   w `chart.resize()` w środku przeciągania wykresu. Odczyt jest teraz nakładką nad
   wykresem (poza układem, `pointer-events-none`), z `tabular-nums`, grupowany po typie
   wskaźnika i zaokrąglany do dwóch miejsc. Testy: `"keeps showing the newest known
   indicator value once the pointer leaves the chart…"`, `"draws the readout over the chart
   rather than in the header…"`, `"puts several instances of one indicator on one readout
   row…"`.

Po tych trzech poprawkach polecenie działa end-to-end: cztery SMA, każda w swoim kolorze,
pojawiają się na wykresie w trakcie rozmowy. Zakres formalny 8.2 mówił o EMA 200 na
godzinie; sprawdzone zostało mocniejsze żądanie (cztery instancje jednego wpisu naraz,
z kolorami), więc zadanie odhaczone.

## Addendum — `market-mcp` sprawdzone na żywo

Poprzednia wersja tego dokumentu notowała jako lukę, że `list_indicators`
i `list_tracked_pairs` nie były porównane z kształtem zakładanym przez testy. Ręczny
przebieg 8.2 to zamknął — i znalazł tam realną rozbieżność (punkt 1 wyżej). Kształt
`list_indicators` (koperta ze słownikiem pod kluczem `indicators`) potwierdził się zgodny
z założeniem testów; `list_tracked_pairs` nie, i to jest naprawione.

## Addendum — 9.3 domknięte, na innej maszynie

Na tym stanowisku baza deweloperska nie była odświeżana od dawna: kontener
`tradingcenter-db` stał (5 dni), `market_data` był na `0007` (head), ale rola i baza
`agent` **nie istniały w ogóle** — utworzone dopiero teraz przez `dev.sh`, nigdy ręcznie.
`modules/agent/.env` też nie istniał (plik gitignored, per-maszyna) — skopiowany z
`.env.example`, `OPENAI_API_KEY` uzupełniony placeholderem (`local-dev-placeholder-not-a-
real-key`), bo `agent/config.py`'s `_not_blank` odmawia startu na pustym kluczu, a
`migrations/env.py` importuje `Settings()` żeby dostać `DATABASE_URL` — realny klucz
potrzebny dopiero do faktycznej rozmowy z modelem, nie do migracji.

Odtworzone ręcznie, dokładnie tak jak `dev.sh` robi to przy pierwszym uruchomieniu:

```
CREATE ROLE agent LOGIN PASSWORD 'change-me';
CREATE DATABASE agent OWNER agent;
```

`uv run alembic upgrade head` w `modules/agent` przeszedł od `-> 0001` aż do `0005 (head)`
bez błędu, migracja `0004_chart_commands` (ta edytowana w tym przebiegu — usunięty
`ix_chart_commands_session_id`) włącznie. `\d chart_commands` na świeżo zmigrowanej bazie
potwierdza: jedyny indeks to `chart_commands_pkey`. Zadanie 9.3 odhaczone w `tasks.md`.
