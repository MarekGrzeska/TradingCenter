## 1. Kadr w module agent: kształt i zapis

- [x] 1.1 `agent/models.py`: `ChartFocus` (pola `from_`, `to`, `around`, `bars`, `last_bars`, wszystkie opcjonalne) plus `focus: ChartFocus | None` na `ChartCommand`; `merged_with` traktuje je jak resztę pól
- [x] 1.2 Migracja `0006`: nullowalna kolumna `JSONB focus` w `chart_commands`, `chart_commands_sets_something` rozszerzony o nią, `downgrade` zdejmujący obie zmiany
- [x] 1.3 `agent/store.py`: `record_chart_command` przyjmuje i zapisuje kadr, `_chart_command_from_row` go odczytuje
- [x] 1.4 `agent/contract.py`: `focus` na `ChartCommandOut`, wystawiany jako `null`, gdy polecenie go nie niosło
- [x] 1.5 Test integracyjny (`-m db`): zapis polecenia z kadrem i odczyt przez `chart_state_after`; polecenie z samym kadrem nie wpada w check bazy

## 2. Kadr w narzędziu `set_chart`

- [x] 2.1 Schemat narzędzia: `focus` z opisem trzech form, granicami `[10, 1000]` dla `bars`/`last_bars` i formatem czasu ISO 8601 UTC
- [x] 2.2 `_as_focus`: parsowanie i odmowy — dokładnie jedna forma, `from < to`, granice liczby świec, czas dający się sparsować
- [x] 2.3 Odmowa kadru leżącego w całości w przyszłości (zegar modułu, bez odczytu z archiwum)
- [x] 2.4 `set_chart` bez żadnego z czterech pól (`symbol`, `resolution`, `indicators`, `focus`) nadal odmawia; kadr liczy się jako „coś do ustawienia"
- [x] 2.5 `_confirmation` mówi o kadrze zdaniem, które model może powtórzyć operatorowi
- [x] 2.6 Testy `test_chart_tool.py`: po jednym na każdą odmowę z 2.2–2.3 oraz na zapis polecenia z samym kadrem (`tests/test_chart_focus_tool.py`)

## 3. Migawka niesie widoczny fragment osi

- [x] 3.1 `agent/models.py`: `visible_from` / `visible_to` na `ChartSnapshot`, oba opcjonalne osobno
- [x] 3.2 `ChartSnapshot.as_context`: zdanie o widocznym fragmencie, pomijane w całości, gdy pola są puste
- [x] 3.3 `agent/contract.py`: te pola na wejściu tury; żądanie bez nich działa jak dotąd
- [x] 3.4 Testy: migawka z fragmentem i bez niego, obie trafiające do promptu tury w oczekiwanym kształcie

## 4. Prompt systemowy

- [x] 4.1 Migracja `0006` seeduje `v6`: akapit `set_chart` wymienia kadr i trzy sposoby jego podania, tekst `v5` przepisany w całości (oba warianty, jak w `0005`)
- [x] 4.2 Test sprawdzający, że zaseedowana rewizja istnieje i niesie nazwę narzędzia oraz słowo o kadrze

## 5. Terminal: DTO i przekazanie kadru do slotu

- [ ] 5.1 `src/agent/agentApi.ts`: `AgentChartFocus` na `AgentChartCommand`, mapper ISO → epoch-sekundy, `null` gdy polecenie nie niosło kadru
- [ ] 5.2 `src/grid/gridStore.ts`: przejściowe, niezapisywane do `localStorage` pole „żądany kadr" per slot, z własnym `subscribe` i metodą czyszczącą po zastosowaniu
- [ ] 5.3 `parseGridConfig` i zapis konfiguracji nietknięte — test, że kadr nie trafia do `localStorage` i że konfiguracja zapisana bez niego wczytuje się bez zmian
- [ ] 5.4 `src/agent/chartControl.ts`: `syncAgentChart` przekazuje kadr do aktywnego slotu i dopisuje go do `applied`
- [ ] 5.5 Testy `chartControl.test.ts`: polecenie z samym kadrem, polecenie z kadrem i symbolem, polecenie bez kadru nienaruszające widoku

## 6. Terminal: wykres stosuje kadr

- [ ] 6.1 `Chart.tsx` przyjmuje żądany kadr, zamienia trzy formy na docelowy zakres czasu i ustawia widok, gdy świece z niego są narysowane
- [ ] 6.2 `useOlderBars`: drugi powód do dociągania — najstarsza narysowana świeca późniejsza niż początek żądanego kadru; ten sam `MAX_PAGES` kończy sprawę
- [ ] 6.3 Kadr, którego pager nie zapełnił, zostaje pominięty: widok bez zmian, wpis w `skipped`, zdanie w panelu
- [ ] 6.4 Kadr zużywa się raz: po zastosowaniu (albo pominięciu) slot go czyści, a przewijanie operatora do niego nie wraca
- [ ] 6.5 Testy `Chart.test.tsx`: kadr na już narysowane świece bez odczytu, kadr wymagający dociągnięcia, kadr na okres bez świec

## 7. Terminal: zmiana interwału zachowuje kadr

- [ ] 7.1 Zapamiętanie przy zmianie `resolution`: początek i koniec widocznego zakresu oraz to, czy prawa krawędź serii była widoczna
- [ ] 7.2 Pierwszy `redraw` nowej serii ustawia zachowany odcinek zamiast `fitContent()`; `fitContent()` zostaje tam, gdzie slot niczego jeszcze nie rysował
- [ ] 7.3 Przycięcie liczby świec do `[MIN_VISIBLE_BARS, MAX_VISIBLE_BARS]` wokół środka odcinka
- [ ] 7.4 Kotwica prawej krawędzi: wykres stojący na bieżącej świecy zostaje na bieżącej świecy nowego interwału
- [ ] 7.5 Testy: zmiana interwału nad fragmentem historii, przy prawej krawędzi, oraz odcinek zbyt krótki dla nowego interwału

## 8. Terminal: rejestr widocznego zakresu

- [ ] 8.1 Niereaktywny rejestr `slotId → {from, to}`, pisany przez `Chart` przy zmianie widocznego zakresu, czyszczony przy odmontowaniu slotu
- [ ] 8.2 `activeChartSnapshot` czyta z niego i dokłada `visibleFrom`/`visibleTo` do migawki; brak wpisu znaczy brak pól, nie zera
- [ ] 8.3 Testy: migawka slotu z odnotowanym zakresem, migawka slotu bez niego

## 9. Domknięcie

- [ ] 9.1 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright` w `modules/agent`
- [ ] 9.2 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `modules/terminal`
- [ ] 9.3 Przejście ręką na żywym stacku: „pokaż mi wczorajszy poranek", „przybliż ostatnie 50 świec", zmiana interwału nad tym samym miejscem
- [ ] 9.4 `openspec validate agent-chart-navigation --strict`
- [ ] 9.5 `review.md` wg szablonu — bez niego zmiany nie da się zarchiwizować
