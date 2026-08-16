## Verdict

Rysunki na wykresie — poziomy, strefy i linie trendu, które agent zostawia na instrumencie
— są zaimplementowane w całości: od tabeli `chart_drawings` z `CHECK`-iem per kształt, przez
dwa narzędzia modelu (`draw_on_chart`, `list_chart_drawings`), publikację
(`GET`/`PATCH`/`DELETE /drawings`), rewizję promptu `v7`, aż po rysowanie trzech kształtów
na wykresie i listę, z której operator kasuje i poprawia. Trzy realne usterki znalezione
w trakcie tego review zostały naprawione przed napisaniem tego dokumentu — patrz Findings.

Rzecz, która w tej zmianie działa odwrotnie niż w `agent-chart-control` i jest tego świadoma:
`draw_on_chart` jest **przyrostowe**, nie deklaratywne. Pominięcie wskaźnika kosztuje jedno
kliknięcie, pominięcie wsparcia kosztowałoby tygodnie zbierania — uzasadnienie stoi
w specyfikacji, w `design.md` i w docstringu `tools/drawings.py`, żeby następny czytelnik
nie „naprawił" tej niespójności.

Ręczne przejście na żywym stacku (task 8.3) **nie zostało wykonane** — wymaga Dockera,
sesji Capital i klucza OpenAI, i jest czynnością operatora. Patrz Gaps.

## Verified

- `modules/agent`: `uv run pytest` — **289 passed**, 2 warnings (nieistotne, `httpx`/`pydantic-settings`).
- `modules/agent`: `uv run pytest -m db` — **187 passed**, 102 deselected.
- `modules/agent`: `uv run ruff check .` — All checks passed.
- `modules/agent`: `uv run pyright` — 0 errors, 0 warnings, 0 informations.
- `modules/terminal`: `pnpm test` (vitest) — **666 passed** w 47 plikach.
- `modules/terminal`: `pnpm lint` (eslint .) — bez zastrzeżeń.
- `modules/terminal`: `pnpm typecheck` (tsc --noEmit) — bez błędów.
- `openspec validate agent-chart-drawings --strict` — valid.
- `pnpm contract:generate` **niepotrzebne**: `market_data/contract.py` nietknięty, a kontrakt
  modułu `agent` jest pisany ręcznie po obu stronach (`design.md` zmiany `agent-chat`).
