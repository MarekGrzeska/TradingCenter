## 1. Kształt selekcji i paleta

- [x] 1.1 `data/types.ts`: `IndicatorSelection` dostaje `key: string` (tożsamość instancji)
      i `color: string | null` (nazwa tokenu palety albo przydział samoczynny); komentarz
      mówi, że `key` jest nadawany, nie liczony z zawartości
- [x] 1.2 `chart/theme.ts`: wyeksportować listę tokenów palety wskaźników i funkcję
      rozwiązującą nazwę tokenu na barwę bieżącego motywu; nieznany token → `null`
- [x] 1.3 Test `theme.test.ts`: każdy eksportowany token rozwiązuje się na barwę, a token
      spoza listy nie
- [x] 1.4 `data/archive.ts`: `computeIndicators` wysyła nadal tylko `{ id, params }` —
      potwierdzić testem, że `key` ani `color` nie jedzie na drut

## 2. Kolejność wyników po stronie archiwum

- [x] 2.1 `modules/market-data`: test routera — dwa identyczne zamówienia tego samego
      wskaźnika wracają jako dwa wyniki na swoich pozycjach, a kilka różnych wraca
      w kolejności zamówienia (kod routera bez zmian)
- [x] 2.2 `uv run pytest` i `uv run ruff check .` w `modules/market-data`

## 3. Wybierak: instancje

- [x] 3.1 `IndicatorPicker.tsx`: wiersz katalogu przestaje być checkboxem stanu
      globalnego — dodaje instancję (`+`), a każda istniejąca instancja tego wpisu ma
      własny wiersz z parametrami i własnym usunięciem
- [x] 3.2 `setParam` i błędy parametrów kluczowane po `key` instancji, nie po `id` wpisu
- [x] 3.3 Licznik na przycisku „Indicators" liczy instancje
- [x] 3.4 Testy `IndicatorPicker.test.tsx`: trzy instancje jednego wpisu z różnymi
      okresami; zmiana okresu jednej nie rusza pozostałych; usunięcie jednej zostawia
      pozostałe; dodanie drugiej instancji z parametrami domyślnymi jest dozwolone

## 4. Wybierak: kolor

- [x] 4.1 Rząd próbek palety pod parametrami instancji: `<button>` na próbkę,
      `aria-pressed` na wybranej, plus powrót do przydziału samoczynnego
- [x] 4.2 Testy: wybór koloru trafia do selekcji jako nazwa tokenu; powrót do
      samoczynnego czyści `color` na `null`; próbki mają dostępne nazwy

## 5. Wykres: zestawianie wyników z instancjami

- [x] 5.1 `useIndicators`: stan niesie tablicę selekcji, dla której policzono wyniki —
      jeden spójny snapshot `{ times, results, selections }`
- [x] 5.2 Test `useIndicators`: po zmianie selekcji w trakcie odczytu snapshot pozostaje
      spójny (wyniki i selekcje z tego samego odczytu)
- [x] 5.3 `Chart.tsx`: pętla rysująca iteruje po parach (instancja, wynik) zestawionych po
      indeksie snapshotu, zamiast po samych wynikach
- [x] 5.4 Klucze map serii, paneli własnych, linii odniesienia, wtyczek znaczników,
      `RayPrimitive`, `ZonePrimitive` i `TimeProfilePrimitive` przechodzą na `key`
      instancji (serie linii: `` `${key}|${lineSpec.key}` ``)

## 6. Wykres: kolor instancji

- [x] 6.1 Kolor linii, znaczników i poziomów brany z `color` **bieżącej** selekcji o tym
      kluczu (nie ze snapshotu), żeby przemalowanie działało bez ponownego odczytu
- [x] 6.2 Cykl samoczynny pomija barwy wybrane ręcznie i pozostaje stabilny wobec
      włączania i wyłączania innych instancji
- [x] 6.3 Testy `Chart.test.tsx`: dwie instancje jednego wpisu rysują się osobno; kolor
      wybrany trafia na serię; kolor instancji nie zmienia się po dodaniu kolejnej;
      instancja bez koloru dostaje barwę z cyklu

## 7. Odczyt spod kursora

- [x] 7.1 `activeIndicatorReadout` kluczuje wpisy po `key` instancji i podpisuje je
      parametrami tej instancji
- [x] 7.2 Odczyt niesie barwę instancji, żeby przy identycznych parametrach dało się
      rozróżnić, która wartość jest z której linii
- [x] 7.3 Testy: dwie instancje jednego wpisu dają dwa podpisane odczyty

## 8. Zapis slotu

- [x] 8.1 `grid/model.ts`: `isIndicatorSelection` przyjmuje `key` i `color` jako
      opcjonalne; wczytanie nadaje brakujący `key` i ustawia brakujący `color` na `null`
- [x] 8.2 Testy `model.test.ts`: slot zapisany w starym kształcie wczytuje się w całości;
      slot z instancjami i kolorami wraca bez zmian; zły kształt dalej odrzuca slot

## 9. Domknięcie

- [x] 9.1 `pnpm lint`, `pnpm typecheck`, `pnpm test` w `modules/terminal`
- [ ] 9.2 Sprawdzić w uruchomionym terminalu: trzy EMA (20/50/200) w trzech kolorach,
      przeżywające przeładowanie strony
- [x] 9.3 `openspec validate add-indicator-instances-and-colors --strict`
- [ ] 9.4 Gałąź, commit, pull request
