## Why

Wykres pokazuje dokładnie tyle, ile przyniesie snapshot subskrypcji — ostatnie 500 świec — i na tym
historia się kończy: przewinięcie w lewo trafia w pustkę, choć archiwum trzyma dane od `collect_from`.
Przy okazji: wybór instrumentu w slocie jest autocompletem, a lista archiwizowanych par jest z
założenia krótka (ogranicza ją `MAX_TRACKED_PAIRS`), więc wpisywanie frazy to praca, której nie ma po co
wykonywać — operator chce zobaczyć wszystko, co zbieramy, i kliknąć jedną pozycję.

## What Changes

- Wykres dociąga starsze świece, gdy operator przewija w lewo poza to, co narysowane: odczyt zakresu z
  archiwum, doklejenie na początek serii, bez ruszania widocznego kadru.
- Wykres mówi, że dociąga (i że doszedł do końca historii albo że odczyt się nie powiódł), zamiast
  milczeć przy pustym marginesie.
- Snapshot pozostaje jedynym źródłem prawej krawędzi serii; odczyt zakresu dotyczy wyłącznie okresów
  starszych niż najstarsza narysowana świeca — szew między historią a strumieniem nie wraca.
- Pole instrumentu w slocie przestaje być autocompletem i staje się listą wyboru wszystkich
  instrumentów archiwizowanych. Znika lokalne filtrowanie po frazie i źródło `archivedInstrumentSource`.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `terminal-chart`: nowy wymóg — historia dociągana przy przewijaniu w lewo, wraz ze stanami, które
  wykres o tym dociąganiu mówi.
- `terminal-grid`: wymóg „Slot przyjmuje wyłącznie instrument archiwizowany" przestaje mówić o
  podpowiedziach i frazie, a zaczyna o liście wyboru.

## Impact

- `modules/terminal/src/chart/` — `Chart.tsx` (nasłuch zakresu widocznego, doklejanie na początek serii),
  nowy moduł stronicowania historii, `testDoubles.ts` (stub osi czasu).
- `modules/terminal/src/grid/` — `SymbolField.tsx` staje się selectem, `GridView.tsx` podaje mu listę
  i stan odczytu.
- `modules/terminal/src/ui/autocompleteSources.ts` — usunięcie `archivedInstrumentSource` wraz z testami.
  `Autocomplete` zostaje: używa go kreator instrumentów.
- Bez zmian w `market-data` i bez zmian w kontrakcie: `GET /candles/{symbol}` z zakresem już istnieje i
  terminal ma go w `MarketDataSource.history`.
