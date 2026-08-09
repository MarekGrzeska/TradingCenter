## 1. Kolejność

- [x] 1.1 `combinedEntries` sortuje po `at` malejąco jako kluczu głównym
- [x] 1.2 Remis rozstrzygany symbolem, a potem kanoniczną kolejnością interwałów — stabilnie między odczytami, bo zakładka odpytuje cyklicznie, a zlecenie z kreatora tworzy kilka par z tym samym `createdAt`
- [x] 1.3 Komentarz przy funkcji mówi, co się zmieniło i co to kosztowało (skasowanie przestaje sąsiadować z dociągnięciem, które odwróciło)

## 2. Testy

- [x] 2.1 Zdarzenia dwóch różnych par: nowsze jest wyżej, mimo że jego symbol jest alfabetycznie dalszy
- [x] 2.2 Skasowanie jednej pary nowsze niż dociągnięcie innej wypada nad nim
- [x] 2.3 Kilka par z tym samym `createdAt` (kształt zlecenia z kreatora) wychodzi w tej samej kolejności przy dwóch odczytach o różnym porządku wejściowym
- [x] 2.4 Dwa istniejące testy kolejności (`newest first` dla jednej pary, skasowanie obok dociągnięcia) MUST przejść **bez zmiany** — obie dotyczą jednej pary, więc nowa reguła ich nie narusza; gdyby wymagały edycji, znaczyłoby to, że zmiana sięga dalej, niż zamierzono — *przeszły bez zmiany*

## 3. Domknięcie

- [x] 3.1 `lint`, `typecheck` i testy w `terminal` (224 passed)
- [x] 3.2 README terminala, jeśli opisuje układ `Data History`
- [x] 3.3 `openspec validate data-history-newest-first --strict`
