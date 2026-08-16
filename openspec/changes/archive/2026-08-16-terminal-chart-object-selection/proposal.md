## Why

Rysunki na wykresie (`agent-chart-drawings`) są narysowane, ale nie da się z nimi nic
zrobić **na wykresie**. Poziom to kreskowana linia 1 px z gołym tekstem 10 px, która
przegrywa z knotami świec; żeby dowiedzieć się, czym jest, trzeba otworzyć listę
w nagłówku i odnaleźć go po cenie. Kliknąć w niego nie można wcale.

Do tego kolor: rysunki biorą go z `indicatorLineColor`, czyli **z tej samej palety co
wskaźniki**. Naniesiony przez operatora opór potrafi mieć dokładnie ten kolor co EMA 200
na tym samym wykresie — to nie jest kwestia gustu, tylko obiekt, którego nie da się
odróżnić od czegoś zupełnie innego. Przypisanie idzie z pozycji w tablicy, więc
skasowanie jednego rysunku przemalowuje pozostałe.

## What Changes

- **Rysunek operatora wyróżnia się od wyniku wskaźnika**: 2 px ciągłe wobec 1 px
  kreskowanego. Waga linii niesie autorstwo — co jest ustaleniem, a co rzeczą policzoną
  z katalogu.
- **Etykieta ceny przy osi cen** dla każdego rysunku, oraz podpis na wypełnionym chipie
  zamiast gołego tekstu. Podpis przykleja się do lewej krawędzi widoku, gdy początek
  rysunku jest poza ekranem — poziom nigdy nie jest bezimienną kreską.
- **Nowa zdolność: wybór obiektu na wykresie.** Kliknięcie w rysunek zaznacza go,
  najechanie zmienia kursor. Zaznaczony grubieje i dostaje otoczkę, pozostałe przygasają.
  Kliknięcie w puste miejsce i `Esc` odznaczają. Zaznaczenie jest wspólne z listą
  w nagłówku, w obie strony.
- **Opis przy obiekcie**: zaznaczenie otwiera kartę obok klikniętego miejsca — kształt,
  ceny, podpis, chwila powstania, oraz poprawienie i usunięcie tą samą drogą, którą
  robi to lista.
- **Własna paleta rysunków**, odrębna od wskaźnikowej, przypisywana po identyfikatorze
  rysunku, a nie po pozycji w liście.
- **Etykieta przy osi cen kolorowana rolą**, nie kolorem linii: wsparcie pod bieżącą
  ceną, opór nad nią. Linia mówi, **który** to obiekt; etykieta mówi, **czym** jest.
- Narzędzie `draw_on_chart` przyjmuje nowe tokeny kolorów — inaczej model może wybierać
  wyłącznie kolory wskaźników dla obiektów, które wskaźnikami nie są.

## Capabilities

### New Capabilities

- `terminal-chart-objects`: wybór naniesionego obiektu na wykresie — trafianie w niego
  wskaźnikiem myszy, stan zaznaczenia, opis przy obiekcie i to, jak zaznaczenie łączy się
  z listą.

### Modified Capabilities

- `terminal-chart`: rysunki naniesione na instrument wyróżniają się od wskaźników wagą
  linii, niosą etykietę przy osi cen i podpis czytelny nad świecami.
- `agent-chart-drawings`: paleta rysunków jest odrębna od wskaźnikowej, a kolor rysunku
  nie zależy od tego, ile innych rysunków stoi obok.

## Impact

- `modules/terminal`: `src/chart/theme.ts` (paleta rysunków), `RayPrimitive.ts`,
  `ZonePrimitive.ts`, `TrendlinePrimitive.ts` (waga, chip, etykieta przy osi, `hitTest`),
  `Chart.tsx` (nasłuch kliknięcia, stan zaznaczenia, karta), `DrawingList.tsx` (wspólne
  zaznaczenie), nowy komponent karty obiektu.
- `modules/agent`: `agent/tools/chart.py` — `CHART_COLORS` jest listą, wobec której
  `draw_on_chart` waliduje kolor od modelu, więc musi objąć nowe tokeny. Zmienia to
  schemat narzędzia widziany przez model; `agent/contract.py` bez zmian.
- Bez zmian: `market-data`, `market-mcp`, `capital-gateway`, `infra/`.
  `pnpm contract:generate` niepotrzebny — `market_data/contract.py` nietknięty.
- **Kolejność, i to jest wiążące**: `agent-chart-drawings` nie jest jeszcze
  zarchiwizowana, więc wymagania, które ta zmiana modyfikuje („Wykres rysuje obiekty
  naniesione na instrument", „Rysunek należy do instrumentu, nie do widoku"), leżą dziś
  w jej delcie, a nie w `openspec/specs/`. Ta zmiana MUSI zostać zarchiwizowana po niej,
  inaczej `MODIFIED` nie będzie miało czego modyfikować.
- Zależność biblioteczna: żadna nowa. `hitTest` na prymitywie, `hoveredObjectId`
  w zdarzeniu kliknięcia i `priceAxisViews` są w lightweight-charts 5.0.9, które terminal
  już ma.
