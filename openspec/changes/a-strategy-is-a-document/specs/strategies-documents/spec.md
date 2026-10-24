## Purpose

Strategia jako dokument w bazie: jaki ma kształt, kiedy zostaje przyjęta, jak powstają jej rewizje i dlaczego
nic, co raz policzono, nie znika. Nowa strategia nie wymaga zmiany kodu ani wdrożenia.

## ADDED Requirements

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