- Task 8.3 (ręczne przejście na żywym stacku) — **nie uruchomione**; patrz Gaps.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `modules/terminal/src/chart/DrawingList.tsx` | Przy nieudanym odczycie i pustym cache lista mówiła jednocześnie „the drawn objects could not be read" i „Nothing is drawn on this instrument." — czyli dokładnie to zdanie, którego `terminal-chart`, „Instrument bez obiektów" zabrania mylić z nieudanym odczytem. | **FIXED** w `524c101` — zdanie o pustce pada wyłącznie przy `status === "ready"`. Test `"a failed read says so, and does not read as an empty instrument"` napisany przed poprawką i to on ją wymusił. |
| Medium | `modules/agent/agent/tools/drawings.py`, `_as_geometry` (gałąź `zone`) | Strefa z `to` wcześniejszym niż `from` przechodziła: to jedyna reguła kształtu bez `CHECK`-a za sobą, bo oba momenty strefy są opcjonalne i baza nie ma czego pilnować. Terminal rysuje taką strefę jako prostokąt o zerowej szerokości (`ZonePrimitive`: `Math.max(xEnd - xStart, 0)`), czyli jako rysunek, którego po prostu nie widać. | **FIXED** w `c5d6980` — odmowa nazywająca oba momenty, plus test na odmowę i test na strefę otwartą w czasie (samo `from`), żeby poprawka nie odcięła legalnego kształtu. |
| Medium | `modules/agent/agent/tools/drawings.py`, `_as_removals` | Identyfikator spoza zakresu `bigint` (model wymyślający długą liczbę) trafiał do `id = ANY($2::bigint[])`, gdzie asyncpg podnosi wyjątek — czyli martwa tura zamiast zdania, które model umie poprawić (`agent-tools`, „Odmowa narzędzia jest wynikiem, nie awarią tury"). Python nie ma sufitu na `int`, więc było to osiągalne wprost z wywołania. | **FIXED** w `c5d6980` — `0 < id <= MAX_DRAWING_ID` (stała w `store.py`, obok `MAX_DRAWINGS_PER_SYMBOL`), odmowa w tym samym brzmieniu co dla nieistniejącego identyfikatora, plus test. |

Poza tym przejrzano cały diff `cf8f5d3..HEAD` bez dalszych ustaleń. Sprawdzone szczególnie:

- **Atomowość wywołania.** Cała transakcja obejmuje usunięcia, sufit i wstawienia, przy czym
  usunięcia idą pierwsze — dzięki temu „przesuń opór" mieści się przy suficie, gdzie dwa
  osobne wywołania musiałyby być ręcznie uszeregowane. Odmowa wewnątrz transakcji cofa
  usunięcie razem z resztą (`test_a_removal_that_names_one_missing_id_takes_back_the_others`).
- **Sufit liczony po usunięciach**, nie przed — inaczej wymiana jeden za jeden przy suficie
  byłaby odmawiana bez powodu.
- **Cykl życia rysunków wobec wskaźników.** Osobne prymitywy w osobnej mapie; test
  `"keeps the objects through a resolution change"` sprawdza **te same instancje**, nie samą
  liczbę — wspólna mapa dałaby nowe instancje i objawiłaby się jako znikające wsparcia.
- **`PATCH` po roli ceny, nie po kolumnie.** Rola, której dany kształt nie ma, jest odrzucana
  (422) zamiast wpisywana w kolumnę znaczącą tam co innego; strefa poprawiana samym `top`
  jest sprawdzana wobec `bottom`, który już ma, pod `FOR UPDATE`, więc sprawdzenie i zapis
  widzą jeden stan.
- **`DELETE` nieistniejącego → 404**, nie ciche 204. Rysunek, który zniknął z ekranu i nie
  z zapisu, wróciłby przy następnym odczycie.
- **Nieznany `kind` na drucie** jest pomijany, nie wywraca odczytu — moduł wdrożony przed
  terminalem może ogłosić czwarty kształt (`agentApi.test.ts`, `"skips a kind it has no
  shape for"`). W `patchDrawing` odwrotnie: tam pominięcie zostawiłoby wołającego bez wyniku
  i bez powodu, więc jest błąd.
- **Odczyt nie sprawdza symbolu w archiwum** — celowo: `list_chart_drawings` czyta własną
  tabelę modułu i odpowiada, cokolwiek robi archiwum. Prompt `v7` obiecuje operatorowi
  dokładnie to.
- **Odmowa nie zostawia śladu**: każdy test odmowy sprawdza `list_drawings(...) == []`.

## Spec coverage

### `agent-chart-drawings` (nowa zdolność)

| Requirement / Scenario | Proven by |
|---|---|
| Rysunek należy do instrumentu — Ten sam poziom na dwóch interwałach | `Chart.test.tsx::"keeps the objects through a resolution change"` |
| — Ten sam poziom w dwóch slotach | `drawingsStore.test.ts::"keeps one instrument's objects out of another's"` + `GridView.tsx::useSlotDrawings` (wpis po symbolu, nie po slocie) |
| — Strefa bez drugiej ceny | `test_drawings_tool.py::test_a_zone_with_equal_prices_is_not_a_zone`; schemat narzędzia wymaga `top` i `bottom` |
| Rysunki są trwałe i mają własną tożsamość — Rysunek przeżywa odświeżenie strony | `test_chart_drawings_store.py` (round-trip trzech kształtów) + `test_drawings_router.py::test_a_level_is_published_with_its_geometry` |
| — Rysunek przeżywa rozmowę | `test_chart_drawings_store.py`; `session_id` nullowalny z `ON DELETE SET NULL` (migracja `0007`) |
| — Sufit rysunków na instrumencie | `test_drawings_tool.py::test_the_ceiling_refuses_the_whole_call` |
| Agent stawia i kasuje rysunki narzędziem — Agent stawia wsparcie i opór | `test_drawings_tool.py::test_two_levels_in_one_call_both_land` |
| — Agent kasuje rysunek, który sam postawił | `test_drawings_tool.py::test_read_then_remove_uses_the_same_id` |
| — Wywołanie z jednym rysunkiem nie do przyjęcia | `test_drawings_tool.py::test_a_colour_the_chart_cannot_draw_is_refused_and_nothing_lands` |
| — Agent nie kasuje przez pominięcie | `test_drawings_tool.py::test_adding_does_not_remove_what_is_already_there` |
| Agent odczytuje rysunki narzędziem — Pytanie o naniesione poziomy | `test_drawings_tool.py::test_the_read_carries_ids_shapes_and_labels` |
| — Odczyt instrumentu spoza ekranu | `test_drawings_tool.py::test_the_read_answers_without_an_archive` (odczyt nie dotyka market-mcp ani slotów) |
| — Odczyt, potem skasowanie | `test_drawings_tool.py::test_read_then_remove_uses_the_same_id` |
| — Dwa odczyty pod rząd dają to samo | `test_drawings_tool.py::test_the_read_is_safe_to_repeat` |
| Odmowa rysowania nazywa, co poprawić — Instrument, którego archiwum nie zbiera | `test_drawings_tool.py::test_a_symbol_the_archive_does_not_collect_is_refused_with_the_ones_it_does` |
| — Strefa o odwróconych cenach | `test_drawings_tool.py::test_a_zone_with_inverted_prices_names_both` |
| — Linia trendu z dwoma punktami w tej samej chwili | `test_drawings_tool.py::test_a_trendline_with_both_points_at_one_moment_is_refused` |
| — Kasowanie nieistniejącego rysunku | `test_drawings_tool.py::test_removing_an_id_that_is_not_there_says_so`, `test_an_id_belonging_to_another_instrument_is_not_removable` |
| — Cena niedodatnia | `test_drawings_tool.py::test_a_price_at_or_below_zero_is_refused` |
| Operator cofa rysunek ręką — Operator kasuje poziom postawiony przez agenta | `test_drawings_router.py::test_a_removal_is_lasting`; `DrawingList.test.tsx::"removes one object"` |
| — Operator poprawia cenę poziomu | `test_drawings_router.py::test_a_correction_is_what_the_model_reads_back` |
| — Odczyt rysunków instrumentu | `test_drawings_router.py::test_the_read_does_not_carry_another_instruments_drawings` |

### `agent-tools` (delta)

| Requirement / Scenario | Proven by |
|---|---|
| Narzędzie własne modułu obok narzędzi serwera | `test_tool_calls_store.py::test_a_turn_with_tools_runs_the_prompt_that_says_that` (trzy nazwy po narzędziach serwera) |
| Brak serwera narzędzi | `test_tool_calls_store.py::test_a_turn_without_tools_runs_the_prompt_that_says_so` |
| Ślad wywołania mówi, kto je wykonał | `MODULE_TOOL_NAMES` w `contract.py` obejmuje trzy nazwy; `test_transcript_contract.py` (istniejące) na `source` |
| Operator prosi o naniesienie oporu | `test_drawings_tool.py::test_two_levels_in_one_call_both_land` |
| Operator cofa to, co narysował agent | `test_drawings_router.py::test_a_removal_is_lasting` |

### `terminal-chart` (delta)

| Requirement / Scenario | Proven by |
|---|---|
| Wykres rysuje obiekty naniesione na instrument — Poziom po zmianie interwału | `Chart.test.tsx::"keeps the objects through a resolution change"` |
| — Linia trendu między dwoma punktami | `TrendlinePrimitive.test.ts::"draws a segment between its two points and stops there"`, `"keeps its slope when one point is off the left edge"`, `"draws a line whose both ends are outside the visible range"` |
| — Zmiana symbolu | `Chart.test.tsx::"replaces them when the symbol changes"` |
| — Nieudany odczyt obiektów | `drawingsStore.test.ts::"a failed read keeps what was already drawn and says what went wrong"`; `DrawingList.test.tsx::"a failed read keeps showing what was already there"` |
| — Obiekt bez koloru dostaje kolor od wykresu | `TrendlinePrimitive.test.ts::"uses the line's own colour when it has one, and the chart's when it does not"`; `Chart.tsx`'s `indicatorColorFromToken(...) ?? indicatorLineColor(colors, index)` |
| Operator zarządza naniesionymi obiektami z listy — Operator usuwa poziom z listy | `DrawingList.test.tsx::"removes one object"` |
| — Operator poprawia cenę z listy | `DrawingList.test.tsx::"corrects a price, sending only what moved"` |
| — Usunięcie się nie powiodło | `DrawingList.test.tsx::"says a removal failed and leaves the row where it was"` |
| — Instrument bez obiektów | `DrawingList.test.tsx::"an instrument with nothing on it says so"` + `"a failed read says so, and does not read as an empty instrument"` |

### `terminal-agent-chat` (delta)

| Requirement / Scenario | Proven by |
|---|---|
| Agent nanosi opór w trakcie rozmowy | `agentChatStore.test.ts::"says what the agent drew, once the turn is over"` |
| Tą samą drogą co o poleceniu wykresu | `agentChatStore.test.ts::"says both in one sentence when the agent set the chart and drew on it"` |
| Nieudany odczyt obiektów nie przerywa rozmowy | `agentChatStore.test.ts::"reads the objects after every turn, even one that set no chart"`; nieudany odczyt jest połykany w `drawingsStore.read` |

## Gaps

- **Task 8.3, ręczne przejście na żywym stacku** — nie wykonane. Wymaga Dockera, sesji
  Capital i klucza OpenAI, i jest czynnością operatora, nie tego review. Do sprawdzenia:
  „nanieś opór na 21500", „co mamy naniesione", skasowanie z listy, przeżycie odświeżenia
  strony i zmiany interwału. Nic z tego nie jest logiką, której testy tu nie dotykają —
  ale żaden test nie dowodzi, że model *sięgnie* po `draw_on_chart`, gdy operator poprosi
  o naniesienie oporu, ani że opis narzędzia jest dla niego czytelny. To zachowanie modelu
  językowego i jedyny sposób sprawdzenia go to rozmowa.
- **Wyścig o sufit** — dwa równoległe wywołania `draw_on_chart` na tym samym instrumencie
  mogą oba przejść sprawdzenie sufitu i razem go przekroczyć: `count_drawings` nie blokuje
  wierszy, których jeszcze nie ma. Świadomie niezałatane — jeden operator, jedna tura naraz,
  a `SERIALIZABLE` albo blokada doradcza dla ograniczenia, którego przekroczenie o jeden
  nic nie psuje, byłaby ceną bez odbiorcy.
- **`PATCH` nie pozwala skasować etykiety** — pusta etykieta jest odmawiana (jak w
  `PatchSessionIn`), a `None` znaczy „zostaw". Zdjęcie podpisu wymagałoby wartownika na
  drucie. Specyfikacja mówi tylko o „poprawić ceny oraz etykietę", więc to nie jest luka
  wobec wymagania — jest luką wobec tego, czego operator może kiedyś chcieć.
- **Rysowanie myszą** — poza zakresem tej zmiany z założenia (`design.md`, Non-Goals);
  dlatego publikacja nie ma `POST`-a.
