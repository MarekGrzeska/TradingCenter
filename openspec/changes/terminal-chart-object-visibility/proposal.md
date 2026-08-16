## Why

Dziś naniesiony obiekt można tylko **skasować**. Operator, który zebrał na US100
kilkanaście poziomów przez miesiąc i chce na chwilę popatrzeć na czyste świece, ma jedno
wyjście: usunąć je i postawić od nowa — czyli stracić chwilę powstania, identyfikator
i etykietę każdego z nich. To jest kasowanie w roli, w której miało być zgaszenie światła.

To samo z drugiej strony: agent poproszony o „sprawdzenie strefy popytu bez tych
wszystkich linii" nie ma czym tego zrobić. Narzędzie zna `add` i `remove`, więc jedyne
posunięcie, jakie może wykonać, jest nieodwracalne — a `agent-chart-drawings` sam mówi,
dlaczego to źle: pominięcie wsparcia kosztowałoby tygodnie zbierania.

## What Changes

- **Rysunek niesie stan widoczności.** Nowa kolumna `hidden` w `chart_drawings`
  i pole na drucie. Ukryty rysunek nadal istnieje: ma ten sam identyfikator, tę samą
  chwilę powstania i tę samą etykietę, i wraca dokładnie taki, jaki był.
- **Ukrycie jest własnością obiektu, nie stanem ekranu.** Ukryty jest ukryty we wszystkich
  slotach pokazujących ten instrument, po odświeżeniu strony i po restarcie modułu — tak
  jak sam rysunek należy do instrumentu, a nie do widoku.
- **`draw_on_chart` dostaje `hide` i `show`** — dwie listy identyfikatorów obok `add`
  i `remove`, w tym samym przyrostowym wywołaniu i pod tą samą regułą „w całości albo
  wcale". `list_chart_drawings` zaczyna mówić, który rysunek jest ukryty; bez tego model
  gasi zgaszone i nie umie odpowiedzieć, co stoi na wykresie.
- **Operator przełącza to ręką** — z listy obiektów i z karty obiektu, tą samą drogą,
  którą dziś poprawia cenę: `PATCH /drawings/{id}` przyjmuje `hidden`.
- **Wykres nie rysuje ukrytych.** Ukryty obiekt nie ma prymitywu, więc nie da się w niego
  kliknąć ani nie zasłania świec. Zostaje na liście, wyszarzony, bo lista jest jedyną
  drogą powrotną.
- Nowa rewizja promptu: akapit o rysunkach mówi, że gaszenie jest odwracalne, a kasowanie
  nie — inaczej model dalej będzie kasował, żeby coś schować.

## Capabilities

### New Capabilities

Brak. Ukrywanie jest własnością rysunku i operacją na nim, a nie nową zdolnością obok
istniejących.

### Modified Capabilities

- `agent-chart-drawings`: rysunek niesie stan widoczności, który MUST przeżyć to samo, co
  sam rysunek; narzędzie gasi i zapala obok stawiania i kasowania, a odczyt mówi, który
  rysunek jest zgaszony.
- `terminal-chart`: wykres rysuje obiekty widoczne, a lista pozwala zgasić i zapalić
  pojedynczy obiekt bez jego usuwania.
- `terminal-chart-objects`: opis wskazanego obiektu pozwala go zgasić i zapalić, tak samo
  jak pozwala go poprawić i usunąć.

## Impact

- `modules/agent`: migracja dokładająca `hidden` do `chart_drawings` plus rewizja promptu;
  `store.py` (`update_drawing`, `_SELECT_DRAWING_COLUMNS`, `_drawing_from_row`),
  `models.py` (`ChartDrawing.hidden`), `contract.py` (`ChartDrawingOut.hidden`,
  `PatchDrawingIn.hidden`), `routers/drawings.py`, `tools/drawings.py` (`hide`/`show`
  w schemacie i w wykonaniu, `hidden` w odczycie).
- `modules/terminal`: `agentApi.ts` i `drawingsStore.ts` (pole na drucie i przełącznik),
  `Chart.tsx` (ukryty obiekt nie dostaje prymitywu i nie może być wskazany),
  `DrawingList.tsx` i `DrawingCard.tsx` (przełącznik i wyszarzenie).
- Bez zmian: `market-data`, `market-mcp`, `capital-gateway`, `infra/`.
  `pnpm contract:generate` niepotrzebny — `market_data/contract.py` nietknięty, a kontrakt
  agenta terminal trzyma ręcznie po obu stronach.
- **Sufit stu obiektów na instrument liczy także ukryte.** Sufit jest o zapisie, nie
  o ekranie, a taki, który da się obejść gaszeniem, nie jest sufitem.
- **Kolejność archiwizacji, i to jest wiążące**: ta zmiana modyfikuje wymagania, które
  leżą dziś w deltach dwóch niezarchiwizowanych zmian — `agent-chart-drawings` („Rysunki
  są trwałe i mają własną tożsamość", „Agent stawia i kasuje rysunki narzędziem", „Agent
  odczytuje rysunki narzędziem", „Wykres rysuje obiekty naniesione na instrument",
  „Operator zarządza naniesionymi obiektami z listy") oraz
  `terminal-chart-object-selection` („Wskazany obiekt mówi, czym jest"). Kolejność MUSI
  być: `agent-chart-drawings` → `terminal-chart-object-selection` → ta zmiana. Inaczej
  `MODIFIED` nie będzie miało czego modyfikować.
- Zależność biblioteczna: żadna nowa.
