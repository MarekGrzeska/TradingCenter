## 1. Zapis rysunków w module agent

- [x] 1.1 Migracja: tabela `chart_drawings` — `id` (Identity), `session_id` (FK, nullowalny), `symbol`, `kind`, `time_a`, `price_a`, `time_b`, `price_b`, `label`, `color`, `created_at`, `updated_at`
- [x] 1.2 Ta sama migracja: `CHECK` per kształt wg tabeli w `design.md` — `level`, `zone` (`price_b > price_a`), `trendline` (oba czasy wymagane, `time_b > time_a`), oraz `price_a > 0`
- [x] 1.3 Indeks po `symbol` — jedyny odczyt, jaki ta tabela obsługuje
- [x] 1.4 `agent/models.py`: `ChartDrawing` jako unia trzech kształtów dyskryminowana przez `kind`
- [x] 1.5 `agent/store.py`: `list_drawings(symbol)`, `add_drawings(...)`, `remove_drawings(ids, symbol)`, `update_drawing(id, ...)` plus tłumaczenie unia ↔ cztery kolumny, w obie strony
- [x] 1.6 Sufit 100 rysunków na instrument sprawdzany w tej samej transakcji, w której powstają
- [x] 1.7 Testy integracyjne (`-m db`): każdy `CHECK` odrzuca to, co ma odrzucać; round-trip każdego z trzech kształtów; sufit

## 2. Narzędzia agenta

- [ ] 2.1 `agent/tools/drawings.py`: deskryptor `draw_on_chart` — `symbol`, `add[]` (trzy kształty z polami po ludzku), `remove[]` (identyfikatory), kolory z `CHART_COLORS` importowanych z `tools/chart.py`
- [ ] 2.2 Sprawdzenie symbolu przez `list_tracked_pairs` w `market-mcp`, z tą samą odmową, gdy serwera narzędzi nie ma, co w `set_chart`
- [ ] 2.3 Odmowy: kolor spoza palety, strefa o cenach równych albo odwróconych, linia trendu o punktach w tej samej chwili, cena niedodatnia, sufit, identyfikator nieistniejący na tym instrumencie
- [ ] 2.4 Atomowość: całe wywołanie w jednej transakcji, wywołanie z jednym rysunkiem nie do przyjęcia nie stawia żadnego
- [ ] 2.5 Deskryptor `list_chart_drawings(symbol)` i jego wykonanie — odczyt z identyfikatorami, bezpieczny do powtórzenia
- [ ] 2.6 `agent/tools/__init__.py` i miejsce składania zestawu narzędzi tury: trzy narzędzia własne zamiast jednego
- [ ] 2.7 `agent/contract.py`: `MODULE_TOOL_NAMES` obejmuje nowe nazwy, żeby `source` w śladzie wywołania mówił „module"
- [ ] 2.8 Testy `test_drawings_tool.py`: po jednym na każdą odmowę z 2.3, na atomowość, na odczyt i na parę „odczytaj, potem skasuj"

## 3. Publikacja rysunków

- [ ] 3.1 `agent/contract.py`: `ChartDrawingOut` jako unia dyskryminowana, `PatchDrawingIn` na ceny i etykietę
- [ ] 3.2 `agent/routers/drawings.py`: `GET /drawings?symbol=`, `PATCH /drawings/{id}`, `DELETE /drawings/{id}` — globalne, `current_principal` wyłącznie do odrzucenia nieuwierzytelnionego żądania
- [ ] 3.3 `PATCH` zachowuje tożsamość rysunku i nie pozwala zmienić `kind` ani `symbol`
- [ ] 3.4 `DELETE` nieistniejącego rysunku odpowiada 404, a nie cichym sukcesem
- [ ] 3.5 Router wpięty w `agent/app.py`
- [ ] 3.6 Testy routera: odczyt po symbolu nie zwraca cudzych rysunków, poprawka zachowuje identyfikator, usunięcie jest trwałe

## 4. Prompt systemowy

- [ ] 4.1 Migracja seedująca nową rewizję: akapit o obu narzędziach, tekst poprzedniej rewizji przepisany w całości (oba warianty)
- [ ] 4.2 Zdanie odróżniające rysunek operatora od `levels_near_price` — jedno jest ustaleniem, drugie odczytem z archiwum
- [ ] 4.3 Test sprawdzający, że rewizja istnieje i niesie obie nazwy narzędzi

## 5. Terminal: odczyt i zapis rysunków

- [ ] 5.1 `src/agent/agentApi.ts`: `ChartDrawing` w kształtach terminala (epoch-sekundy), `listDrawings(symbol)`, `patchDrawing(id, ...)`, `deleteDrawing(id)`
- [ ] 5.2 Mapper drutu: ISO → epoch-sekundy, `kind` jako dyskryminator, nieznany `kind` pomijany zamiast wywracać odczyt
- [ ] 5.3 Odczyt rysunków po zakończonej turze i przy zmianie symbolu slotu
- [ ] 5.4 Zdanie w panelu z porównania „przed i po" odczycie — tym samym kanałem co `describeChartControl`
- [ ] 5.5 Nieudany odczyt nie czyści wykresu ani nie przerywa rozmowy
- [ ] 5.6 Testy `agentApi.test.ts` i towarzyszące: mapowanie trzech kształtów, nieznany `kind`, nieudany odczyt

## 6. Terminal: rysowanie obiektów

- [ ] 6.1 `src/chart/TrendlinePrimitive.ts` na wzór `RayPrimitive` — odcinek między dwoma punktami, bez przedłużania i bez przycinania do widocznego zakresu
- [ ] 6.2 `TrendlinePrimitive.test.ts`: oba punkty poza widocznym zakresem, jeden poza, punkty których czasu skala nie umie umiejscowić
- [ ] 6.3 `Chart.tsx`: własne instancje `RayPrimitive`/`ZonePrimitive`/`TrendlinePrimitive` dla rysunków, w mapach osobnych od wskaźnikowych
- [ ] 6.4 Rysunki przeżywają zmianę rozdzielczości i znikają przy zmianie symbolu
- [ ] 6.5 Etykieta i kolor rysunku; brak koloru rozwiązywany przez wykres
- [ ] 6.6 Testy `Chart.test.tsx`: trzy kształty na wykresie, zmiana rozdzielczości, zmiana symbolu

## 7. Terminal: lista rysunków

- [ ] 7.1 Lista obiektów aktywnego slotu: kształt, ceny, etykieta, chwila powstania — dostępna bez rozmowy z agentem
- [ ] 7.2 Usunięcie pojedynczego obiektu, ze skutkiem widocznym na wykresie od razu
- [ ] 7.3 Poprawienie cen i etykiety, ze skutkiem widocznym od razu
- [ ] 7.4 Nieudane usunięcie albo poprawka: zdanie o tym, a lista i wykres bez zmian
- [ ] 7.5 Pusta lista mówi, że nic nie jest naniesione, i nie da się jej pomylić z nieudanym odczytem
- [ ] 7.6 Testy listy: usunięcie, poprawka, nieudane usunięcie, instrument bez obiektów

## 8. Domknięcie

- [ ] 8.1 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright` w `modules/agent`
- [ ] 8.2 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `modules/terminal`
- [ ] 8.3 Przejście ręką na żywym stacku: „nanieś opór na 21500", „co mamy naniesione", skasowanie z listy, przeżycie odświeżenia strony i zmiany interwału
- [ ] 8.4 `openspec validate agent-chart-drawings --strict`
- [ ] 8.5 `review.md` wg szablonu — bez niego zmiany nie da się zarchiwizować
