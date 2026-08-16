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

- [x] 5.1 `src/agent/agentApi.ts`: `AgentChartFocus` na `AgentChartCommand`, mapper ISO → epoch-sekundy, `null` gdy polecenie nie niosło kadru
- [x] 5.2 `src/grid/gridStore.ts`: przejściowe, niezapisywane do `localStorage` pole „żądany kadr" per slot, z własnym `subscribe` i metodą czyszczącą po zastosowaniu
- [x] 5.3 `parseGridConfig` i zapis konfiguracji nietknięte — test, że kadr nie trafia do `localStorage` i że konfiguracja zapisana bez niego wczytuje się bez zmian
- [x] 5.4 `src/agent/chartControl.ts`: `syncAgentChart` przekazuje kadr do aktywnego slotu i dopisuje go do `applied`
- [x] 5.5 Testy `chartControl.test.ts`: polecenie z samym kadrem, polecenie z kadrem i symbolem, polecenie bez kadru nienaruszające widoku

## 6. Terminal: wykres stosuje kadr

- [x] 6.1 `Chart.tsx` przyjmuje żądany kadr, zamienia trzy formy na docelowy zakres czasu i ustawia widok, gdy świece z niego są narysowane
- [x] 6.2 `useOlderBars`: drugi powód do dociągania — najstarsza narysowana świeca późniejsza niż początek żądanego kadru; ten sam `MAX_PAGES` kończy sprawę (przez `needsMore` w `olderReader`, `useOlderBars.ts` samo nietknięte)
- [x] 6.3 Kadr, którego pager nie zapełnił, zostaje pominięty: widok bez zmian, toast (`showToast`) tą samą drogą co niedostępny wskaźnik — patrz design.md, decyzja o odejściu od `chartNotice`
- [x] 6.4 Kadr zużywa się raz: po zastosowaniu (albo pominięciu) slot go czyści (`onFocusRequestSettled` → `gridStore.clearFocusRequest`), a przewijanie operatora do niego nie wraca
- [x] 6.5 Testy `Chart.test.tsx`: kadr na już narysowane świece bez odczytu (from/to, last-bars, around/bars), kadr wymagający dociągnięcia, kadr na okres bez świec (toast)

## 7. Terminal: zmiana interwału zachowuje kadr

- [x] 7.1 Zapamiętanie przy zmianie `resolution`: początek i koniec widocznego zakresu oraz to, czy prawa krawędź serii była widoczna (tylko gdy zmienia się sama `resolution` — `symbol`/`source` inne niż poprzednio zerują ten zamiar)
- [x] 7.2 Pierwszy `redraw` nowej serii ustawia zachowany odcinek zamiast `fitContent()`; `fitContent()` zostaje tam, gdzie slot niczego jeszcze nie rysował
- [x] 7.3 Przycięcie liczby świec do `[MIN_VISIBLE_BARS, MAX_VISIBLE_BARS]` = `[10, 500]` wokół środka odcinka
- [x] 7.4 Kotwica prawej krawędzi (z tolerancją `RIGHT_EDGE_SLACK_BARS`): wykres stojący na bieżącej świecy zostaje na bieżącej świecy nowego interwału
- [x] 7.5 Testy: zmiana interwału nad fragmentem historii, przy prawej krawędzi, odcinek zbyt krótki dla nowego interwału, brak zmiany przy pierwszym rysowaniu slotu i przy zmianie symbolu

## 8. Terminal: rejestr widocznego zakresu

- [x] 8.1 Niereaktywny rejestr `slotId → {from, to}` — w `gridStore` (`getVisibleRange`/`setVisibleRange`), nie w osobnym module, żeby `GridView` nie musiało importować `chartControl.ts`/`agentApi`'s singletona; `Chart` zgłasza przez nowy prop `onVisibleRangeChange`, `GridView` zapisuje, czyszczone przy odmontowaniu slotu (wywołanie z `null` w cleanupie)
- [x] 8.2 `activeChartSnapshot` czyta z niego i dokłada `visibleFrom`/`visibleTo` do migawki; brak wpisu znaczy `null`/`null`, nie zera. `chartSnapshotToWire` w `agentApi.ts` domyka mapowanie na drut (epoch → ISO, tylko gdy obie połówki znane) — dotąd `sendMessage` wysyłało `chart` bez mapowania
- [x] 8.3 Testy: `gridStore` (get/set/clear, brak wpływu na `localStorage`/config listeners), `Chart.tsx` (`onVisibleRangeChange` na pan/pusta seria/unmount), `activeChartSnapshot` (z zakresem, bez, zakres innego slotu), `agentApi.sendMessage` (obie połówki, tylko jedna)

## 9. Domknięcie

- [x] 9.1 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright` w `modules/agent` — 233 + 131, czysto
- [x] 9.2 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `modules/terminal` — 618 testów, czysto
- [ ] 9.3 Przejście ręką na żywym stacku: „pokaż mi wczorajszy poranek", „przybliż ostatnie 50 świec", zmiana interwału nad tym samym miejscem — operator testuje sam
- [x] 9.4 `openspec validate agent-chart-navigation --strict`
- [x] 9.5 `review.md` wg szablonu — bez niego zmiany nie da się zarchiwizować
