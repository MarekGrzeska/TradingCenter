## Purpose

Język formuł, w którym zapisane są warunki, ceny i odległości w dokumencie strategii: co da się w nim wyrazić,
jak silnik rozumie serie, interwały, inne instrumenty i czas, i dlaczego przyszłości nie da się w nim zapisać.

## ADDED Requirements

### Requirement: Formuła jest parsowana, nigdy wykonywana

Formuła MUST być wyrażeniem w składni wyrażeń Pythona i MUST być przyjmowana tylko wtedy, gdy składa się
wyłącznie z konstrukcji z zamkniętej listy: liczby, nazwy, działania `+ - * /`, jednoargumentowy minus,
porównania (także łańcuchowe, jak `7 <= hour < 20`), `and`, `or`, `not`, wyrażenie warunkowe `a if c else b`,
wywołanie funkcji z listy języka, pole (`bbands(20, 2).upper`, `p.fast`), indeks `[n]` oraz operator `@`.
Stała tekstowa MAY wystąpić wyłącznie jako prawy operand `@`. Każda inna konstrukcja MUST być odrzucona przy
zapisie. Tekst formuły MUST NOT trafić do żadnego mechanizmu wykonującego kod; silnik MUST interpretować
wyłącznie sprawdzone drzewo.

#### Scenario: Formuła z dozwolonych konstrukcji

- **WHEN** dokument zawiera `ema(20) @ HOUR_4 > ema(50) @ HOUR_4 and close[1] < low[2]`
- **THEN** formuła MUST zostać przyjęta

#### Scenario: Konstrukcja spoza listy

- **WHEN** formuła zawiera `__import__("os")`, `lambda`, wyrażenie listowe, przypisanie albo wycinek `[1:5]`
- **THEN** dokument MUST zostać odrzucony
- **AND** błąd MUST wskazywać sekcję, formułę i kolumnę, w której stoi niedozwolona konstrukcja

### Requirement: Serie, przesunięcia i okna

Każda nazwa serii (`open`, `high`, `low`, `close`, `volume`) i każda formuła na seriach MUST mieć wartość na
każdej świecy osi, w której jest liczona: domyślnie na osi interwału decyzji strategii. Indeks `[n]` MUST
oznaczać wartość sprzed `n` świec tej osi, a `n` MUST być nieujemną stałą całkowitą albo parametrem. Długość
okna funkcji okienkowej MUST być dodatnią stałą całkowitą albo parametrem. Przesunięcie i okno MUST NOT
przekraczać 5000 świec.

#### Scenario: Przesunięcie wstecz

- **WHEN** formuła `close[1]` jest liczona na świecy *t*
- **THEN** jej wartość MUST być zamknięciem świecy *t − 1* tej samej osi

#### Scenario: Indeks ujemny

- **WHEN** formuła zawiera `close[-1]` albo przesunięcie wyliczane z innej formuły
- **THEN** dokument MUST zostać odrzucony z błędem mówiącym, że język nie sięga w przyszłość

### Requirement: Zamknięta lista funkcji, otwarta na katalog wskaźników

Język MUST oferować dokładnie te funkcje własne: czas świecy (`hour`, `minute`, `weekday` ze stałymi `MONDAY`
… `SUNDAY`, liczone od początku świecy, UTC), okna (`highest`, `lowest`, `sum`, `average`), zdarzenia
(`crosses_above`, `crosses_below`, `rising`, `falling`, `bars_since`, `value_when`, `highest_since`,
`lowest_since`), działania (`abs`, `min`, `max`) oraz `stale` i `at_entry`.

Każdy wpis katalogu wskaźników archiwum, którego wyjściem są linie, MUST być funkcją o nazwie swojego
identyfikatora, z parametrami katalogu podawanymi pozycyjnie w kolejności katalogu albo po nazwie. Wskaźnik o
kilku liniach MUST wymagać wyboru linii polem. Wpis z innym wyjściem (znaczniki, strefy, poziomy) MUST być
odrzucony z wyjaśnieniem. Nowy wpis katalogu MUST być dostępny w formułach bez zmiany silnika. Nazwa ze
zmiennych dokumentu MUST NOT przesłaniać nazwy funkcji ani serii.

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wpis z wyjściem liniowym
- **THEN** formuła wywołująca go po identyfikatorze MUST przejść walidację bez zmiany kodu pakietu strategii

#### Scenario: Wskaźnik wielolinijkowy bez wyboru linii

- **WHEN** formuła zawiera `bbands(20, 2) > close`
- **THEN** dokument MUST zostać odrzucony z podpowiedzią, które linie można wybrać

