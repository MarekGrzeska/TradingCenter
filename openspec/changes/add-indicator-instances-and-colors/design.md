## Context

Motywacja: `proposal.md`, „Why". Wymagania: delty w `specs/`.

Stan, który ta zmiana zastaje w terminalu:

- `IndicatorSelection` to `{ id, params }` (`data/types.ts`). Wybierak trzyma je w tablicy
  i wszędzie szuka po `s.id === entry.id` — checkbox, `toggle`, `setParam`. Stąd jedna
  instancja na wpis katalogu.
- `Chart.tsx` nie iteruje po selekcjach, tylko po **wynikach** (`indicatorsState.results`)
  i klucza wszystko przez `` `${result.id}|${paramsKey}` `` — serie linii, panele własne,
  linie odniesienia, wtyczki znaczników, `RayPrimitive`, `ZonePrimitive`,
  `TimeProfilePrimitive`, a także legendę pod wykresem. Wynik nie niesie niczego, co
  wskazywałoby zamawiającą go instancję.
- Kolor bierze się z `indicatorLineColor(colors, colorIndex)` — licznik rosnący w pętli
  rysowania, więc barwa linii zależy od tego, ile linii policzono przed nią.
- Slot siatki zapisuje selekcje w `localStorage`, a `grid/model.ts` waliduje wczytany
  kształt (`isIndicatorSelection`) i odrzuca slot, który się nie zgadza.

Po stronie archiwum nie ma nic do zrobienia poza testem: router liczy `body.specs` w pętli
i składa `results` w tej samej kolejności.

## Goals / Non-Goals

**Goals:**

- Instancja wskaźnika jako byt pierwszej klasy w terminalu, z tożsamością niezależną od
  `id` i parametrów.
- Kolor wybierany przez operatora, stabilny wobec dokładania i usuwania innych instancji.
- Slot zapisany przed tą zmianą wczytuje się bez utraty wskaźników.

**Non-Goals:**

- Kolor na drucie. `market_data/contract.py` zostaje nietknięty; archiwum nie wie
  o kolorach i nie ma po co wiedzieć.
- Kolor dla kształtów innych niż linia. Strefy rysują się barwą kierunku (`up`/`down`),
  profil czasu ma własny kolor punktu kontrolnego — to nie jest wybór operatora i ta
  zmiana go nie rusza. Kolor instancji dotyczy linii, znaczników i poziomów.
- Grubość, styl kreski, przezroczystość. Jedna oś wyboru naraz.
- Kolejność rysowania instancji, przeciąganie ich na liście, grupowanie.

## Decisions

### Instancja ma własny klucz, a nie klucz wyprowadzony z (id, parametry)

`IndicatorSelection` dostaje `key: string` — nadawany przy dodaniu, niosący się przez
zapis slotu, nigdy nie liczony z zawartości.

Rozważane i odrzucone: klucz wyprowadzony z `` `${id}|${params}` ``, czyli to, czym
`Chart.tsx` posługuje się dziś. Kusi, bo nie wymaga nowego pola i pasuje do istniejących
map. Przegrywa na dodawaniu: druga instancja EMA powstaje z parametrami domyślnymi, więc
w chwili dodania jest identyczna z pierwszą — trzeba by albo odmówić dodania, albo zgadywać
inny okres za operatora, albo znieść stan, w którym dwie instancje mają jeden klucz
i nadpisują sobie serie. Klucz własny znosi cały ten problem, a przy okazji daje Reactowi
stabilny `key` na liście, której elementy operator usuwa ze środka.

Wartość klucza: `crypto.randomUUID()`, dostępne w przeglądarce i w jsdom. Testy, które
potrzebują przewidywalności, budują selekcje same — klucz jest zwykłym stringiem.

### Wynik wiąże się z instancją po pozycji w odpowiedzi

`Chart.tsx` przestaje szukać instancji po `result.id` i `result.params`. Zamawiane
instancje i zwrócone wyniki zestawiane są po indeksie — n-ty wynik należy do n-tej
zamówionej instancji. Dlatego ta zmiana dokłada wymaganie kolejności do
`market-data-indicators`: terminal zaczyna na niej polegać, a spec dotąd jej nie obiecywał.

Rozważane i odrzucone: dokładanie do kontraktu pola z kluczem instancji
(`IndicatorSpecIn.key`, przepisywane na `IndicatorResultOut`). Uczciwsze wobec zestawiania,
ale wpuszcza pojęcie terminala do kontraktu modułu, który nic o instancjach nie wie,
i uruchamia całą pięcioprzystankową trasę pola na drucie — łącznie z regeneracją kontraktu
i snapshotem w `market-mcp` — po coś, co kolejność już daje.

