## Verdict

Wszystko z propozycji weszło: jeden wpis katalogu można włączyć wiele razy, każda instancja
ma własne parametry, własny kolor z palety motywu i własne usunięcie, a slot pamięta to
przez przeładowanie. Archiwum nie dostało ani jednej linii kodu — tylko wymaganie
kolejności wyników i trzy testy, które je pilnują, bo terminal zaczął na tej kolejności
polegać. Dwie rzeczy świadome, nie przeoczenia: **kolor dotyczy pierwszej linii wpisu**
(MACD dalej bierze pozostałe z cyklu — trzy linie w jednym kolorze nie mówią nic), oraz
**seria histogramowa nie przyjmuje koloru instancji**, bo maluje się per słupek kolorem
znaku. Zadanie 9.2 — sprawdzenie w uruchomionym terminalu — domknięte później, na żywym
stacku operatora; patrz addendum na końcu, bo wyszło z niego więcej niż samo odhaczenie.

## Verified

| Komenda | Wynik |
|---|---|
| `modules/terminal`: `pnpm lint` | czysto (0 błędów, 0 ostrzeżeń) |
| `modules/terminal`: `pnpm typecheck` | czysto |
| `modules/terminal`: `pnpm test` | 43 pliki, **557 testów, wszystkie zielone** |
| `modules/market-data`: `uv run ruff check .` | `All checks passed!` |
| `modules/market-data`: `uv run pytest` | **1022 passed, 7 skipped** |
| `modules/market-data`: `uv run pytest tests/test_indicators_router.py -m db -k ResultOrder` | **3 passed** (testcontainers) |
| `openspec validate add-indicator-instances-and-colors --strict` | valid |

Nie uruchamiane: `-m live` (z założenia). Ręczne sprawdzenie w przeglądarce (9.2) zostało
przeprowadzone później — patrz addendum na końcu; liczba testów terminala urosła od tamtej
pory do **580**, wraz z testami, które z tego przebiegu wynikły.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoki | `Chart.tsx` `assignLineColors` | Kolor bieżącej selekcji był brany jako `chosenByKey.get(key) ?? selection.color`. `??` przepuszcza `null`, a `null` to właśnie „Auto" — instancja odtworzona z zapisanego slotu z kolorem po kliknięciu **Auto** dalej rysowałaby się starym kolorem aż do następnego przeliczenia. Zamienione na `has()`. | **FIXED**, wraz z testem `Chart.test.tsx::"clears a restored colour back to the cycle when the operator picks Auto"` |
| Wysoki | `useIndicators.ts` | Efekt zależał od tablicy selekcji, więc **wybór koloru odpalał odczyt archiwum**. Wyszło z padającego testu „repaints a line the moment its colour is picked". Efekt kluczowany teraz na `key\|id\|params`, kolor rozwiązywany przy rysowaniu z bieżących selekcji. | **FIXED** w tym samym commicie co reszta |
| Średni | `testDoubles.ts` `makeFakeSeries` | Podwójka serii nie miała `applyOptions`, więc przemalowanie istniejącej serii wywracało każdy test wykresu (`TypeError: series.applyOptions is not a function`). Dołożone razem z zapisem opcji, co jest też tym, czym testy koloru mierzą wynik. | **FIXED** |
| Niski | `Chart.tsx` pętla rysująca | Efekt uboczny przejścia na klucz instancji: zmiana okresu nie tworzy już nowego klucza serii, więc seria jest przestawiana zamiast usuwana i budowana od zera. Zmiana na plus, odnotowana, żeby nie czytać jej jako przypadku. | — |

Poza tym z przeglądu diffu: brak. Pętla sprzątająca, panele własne, prymitywy i linie
odniesienia przeszły na `selection.key` jednym ruchem i mają swoje istniejące testy
(deselekcja, zmiana symbolu, dwa panele własne) — wszystkie dalej zielone.

## Spec coverage

**`terminal-chart` — Operator wybiera wskaźniki z tego, co oferuje źródło (MODIFIED)**

