## 1. Paleta rysunków

- [x] 1.1 `src/chart/theme.ts`: tokeny palety rysunków, odrębne od `INDICATOR_LINE_TOKENS`, oraz ich odczyt do `ChartColors`
- [x] 1.2 `drawingColorFromToken(colors, token)` rozwiązujące tokeny rysunków **oraz** wskaźnikowe — rysunek sprzed zmiany zachowuje swój kolor
- [x] 1.3 `drawingColorFor(id, colors)`: kolor z identyfikatora rysunku, nie z pozycji w tablicy
- [x] 1.4 `Chart.tsx`: rysunki biorą kolor stąd zamiast z `indicatorLineColor`
- [x] 1.5 Testy `theme.test.ts`: paleta rysunków rozłączna z wskaźnikową, stary token nadal rozwiązywany, ten sam identyfikator zawsze tym samym kolorem

## 2. Paleta po stronie agenta

- [x] 2.1 `agent/tools/chart.py`: tokeny rysunków obok `CHART_COLORS`, jako osobna lista
- [x] 2.2 `agent/tools/drawings.py`: `draw_on_chart` waliduje kolor wobec palety rysunków, nie wskaźnikowej — w schemacie narzędzia i w odmowie
- [x] 2.3 Migracja seedująca nową rewizję promptu: akapit o rysunkach mówi o palecie rysunków, nie „tej samej co wskaźniki"; tekst poprzedniej rewizji przepisany w całości, oba warianty
- [x] 2.4 Testy: kolor z palety rysunków przyjęty, token wskaźnikowy odrzucony z nazwaniem go, rewizja niesie obie nazwy narzędzi i nie obiecuje już palety wskaźników

## 3. Wygląd rysunku

- [x] 3.1 `RayPrimitive`/`ZonePrimitive`/`TrendlinePrimitive`: waga linii jako parametr — 2 px ciągłe dla rysunku, 1 px kreskowane dla wskaźnika, bez rozdwajania klas
- [x] 3.2 Podpis na wypełnionym chipie zamiast gołego tekstu
- [x] 3.3 Podpis przyklejony do lewej krawędzi widoku, gdy początek rysunku jest poza nią
- [x] 3.4 `priceAxisViews()` na trzech prymitywach: etykieta ceny przy osi
- [x] 3.5 Kolor etykiety przy osi z roli — pod bieżącą ceną wsparcie, nad nią opór; kolor linii, gdy wykres nie ma jeszcze ceny
- [x] 3.6 Testy prymitywów: waga rysunku wobec wskaźnika, chip pod podpisem, podpis przy krawędzi dla obiektu zaczynającego się poza ekranem, kolor etykiety po obu stronach ceny i bez ceny

## 4. Trafianie w obiekt

- [x] 4.1 `hitTest(x, y)` w `RayPrimitive` — pasmo tolerancji wokół odcinka, `externalId` równy identyfikatorowi rysunku, `cursorStyle: "pointer"`
- [x] 4.2 `hitTest` w `ZonePrimitive` (własny prostokąt) i w `TrendlinePrimitive` (pasmo wokół odcinka między punktami)
- [x] 4.3 Trafianie zwraca `null` dla prymitywu rysującego wynik wskaźnika — klikalne są rysunki, nie wskaźniki
- [x] 4.4 Testy trafiania: w linię, tuż obok w granicach tolerancji, dalej niż tolerancja, dla trzech kształtów; prymityw wskaźnika nie trafia nigdy

## 5. Zaznaczenie na wykresie

- [x] 5.1 `Chart.tsx`: stan zaznaczenia po identyfikatorze rysunku, sprzątany przy zmianie symbolu
- [x] 5.2 `subscribeClick`: `hoveredObjectId` zaznacza, kliknięcie w puste miejsce odznacza
- [x] 5.3 `Escape` odznacza
- [x] 5.4 Zaznaczony obiekt rysuje się grubiej i z otoczką, pozostałe przygasają
- [x] 5.5 Testy `Chart.test.tsx`: kliknięcie zaznacza, kliknięcie w puste odznacza, `Escape` odznacza, zmiana symbolu zdejmuje zaznaczenie, zaznaczenie nie zmienia zapisu obiektu

## 6. Karta obiektu

- [x] 6.1 `src/chart/DrawingCard.tsx`: kształt, ceny, podpis, chwila powstania, oraz Popraw i Usuń — zawartość i operacje z `ChartDrawings`, tak jak lista
- [x] 6.2 Edytor pól wyciągnięty z `DrawingList.tsx` do wspólnego komponentu i użyty w obu miejscach
- [x] 6.3 Karta pozycjonowana obok klikniętego miejsca, po tej stronie, gdzie jest miejsce
- [x] 6.4 Usunięcie z karty zdejmuje zaznaczenie razem z obiektem; nieudane usunięcie albo poprawka zostawia obiekt i mówi o tym
- [x] 6.5 Testy `DrawingCard.test.tsx`: opis trzech kształtów, poprawka, usunięcie, nieudana poprawka, nieudane usunięcie

## 7. Jedno zaznaczenie dla wykresu i listy

- [x] 7.1 `DrawingList.tsx` przyjmuje zaznaczenie i zgłasza jego zmianę zamiast trzymać własne
- [x] 7.2 Wiersz zaznaczonego obiektu wyróżniony na liście; wybór z listy zaznacza na wykresie
- [x] 7.3 Testy: z wykresu na listę, z listy na wykres, odznaczenie sięga obu

## 8. Domknięcie

- [x] 8.1 `pnpm test`, `pnpm lint`, `pnpm typecheck` w `modules/terminal`
- [x] 8.2 `uv run pytest`, `uv run pytest -m db`, `uv run ruff check .`, `uv run pyright` w `modules/agent`
- [ ] 8.3 Przejście ręką na żywym stacku: kliknięcie w poziom, poprawka z karty, usunięcie z karty, odznaczenie, przeżycie zmiany interwału i odświeżenia strony
- [x] 8.4 `openspec validate terminal-chart-object-selection --strict`
- [x] 8.5 `review.md` wg szablonu — bez niego zmiany nie da się zarchiwizować