Pułapka, którą trzeba obsłużyć: `useIndicators` trzyma wyniki poprzedniego odczytu, gdy
selekcje już się zmieniły (nowa instancja dodana, odczyt w locie). Zestawienie po indeksie
z **bieżącą** tablicą selekcji da wtedy złe pary. Dlatego `useIndicators` MUST zwracać
w swoim stanie także tablicę selekcji, dla której te wyniki policzono — jeden spójny
snapshot `{ times, results, selections }`, i to jego czyta pętla rysująca. Wiązanie po
`(id, params)` tej pułapki nie miało, więc jest to koszt tej decyzji, nie jej skutek
uboczny do przemilczenia.

### Klucze rysowania biorą się z klucza instancji

Wszystkie mapy w `Chart.tsx` przechodzą z `` `${result.id}|${paramsKey}` `` na
`selection.key`, a serie linii na `` `${selection.key}|${lineSpec.key}` ``. Pętle sprzątające
zostają bez zmian — dalej usuwają to, czego nie ma w zbiorze aktywnych kluczy. Efekt
uboczny na plus: zmiana okresu instancji przestaje tworzyć nowy klucz, więc seria jest
przestawiana zamiast usuwana i budowana od zera.

### Kolor zapisywany jako nazwa tokenu palety, nie jako hex

`IndicatorSelection` dostaje `color: string | null`, gdzie wartością jest nazwa tokenu
z `INDICATOR_LINE_TOKENS` w `theme.ts` (`--color-accent`, `--color-indicator-5`, …).
`theme.ts` eksportuje tę listę i funkcję rozwiązującą token na barwę bieżącego motywu.

Rozważane i odrzucone: zapis surowego hexa. Zrywa jedyne wiązanie między motywem
a wykresem, które ten plik istnieje po to, żeby trzymać — zapisany `#3987e5` przestałby
podążać za tokenem, gdyby ten się zmienił. Odrzucony też indeks slotu palety (0–7): krótszy,
ale przestawienie kolejności palety przemalowałoby zapisane sloty, a ta kolejność jest
wynikiem walidatora kontrastu i może się jeszcze zmienić.

`null` znaczy „przydziel sam" i zostaje zachowaniem domyślnym: instancje bez wybranego
koloru dostają kolejne barwy z cyklu, jak dziś. Licznik cyklu MUST pomijać kolory już
wybrane ręcznie, żeby samoczynny przydział nie trafił w tę samą barwę, co sąsiednia
instancja wybrana przez operatora.

Wybierak dostaje rząd ośmiu próbek pod parametrami instancji — `<button>` na próbkę,
`aria-pressed` na wybranej, plus możliwość powrotu do przydziału samoczynnego.

### Odczyt zapisanego slotu przyjmuje stary kształt

`grid/model.ts` waliduje dziś selekcję jako `{ id, params }`. Nowa walidacja przyjmuje
`key` i `color` jako opcjonalne: brak `key` → nadany przy wczytaniu, brak `color` → `null`.
Stary slot wczytuje się w całości, bez ekranu „konfiguracja nieczytelna".

Rozważane i odrzucone: numer wersji zapisu i osobna migracja. Kształt różni się dwoma
polami opcjonalnymi — wersjonowanie kosztowałoby więcej niż to, co ma opisać.

## Risks / Trade-offs

- **Terminal polega na kolejności wyników, której nie widać w typach** → wymaganie
  w `market-data-indicators` plus test po stronie archiwum (dwa identyczne zamówienia →
  dwa wyniki na swoich pozycjach) i test terminala na zestawianiu po indeksie.
- **Snapshot selekcji w `useIndicators` może się rozjechać z tym, co pokazuje wybierak** —
  operator dodał instancję, wykres jej jeszcze nie rysuje, bo odczyt trwa. To jest stan
  poprawny i dziś już istniejący (wykres pokazuje ostatnio policzone), ale teraz obejmuje
  też kolor: przemalowanie widać dopiero po przeliczeniu → kolor rozwiązywany przy
  rysowaniu z **bieżących** selekcji po kluczu instancji, a nie ze snapshotu, więc zmiana
  koloru działa natychmiast, bez odczytu.
- **Sufit żądania jest liczony jako świece × wskaźniki** (`REQUEST_CEILING` w routerze) —
  operator dokładający instancje szybciej w niego trafi. Zachowanie już opisane
  (`terminal-chart`, „Wykres mówi, gdy wskaźników nie da się policzyć"): odmowa pokazuje
  się operatorowi. Ta zmiana nie rusza sufitu.
- **Osiem kolorów, nieskończenie wiele instancji** → cykl powtarza barwy, tak jak dziś.
  Rozróżnienie niesie legenda z parametrami, nie sama barwa.