| Requirement / Scenario | Proven by |
|---|---|
| Lista pochodzi ze źródła | `Chart.test.tsx::"builds the picker from the catalogue, not from a hand-kept list"` |
| Wskaźnik dołożony po stronie źródła | `Chart.test.tsx::"builds the picker from the catalogue, not from a hand-kept list"` |
| Parametr poza zakresem | `IndicatorPicker.test.tsx::"keeps a param out of range from reaching the selection, and says which range"` |
| Ta sama średnia w kilku okresach | `IndicatorPicker.test.tsx::"draws the same average three times, each with its own period"`; `Chart.test.tsx::"draws the same entry twice, each instance with its own values"` |
| Parametr jednej instancji | `IndicatorPicker.test.tsx::"changes the period of one instance and leaves the others where they were"` |
| Usunięcie jednej instancji | `IndicatorPicker.test.tsx::"removes one instance and keeps the rest"` |
| Dwie instancje o identycznych parametrach są dozwolone (zdanie wymagania, nie scenariusz) | `IndicatorPicker.test.tsx::"adds a second instance carrying the catalogue's defaults, without refusing the duplicate"` |

**`terminal-chart` — Wykres podaje wartości wskaźników spod kursora (MODIFIED)**

| Requirement / Scenario | Proven by |
|---|---|
| Kursor nad świecą | `Chart.test.tsx::"shows an own-pane indicator's value under the cursor beside OHLC, same as a price-pane one"` |
| Kursor poza serią | `Chart.test.tsx::"follows the forming candle as it moves within one period"` (istniejący, świeżość odczytu) |
| Kursor przy kilku instancjach jednego wpisu | `Chart.test.tsx::"gives the crosshair readout one entry per instance, each labelled with its own params"` |

**`terminal-chart` — Kolor wskaźnika wybiera operator (ADDED)**

| Requirement / Scenario | Proven by |
|---|---|
| Operator ustawia kolor | `Chart.test.tsx::"paints an instance in the colour the operator chose, and leaves the other to the cycle"`; `IndicatorPicker.test.tsx::"stores the chosen colour as a palette token on that instance alone"` |
| Kolor przeżywa dołożenie innego wskaźnika | `Chart.test.tsx::"keeps a chosen colour when another instance is added afterwards"` |
| Instancja bez wybranego koloru | `Chart.test.tsx::"paints an instance in the colour the operator chose, and leaves the other to the cycle"` (druga asercja: barwa z palety, różna od wybranej) |
| Dwie instancje w różnych kolorach | `Chart.test.tsx::"draws two instances of one entry in two colours the operator picked"` |
| Kolor spoza palety MUST NOT być przyjęty | `theme.test.ts::"refuses a token the palette does not offer"`; `gridStore.test.ts::"reads a colour the palette no longer offers as no colour, rather than losing the slot"` |
| Kolor MUST NOT zmieniać się przy przeliczaniu innych | `Chart.test.tsx::"repaints a line the moment its colour is picked, without asking the archive again"`; `IndicatorPicker.test.tsx::"marks the chosen swatch and clears it again on Auto"` |

**`terminal-grid` — Slot ma własny instrument i własny interwał (MODIFIED)**

| Requirement / Scenario | Proven by |
|---|---|
| Ten sam instrument w kilku interwałach | `GridView.test.tsx::"changes one slot's resolution without disturbing the others"` (istniejący) |
| Rozdzielczości do wyboru w slocie | `GridView.test.tsx::"limits the resolution selector to what the instrument is archived in"` (istniejący) |
| Slot pusty | `GridView.test.tsx::"invites a choice in an empty slot instead of drawing an empty chart"` (istniejący) |
| Różne wskaźniki w dwóch slotach | `GridView.test.tsx::"restores a slot's chosen indicators across a remount, the same as its instrument"` (istniejący, rozszerzony o kolor) |
| Powrót do terminala z zapisanymi wskaźnikami | `GridView.test.tsx::"restores a slot's chosen indicators across a remount, the same as its instrument"` |
| Powrót do terminala z kilkoma instancjami jednego wpisu | `gridStore.test.ts::"keeps three instances of one entry, each with its own params and colour"` — **na poziomie magazynu, nie interfejsu** (patrz Gaps) |
| Slot zapisany przed instancjami i kolorami | `gridStore.test.ts::"reads a slot saved before indicators had instances or colours"` |
| Zapamiętany wskaźnik zniknął z katalogu | `Chart.test.tsx::"skips a saved selection the catalogue no longer offers, and says so, without discarding it from the next save"` (istniejący) |

**`market-data-indicators` — Jedno żądanie liczy wiele wskaźników na wspólnej osi czasu (MODIFIED)**

