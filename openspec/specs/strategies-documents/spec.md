# strategies-documents Specification

## Purpose
Strategia jako dokument w bazie: jaki ma kształt, kiedy zostaje przyjęta, jak powstają jej rewizje i dlaczego
nic, co raz policzono, nie znika. Nowa strategia nie wymaga zmiany kodu ani wdrożenia.
## Requirements
### Requirement: Kształt dokumentu strategii

Dokument strategii MUST składać się z sekcji: `schema` (wersja języka), `name`, `hypothesis`, `notes`,
`symbol` (dokładnie jeden instrument), `timeframe` (interwał decyzji, jedna z rozdzielczości archiwum),
`params` (nazwa → wartość domyślna, minimum, maksimum, krok), `let` (zmienne nazwane jako formuły), `entries`
(co najmniej jedno wejście: strona `long` albo `short`, warunek `when`, zlecenie `market`, `limit` albo `stop`,
z formułą ceny dla dwóch ostatnich i opcjonalnym wygaśnięciem w świecach), `exits` (`stop` obowiązkowy,
opcjonalnie `target`, `trail` z progiem w R i odległością, `when`, `max_bars`), `sizing` (`risk_fraction` albo
`fixed_units`) oraz `limits` (`daily_stop_r`, `no_entry`). Sekcja albo pole spoza tej listy MUST być odrzucone,
a nie pominięte.

#### Scenario: Dokument bez stopu

- **WHEN** dokument nie ma `exits.stop`
- **THEN** dokument MUST zostać odrzucony z wyjaśnieniem, że stop wyznacza 1 R

#### Scenario: Nieznane pole

- **WHEN** dokument zawiera pole `universe`
- **THEN** dokument MUST zostać odrzucony z błędem w tej ścieżce zamiast przyjęcia z pominięciem pola

### Requirement: Dokument jest sprawdzany przy zapisie

Dokument MUST zostać zapisany wyłącznie wtedy, gdy każda formuła przechodzi walidację języka, wartości
domyślne parametrów mieszczą się w ich zakresach, zmienne w `let` nie odwołują się do siebie w kółko, a każdy
symbol i interwał, do którego dokument się odwołuje, archiwum umie podać. Instrument handlowany MUST mieć w
archiwum serię `MINUTE`. Odrzucony dokument MUST NOT zostawić żadnego śladu w bazie, a odpowiedź MUST zawierać
wszystkie błędy naraz.

#### Scenario: Symbol, którego archiwum nie zbiera

- **WHEN** formuła zawiera `close @ OIL`, a archiwum nie ma takiej serii
- **THEN** dokument MUST zostać odrzucony z błędem nazywającym brakujący symbol

#### Scenario: Cykl w zmiennych

- **WHEN** `let` definiuje `a` przez `b`, a `b` przez `a`
- **THEN** dokument MUST zostać odrzucony z błędem nazywającym obie zmienne

### Requirement: Każdy zapis to niezmienna rewizja

Pierwszy zapis strategii MUST tworzyć rewizję 1, a każdy następny zapis zmienionej treści MUST tworzyć kolejną
rewizję z hashem treści, czasem i autorem. Zapisana rewizja MUST NOT być nigdy zmieniona. Zapis treści
identycznej z ostatnią rewizją MUST NOT tworzyć nowej rewizji.

#### Scenario: Edycja strategii

- **WHEN** operator zapisuje zmieniony dokument strategii, która ma rewizję 3
- **THEN** MUST powstać rewizja 4
- **AND** rewizja 3 MUST pozostać bajt w bajt taka, jak była

#### Scenario: Ponowny zapis tej samej treści

- **WHEN** zapisywana treść jest identyczna z rewizją 4
- **THEN** MUST NOT powstać rewizja 5, a odpowiedź MUST wskazywać rewizję 4

### Requirement: Wersja schematu chroni zapisane strategie

Silnik MUST odrzucać dokument o wersji schematu wyższej niż ta, którą zna. Każdy dokument, który silnik raz
przyjął, MUST dalej dać się sprawdzić i uruchomić w każdej późniejszej wersji silnika.

#### Scenario: Dokument ze schematu przyszłego

- **WHEN** dokument deklaruje schemat wyższy niż obsługiwany
- **THEN** dokument MUST zostać odrzucony z obiema wersjami w komunikacie

#### Scenario: Dokument zapisany przy starszym schemacie

