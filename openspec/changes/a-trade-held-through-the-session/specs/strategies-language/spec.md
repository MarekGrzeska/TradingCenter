## MODIFIED Requirements

### Requirement: Zamknięta lista funkcji, otwarta na katalog wskaźników

Język MUST oferować dokładnie te funkcje własne: czas świecy (`hour`, `minute`, `weekday` ze stałymi `MONDAY`
… `SUNDAY`, liczone od początku świecy, UTC), sesję (`session_bar`, `minutes_to_session_close` z nazwami sesji
`NEW_YORK`, `LONDON`, `TOKYO`), okna (`highest`, `lowest`, `sum`, `average`), zdarzenia
(`crosses_above`, `crosses_below`, `rising`, `falling`, `bars_since`, `value_when`, `highest_since`,
`lowest_since`), działania (`abs`, `min`, `max`) oraz `stale` i `at_entry`.

Każdy wpis katalogu wskaźników archiwum, którego wyjściem są linie, MUST być funkcją o nazwie swojego
identyfikatora, z parametrami katalogu podawanymi pozycyjnie w kolejności katalogu albo po nazwie. Wskaźnik o
kilku liniach MUST wymagać wyboru linii polem. Wpis z innym wyjściem (znaczniki, strefy, poziomy) MUST być
odrzucony z wyjaśnieniem. Nowy wpis katalogu MUST być dostępny w formułach bez zmiany silnika. Nazwa ze
zmiennych dokumentu MUST NOT przesłaniać nazwy funkcji, serii ani sesji.

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wpis z wyjściem liniowym
- **THEN** formuła wywołująca go po identyfikatorze MUST przejść walidację bez zmiany kodu pakietu strategii

#### Scenario: Wskaźnik wielolinijkowy bez wyboru linii

- **WHEN** formuła zawiera `bbands(20, 2) > close`
- **THEN** dokument MUST zostać odrzucony z podpowiedzią, które linie można wybrać

#### Scenario: Parametr wskaźnika poza zakresem katalogu

- **WHEN** formuła zawiera `ema(1)`, a katalog dopuszcza okres od 2
- **THEN** dokument MUST zostać odrzucony z zakresem podanym przez katalog

## ADDED Requirements

### Requirement: Sesja liczona zegarem w swojej strefie

Język MUST znać trzy nazwane sesje, od poniedziałku do piątku w czasie lokalnym sesji, z tymi samymi strefami i
godzinami co strefy sesji rysowane na wykresie: `NEW_YORK` (America/New_York, 9:30–16:00), `LONDON` (Europe/London,
8:00–16:30) i `TOKYO` (Asia/Tokyo, 9:00–15:00). Godziny sesji MUST być liczone w jej strefie razem ze zmianami czasu,
a nie stałym przesunięciem od UTC. Nazwa sesji MUST być dopuszczona wyłącznie jako argument funkcji sesji.

- `session_bar(S)` MUST dawać numer świecy osi w dzisiejszej sesji `S`, liczony zegarem: 1 dla pierwszej świecy, która
  zaczyna się o otwarciu sesji albo po nim, i o jeden więcej co okres osi. Świeca zaczynająca się poza sesją MUST
  mieć 0. Brak świecy w danych MUST NOT przesuwać numeracji następnych.
- `minutes_to_session_close(S)` MUST dawać liczbę minut od chwili decyzji (końca świecy) do zamknięcia sesji `S` w
  lokalnym dniu tej chwili. Po zamknięciu wartość MUST być ujemna. W dniu bez sesji (sobota, niedziela) MUST być
  pusta.

Funkcja sesji liczona na osi `DAY` albo `WEEK`, także przez `@`, MUST zostać odrzucona przy zapisie, bo jedna świeca
obejmuje tam całą sesję.

#### Scenario: Pierwsza świeca M5 sesji nowojorskiej

- **WHEN** strategia na `MINUTE_5` liczy `session_bar(NEW_YORK)` 2 lipca 2026
- **THEN** świeca 13:30–13:35 UTC (9:30 w Nowym Jorku) MUST mieć wartość 1
- **AND** świeca 13:35–13:40 UTC MUST mieć wartość 2, a świeca 13:25–13:30 UTC wartość 0

#### Scenario: Europa zmienia czas przed USA

- **WHEN** strategia na `MINUTE_5` liczy `session_bar(NEW_YORK)` 27 października i 1 grudnia 2026
- **THEN** wartość 1 MUST mieć 27 października świeca 13:30 UTC (14:30 w Polsce), a 1 grudnia świeca 14:30 UTC (15:30
  w Polsce)

#### Scenario: Brak świecy otwarcia

- **WHEN** w danych danego dnia nie ma świecy M5 zaczynającej się o 9:30 w Nowym Jorku
- **THEN** świeca 9:35 MUST mieć `session_bar(NEW_YORK)` równe 2, a żadna świeca tego dnia MUST NOT mieć 1

#### Scenario: Minuty do zamknięcia

- **WHEN** decyzja zapada na końcu świecy kończącej się o 15:55 w Nowym Jorku
- **THEN** `minutes_to_session_close(NEW_YORK)` MUST wynosić 5
- **AND** na świecy kończącej się o 16:10 tego dnia MUST wynosić −10

#### Scenario: Funkcja sesji na osi dziennej

- **WHEN** formuła zawiera `session_bar(NEW_YORK) @ DAY`
- **THEN** dokument MUST zostać odrzucony z wyjaśnieniem, że świeca dzienna obejmuje całą sesję

#### Scenario: Nazwa sesji poza funkcją sesji

- **WHEN** formuła zawiera `close > NEW_YORK` albo `highest(close, NEW_YORK)`
- **THEN** dokument MUST zostać odrzucony z błędem w tej ścieżce

#### Scenario: Te same godziny co na wykresie

- **WHEN** porównuje się sesje języka z domyślnymi strefami i godzinami stref sesji katalogu wskaźników
- **THEN** każda sesja języka MUST mieć tę samą strefę, otwarcie i zamknięcie co jej odpowiednik w katalogu