| Requirement / Scenario | Proven by |
|---|---|
| Kilka wskaźników naraz | `test_indicators_router.py::TestResultOrder::test_results_come_back_in_the_order_they_were_asked_for`; `::TestPartialAnswer::test_a_missing_series_leaves_the_rest_computed` (istniejący) |
| Ten sam wskaźnik z różnymi parametrami | `test_indicators_router.py::TestResultOrder::test_results_come_back_in_the_order_they_were_asked_for` (ema 20 i ema 5 w jednym żądaniu) |
| Kolejność wyników | `test_indicators_router.py::TestResultOrder::test_results_come_back_in_the_order_they_were_asked_for` |
| Dwa identyczne zamówienia | `test_indicators_router.py::TestResultOrder::test_two_identical_specs_answer_on_their_own_positions` |
| Wynik z przyczyną trzyma swoją pozycję (zdanie wymagania) | `test_indicators_router.py::TestResultOrder::test_a_failing_spec_holds_its_position` |
| Terminal nie wysyła `key` ani `color` na drut | `archive.test.ts::"keeps the instance key and the chosen colour off the wire"` |
| Migawka wyników i selekcji nie rozjeżdża się w trakcie odczytu | `useIndicators.test.ts::"does not pair fresh selections with results computed before them"`, `::"keeps the failed read's last good snapshot whole"` |

## Gaps

- **Trzy instancje jednego wpisu przez przeładowanie sprawdzone na poziomie magazynu,
  nie interfejsu.** `gridStore.test.ts` dowodzi, że zapis i odczyt zachowują wszystkie
  trzy z parametrami i kolorami; `GridView.test.tsx` przechodzi tę samą drogę przez
  interfejs, ale z jedną instancją. Luka jest wąska (między nimi nie ma kodu, którego
  któryś z nich nie dotyka), ale jest.
- ~~**Zadanie 9.2 niezamknięte**~~ — **domknięte**, patrz addendum niżej.
- **Kolor a kształty inne niż linia**: strefy rysują się barwą kierunku, profil czasu ma
  własny kolor punktu kontrolnego, a seria histogramowa maluje się per słupek. Kolor
  instancji dociera do linii, znaczników i poziomów — to Non-Goal z `design.md`, nie
  przeoczenie.

## Addendum — 9.2 domknięte w uruchomionym terminalu

Sprawdzone na żywym stacku operatora: **cztery SMA (20/50/100/200), każda w swoim kolorze
z palety**, narysowane w jednym slocie naraz i przeżywające przeładowanie strony. Zakres
formalny 9.2 mówił o trzech EMA; sprawdzona została mocniejsza wersja tego samego zdania
(cztery instancje jednego wpisu, cztery różne kolory), więc zadanie odhaczone. Instancje
trafiły na wykres przez narzędzie agenta (`add-agent-chart-control`), nie przez wybierak —
co jest ostrzejszym testem tej zmiany niż zaplanowany, bo omija ścieżkę, którą przechodzą
wszystkie testy `IndicatorPicker`.

Przy okazji tego przebiegu wyszła i została naprawiona jedna rzecz należąca do **tej**
zmiany, nie do agenta: odczyt wartości pod kursorem trzymał wszystkie instancje w jednym
ciągu w nagłówku. Teraz grupuje je po typie wskaźnika — kilka SMA obok siebie w jednym
wierszu, inny wskaźnik zawsze w swoim — zaokrągla do dwóch miejsc po przecinku, używa
`tabular-nums` (proporcjonalne cyfry przesuwały próbki koloru w poziomie przy każdej
zmianie wartości) i jest nakładką nad wykresem zamiast elementu nagłówka. To ostatnie było
realnym błędem, nie kosmetyką: wysokość odczytu wchodziła w układ, więc przełamanie wiersza
przy zmianie szerokości liczby zmieniało wysokość kontenera wykresu i uruchamiało
`chart.resize()` w środku przeciągania. Testy: `Chart.test.tsx::"puts several instances of
one indicator on one readout row, and a different indicator on its own"`, `::"draws the
readout over the chart rather than in the header, so its height cannot resize the chart"`,
`::"keeps showing the newest known indicator value once the pointer leaves the chart…"`.

**Luka, która została:** trzy instancje przez przeładowanie dalej mają dowód na poziomie
magazynu (`gridStore.test.ts`) i jedną instancję na poziomie interfejsu (`GridView.test.tsx`)
— ręczny przebieg pokrył to od strony operatora, ale nie zostawił po sobie testu.