- **WHEN** silnik obsługuje nowszy schemat, a strategia ma rewizję zapisaną przy starszym
- **THEN** tę rewizję MUST dać się uruchomić bez jej przepisywania

### Requirement: Strategie się archiwizuje, nie usuwa

Strategię MUST dać się zarchiwizować i przywrócić. Zarchiwizowana MUST znikać z domyślnej listy strategii.
Strategii, jej rewizji ani jej uruchomień MUST NOT dać się usunąć przez żadną trasę pakietu, bo licznik prób
przestałby mówić prawdę.

#### Scenario: Archiwizacja

- **WHEN** operator archiwizuje strategię z pięcioma uruchomieniami
- **THEN** strategia MUST zniknąć z domyślnej listy
- **AND** jej rewizje i pięć uruchomień MUST pozostać dostępne pod jej identyfikatorem

### Requirement: Streszczenie powstaje z samego dokumentu

Dla każdego poprawnego dokumentu pakiet MUST tworzyć streszczenie po polsku, wyprowadzone deterministycznie z samego
dokumentu, bez modelu językowego i bez opisu, z którego dokument powstał. Streszczenie MUST obejmować:
- instrument i interwał decyzji;
- każde wejście: stronę, warunek, rodzaj i cenę zlecenia oraz wygaśnięcie;
- wyjścia, rozmiar i limity;
- parametry z zakresami i zmienne nazwane.

Formuły MUST być oddane słowami tam, gdzie konstrukcja albo funkcja ma swoje sformułowanie, a dosłownie tam, gdzie go
nie ma. Każda funkcja rejestru języka MUST mieć swoje sformułowanie. Interwały MUST być nazwane tak jak w terminalu
(`h4`). Godzina z formuły MUST być nazwana jako UTC, razem z godziną polską zimą i latem. `hypothesis` i `notes` MUST być
oddane dosłownie, jako założenia autora. Ten sam dokument MUST dawać zawsze to samo streszczenie.

#### Scenario: Filtr na innym interwale

- **WHEN** wejście ma warunek `ema(20) @ HOUR_4 > ema(50) @ HOUR_4`
- **THEN** streszczenie MUST mówić o EMA(20) powyżej EMA(50) na `h4` i MUST NOT zawierać `HOUR_4`

#### Scenario: Godzina w limicie

- **WHEN** `limits.no_entry` brzmi `weekday == FRIDAY and hour >= 18`
- **THEN** streszczenie MUST mówić o piątku od 18:00 UTC, czyli 19:00 zimą i 20:00 latem w Polsce

#### Scenario: Ten sam dokument dwa razy

- **WHEN** ten sam dokument jest streszczany dwa razy
- **THEN** oba streszczenia MUST być identyczne

### Requirement: Różnice między rewizjami po ścieżkach dokumentu

Pakiet MUST podawać zmiany między dwiema rewizjami jednej strategii jako listę zmian. Każda zmiana MUST nieść ścieżkę w
tej samej postaci co problemy walidacji (`entries[0].when`), rodzaj (dodane, usunięte, zmienione) oraz wartość przed i po.
Domyślnie porównanie MUST dotyczyć rewizji poprzedniej. Inna kolejność kluczy w dokumencie MUST NOT być zmianą.

#### Scenario: Zmiana stopu

- **WHEN** rewizja 5 różni się od rewizji 4 tylko stopem
- **THEN** lista zmian MUST mieć jedną pozycję pod ścieżką `exits.stop` z wartością przed i po

#### Scenario: Pierwsza rewizja

- **WHEN** porównanie dotyczy rewizji 1 bez wskazania innej
- **THEN** odpowiedź MUST mówić, że to pierwsza rewizja, zamiast zgłaszać błąd

### Requirement: Zapis wskazuje rewizję, na której się opiera

Zapis rewizji MAY wskazywać rewizję, na której oparto zmianę. Gdy ostatnia rewizja strategii jest inna niż wskazana, a
zapisywana treść różni się od ostatniej, zapis MUST zostać odrzucony jako konflikt z numerem ostatniej rewizji i MUST NOT
niczego zapisać. Zapis bez wskazanej podstawy MUST działać jak dotąd.

#### Scenario: Zapis na nieaktualnej podstawie

- **WHEN** zapis wskazuje podstawę 4, a ostatnią rewizją jest 5
- **THEN** zapis MUST zostać odrzucony z numerem 5, a rewizja 6 MUST NOT powstać

