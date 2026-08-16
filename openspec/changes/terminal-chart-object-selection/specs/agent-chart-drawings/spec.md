## MODIFIED Requirements

### Requirement: Rysunek należy do instrumentu, nie do widoku

Rysunek MUST być przypisany do instrumentu i MUST być niezależny od interwału oraz od
slotu, w którym akurat widać ten instrument. Opór jest ceną, a nie własnością pięciu minut
— ten sam rysunek MUST być widoczny na każdym wykresie tego instrumentu.

Moduł MUST znać trzy kształty rysunku:

- **poziom** — jedna cena, opcjonalnie z momentem, od którego obowiązuje;
- **strefa** — przedział między dwiema cenami, opcjonalnie z momentem początku i końca;
- **linia trendu** — dwa punkty, każdy z czasem i ceną.

Każdy rysunek MAY nieść etykietę i MUST nieść kolor z **palety rysunków** albo nie nieść
go wcale. Kolor spoza palety jest kolorem, którego wykres nie umie narysować.

Paleta rysunków MUST być odrębna od palety, którą terminal koloruje wskaźniki. Rysunek jest
ustaleniem operatora, a wskaźnik odczytem z archiwum; dwie rzeczy tego rodzaju rysowane
tym samym kolorem na jednym wykresie są nierozróżnialne dokładnie wtedy, kiedy rozróżnienie
jest potrzebne. Paleta MUST nieść na tyle barw, żeby rysunki stojące obok siebie dało się
od siebie odróżnić.

Rysunek MUST być kompletny w chwili powstania: strefa bez drugiej ceny albo linia trendu
z jednym punktem nie jest rysunkiem, którego brakującą część dałoby się później dopisać.

#### Scenario: Ten sam poziom na dwóch interwałach

- **WHEN** agent stawia poziom na instrumencie oglądanym w MINUTE_5, a operator przełącza na HOUR
- **THEN** poziom jest widoczny nadal, na tej samej cenie

#### Scenario: Ten sam poziom w dwóch slotach

- **WHEN** dwa sloty pokazują ten sam instrument
- **THEN** oba pokazują ten sam zestaw rysunków

#### Scenario: Strefa bez drugiej ceny

- **WHEN** agent próbuje postawić strefę podając jedną cenę
- **THEN** rysunek nie powstaje

#### Scenario: Kolor z palety rysunków

- **WHEN** agent stawia rysunek podając kolor z palety rysunków
- **THEN** rysunek powstaje w tym kolorze

#### Scenario: Kolor spoza palety rysunków

- **WHEN** agent stawia rysunek podając kolor, którego paleta rysunków nie zna
- **THEN** dostaje odmowę nazywającą ten kolor
- **AND** rysunek nie powstaje