#### Scenario: Parametr wskaźnika poza zakresem katalogu

- **WHEN** formuła zawiera `ema(1)`, a katalog dopuszcza okres od 2
- **THEN** dokument MUST zostać odrzucony z zakresem podanym przez katalog

### Requirement: Inny interwał i inny instrument

Operator `@` MUST liczyć swój lewy operand w kontekście innego interwału (prawy operand jest nazwą
rozdzielczości archiwum: `MINUTE` … `WEEK`) albo innego instrumentu (każda inna nazwa albo stała tekstowa).
Oba konteksty MAY się łączyć (`close @ US500 @ DAY`). Wynik MUST być dopasowany do osi, na której stoi
wyrażenie: w chwili decyzji *t* MUST obowiązywać ostatni punkt tamtej serii, który był dostępny najpóźniej w *t*.
Świeca jeszcze się formująca MUST NOT być widoczna. `stale(x)` MUST zwracać prawdę, gdy ostatni dostępny punkt
`x` jest starszy niż jeden okres jego rozdzielczości.

#### Scenario: Wyższy interwał w środku jego świecy

- **WHEN** strategia na `HOUR` liczy `close @ HOUR_4` na świecy kończącej się o 10:00 UTC
- **THEN** wartość MUST pochodzić ze świecy H4 zamkniętej o 08:00 UTC, nie z tej, która trwa

#### Scenario: Rynek drugiego instrumentu zamknięty

- **WHEN** strategia na BTCUSD liczy `close @ US100` w sobotę
- **THEN** wartość MUST być zamknięciem ostatniej świecy US100 sprzed zamknięcia rynku
- **AND** `stale(close @ US100)` MUST być prawdą

### Requirement: Wartość jest widoczna od chwili, w której była dostępna

Każdy punkt serii MUST nieść, poza okresem, którego dotyczy, chwilę, od której był dostępny. Silnik MUST
pokazywać formule wyłącznie punkty dostępne najpóźniej w chwili decyzji. Dla świec archiwum chwilą dostępności
MUST być koniec okresu świecy.

#### Scenario: Seria publikowana z opóźnieniem

- **WHEN** seria ma punkt za dzień *D*, dostępny dopiero w *D + 1* o 14:00 UTC
- **THEN** formuła liczona w *D + 1* o 13:00 UTC MUST widzieć poprzedni punkt tej serii, nie punkt za *D*

### Requirement: Stan pozycji i historia transakcji

Język MUST udostępniać stan otwartej pozycji (`position` ze stałymi `LONG`, `SHORT`, `FLAT`, `entry_price`,
`bars_in_trade`, `open_r`, `at_entry(x)` — wartość formuły `x` na świecy wejścia) oraz historię zamkniętych
transakcji (`losses_in_row`, `last_trade_r`, `trades_today`, z dniem liczonym w UTC). Nazwy opisujące otwartą
pozycję MUST być dopuszczone tylko tam, gdzie pozycja istnieje: w wyjściach. Ich użycie w warunku wejścia albo
w limitach MUST być odrzucone przy zapisie.

#### Scenario: Stop z wartości na wejściu

- **WHEN** stop jest zapisany jako `entry_price - 2 * at_entry(atr(14))`
- **THEN** jego odległość MUST wynikać z wartości ATR na świecy wejścia i MUST NOT zmieniać się razem z bieżącym ATR

#### Scenario: Stan pozycji w warunku wejścia

- **WHEN** warunek wejścia zawiera `entry_price`
- **THEN** dokument MUST zostać odrzucony z wyjaśnieniem, że przed wejściem pozycji nie ma

### Requirement: Typy i błędy, które da się poprawić bez zgadywania

Każda formuła MUST mieć sprawdzony typ: miejsca warunków MUST wymagać warunku, a miejsca cen i odległości
liczby. Walidacja MUST zwracać wszystkie błędy dokumentu naraz, a każdy błąd MUST nieść ścieżkę w dokumencie
(np. `entries[0].when`), kolumnę w formule i komunikat. Dla nieznanej nazwy MUST podawać najbliższą znaną,
jeśli taka istnieje.

#### Scenario: Literówka w nazwie funkcji

- **WHEN** formuła zawiera `emaa(20)`
- **THEN** błąd MUST nazywać `emaa` jako nieznaną funkcję i podpowiadać `ema`

#### Scenario: Liczba w miejscu warunku

- **WHEN** warunek wejścia brzmi `close - open`
- **THEN** dokument MUST zostać odrzucony z błędem typu w tej ścieżce
