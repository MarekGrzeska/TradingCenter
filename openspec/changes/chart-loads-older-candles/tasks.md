## 1. Stronicowanie historii

- [x] 1.1 Nowy moduł `chart/useOlderBars.ts`: odczyt zakresu starszego niż podana świeca, okno mierzone
      rozpiętością narysowanych świec, podwajane przy pustej odpowiedzi, limit prób, stan
      `idle | loading | exhausted | error`, przerwanie przy zmianie źródła, symbolu i rozdzielczości.
- [x] 1.2 Testy stronicowania — przez `chart/Chart.test.tsx`, a nie osobno dla haka: hak nie ma
      zachowania, które dałoby się stwierdzić bez serii, którą stronicuje.

## 2. Wykres

- [x] 2.1 `chart/testDoubles.ts`: stub osi czasu — zapamiętane wywołania `fitContent`, nasłuch zmiany
      widocznego zakresu logicznego, odczyt i ustawienie tego zakresu.
- [x] 2.2 `chart/Chart.tsx`: nasłuch widocznego zakresu, żądanie starszej strony przy lewej krawędzi,
      doklejanie na początek serii z korektą kadru, `fitContent()` tylko przy pierwszym rysunku pary.
- [x] 2.3 `chart/Chart.tsx`: pasek stanu dociągania — trwa, początek historii, nieudany odczyt z
      ponowieniem — bez zasłaniania narysowanych świec.
- [x] 2.4 Testy `chart/Chart.test.tsx` do scenariuszy z `specs/terminal-chart`.

## 3. Wybór instrumentu w slocie

- [x] 3.1 `grid/SymbolField.tsx`: select z listą archiwizowanych symboli, pozycja pusta czyszcząca slot,
      komunikat przy pustej liście i przy nieodczytanej liście wraz z ponowieniem.
- [x] 3.2 `grid/GridView.tsx`: podanie symboli, stanu odczytu, błędu i `reload` do `SymbolField`
      w nagłówku slotu, w slocie pustym i w slocie nieaktualnym.
- [x] 3.3 Usunięcie `archivedInstrumentSource` z `ui/autocompleteSources.ts` i jego testów.
- [x] 3.4 Aktualizacja testów `grid/GridView.test.tsx` do wyboru z listy.

## 4. Domknięcie

- [x] 4.1 `modules/terminal/README.md`: opis `ui/` bez usuniętego źródła autocomplete.
- [x] 4.2 `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm contract:check` w `modules/terminal`.
- [x] 4.3 `openspec validate chart-loads-older-candles --strict`.
