## 1. Zapis i kontrakt agenta

- [x] 1.1 Migracja: `hidden boolean not null default false` w `chart_drawings`, plus rewizja promptu przepisana w całości, oba warianty
- [x] 1.2 `agent/models.py`: `ChartDrawing.hidden`, obok `created_at`, nie w geometrii
- [x] 1.3 `agent/store.py`: `hidden` w kolumnach odczytu i w `_drawing_from_row`; `update_drawing` przyjmuje je jak resztę pól, `None` znaczy „zostaw"
- [x] 1.4 `agent/store.py`: `set_drawings_hidden(symbol, ids, hidden)` zwracające identyfikatory, na których faktycznie usiadło — tak jak `remove_drawings`
- [x] 1.5 `agent/contract.py`: `ChartDrawingOut.hidden` oraz `PatchDrawingIn.hidden`, dołożone też do listy w `_asks_for_something`
- [x] 1.6 `agent/routers/drawings.py`: `PATCH` przepuszcza `hidden`
- [x] 1.7 Testy `test_chart_drawings_store.py`: zapis i odczyt `hidden`, gaszenie i zapalanie, identyfikator z innego instrumentu nie daje się zgasić
- [x] 1.8 Testy `test_drawings_router.py`: `PATCH` gasi i zapala, samo `hidden` wystarcza za zmianę, 404 dla nieznanego identyfikatora

## 2. Narzędzie modelu

- [x] 2.1 `agent/tools/drawings.py`: `hide` i `show` w schemacie `draw_on_chart`, opisane jako odwracalne wobec nieodwracalnego `remove`
- [x] 2.2 Wykonanie `hide`/`show` w tej samej transakcji co `add`/`remove`, pod regułą „w całości albo wcale”
- [x] 2.3 Nieznany identyfikator w `hide`/`show` odrzuca całe wywołanie i nazywa ten identyfikator — jak w `remove`
- [x] 2.4 Ten sam identyfikator w `hide` i `show` naraz: odmowa nazywająca go
- [x] 2.5 Wywołanie, które nie robi nic z czterech list, nadal odrzucane
- [x] 2.6 `list_chart_drawings` niesie `hidden` przy każdym rysunku
- [x] 2.7 Sufit: `count_drawings` liczy zgaszone — test stawiający na instrumencie pełnym zgaszonych
- [x] 2.8 Testy `test_drawings_tool.py`: gaszenie, zapalanie, sprzeczne polecenie, nieznany identyfikator cofa resztę, odczyt mówi o zgaszonych
- [x] 2.9 Testy `test_prompt_store.py`: rewizja mówi o gaszeniu i o tym, że jest odwracalne

## 3. Terminal — druty i sklep

- [x] 3.1 `src/agent/agentApi.ts`: `hidden` na kształcie rysunku i w łatce; brak pola na drucie czytany jako zapalony, nie jako brak obiektu
- [x] 3.2 `src/agent/drawingsStore.ts`: `setHidden(id, hidden)` obok `remove` i `patch`, z tą samą umową „null albo zdanie o niepowodzeniu”
- [x] 3.3 Testy sklepu: zgaszenie idzie do modułu i sklep czyta na nowo; nieudane zostawia stan bez zmian

## 4. Terminal — wykres

- [x] 4.1 `Chart.tsx`: prymitywy budowane z zapalonych, lista dostaje całość
- [x] 4.2 Zgaszony obiekt nie ma prymitywu, więc nie trafia i nie stawia etykiety przy osi — bez nowej gałęzi w prymitywach
- [x] 4.3 Wskazanie przeżywa zgaszenie, ale nie usunięcie
- [x] 4.4 Testy `Chart.test.tsx`: zgaszony nie jest rysowany, kliknięcie w jego miejsce nic nie wskazuje, kolory pozostałych bez zmian po zgaszeniu, wskazanie po zgaszeniu

## 5. Terminal — lista i karta

- [x] 5.1 `DrawingList.tsx`: przełącznik przy wierszu, wiersz zgaszonego wyraźnie oznaczony
- [x] 5.2 Instrument z samymi zgaszonymi nie czyta się jak instrument bez obiektów
- [x] 5.3 `DrawingCard.tsx`: „Zgaś”/„Zapal” obok „Usuń”, karta zostaje otwarta po zgaszeniu
- [x] 5.4 Nieudane zgaszenie zostawia obiekt zapalony i mówi o tym — w obu miejscach
- [x] 5.5 Testy `DrawingList.test.tsx` i `DrawingCard.test.tsx`: gaszenie, zapalanie, nieudane gaszenie, karta po zgaszeniu, lista samych zgaszonych

## 6. Domknięcie

- [x] 6.1 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `modules/terminal`
- [x] 6.2 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright` w `modules/agent`
- [ ] 6.3 Przejście ręką na żywym stacku: zgaszenie z listy i z karty, zapalenie z powrotem, przeżycie odświeżenia strony, zgaszenie przez agenta
- [x] 6.4 `openspec validate terminal-chart-object-visibility --strict`
- [ ] 6.5 `review.md` wg szablonu — bez niego zmiany nie da się zarchiwizować
