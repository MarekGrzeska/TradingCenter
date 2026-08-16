## Purpose

Rysunki, które agent zostawia na wykresie operatora: wsparcia, opory, strefy i linie
trendu — ich kształty, przypisanie do instrumentu, trwałość, narzędzia którymi agent je
stawia i odczytuje, oraz to, jak operator je widzi i cofa.

## ADDED Requirements

### Requirement: Rysunek należy do instrumentu, nie do widoku

Rysunek MUST być przypisany do instrumentu i MUST być niezależny od interwału oraz od
slotu, w którym akurat widać ten instrument. Opór jest ceną, a nie własnością pięciu minut
— ten sam rysunek MUST być widoczny na każdym wykresie tego instrumentu.

Moduł MUST znać trzy kształty rysunku:

- **poziom** — jedna cena, opcjonalnie z momentem, od którego obowiązuje;
- **strefa** — przedział między dwiema cenami, opcjonalnie z momentem początku i końca;
- **linia trendu** — dwa punkty, każdy z czasem i ceną.

Każdy rysunek MAY nieść etykietę i MUST nieść kolor z palety terminala albo nie nieść go
wcale. Kolor spoza palety jest kolorem, którego wykres nie umie narysować.

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

### Requirement: Rysunki są trwałe i mają własną tożsamość

Każdy rysunek MUST dostać identyfikator, po którym da się go wskazać, oraz MUST zostać
zapisany wraz z chwilą powstania i sesją rozmowy, w której padł.

Zapis MUST przeżyć restart modułu i odświeżenie przeglądarki. Rysunek postawiony przed
tygodniem MUST dać się odczytać tak samo jak postawiony przed sekundą — to jest cała
różnica między rysunkiem a poleceniem wykresu, które opisuje jedną chwilę.

Liczba rysunków na jednym instrumencie MUST być ograniczona z góry. Wykres, na którym
stoi kilkaset linii, nie pokazuje niczego, a odczyt bez kresu jest odczytem, którego
rozmiaru nikt nie zna.

#### Scenario: Rysunek przeżywa odświeżenie strony

- **WHEN** operator odświeża terminal po tym, jak agent postawił poziom
- **THEN** poziom jest nadal na wykresie

#### Scenario: Rysunek przeżywa rozmowę

- **WHEN** operator zaczyna nową rozmowę po tym, jak w poprzedniej powstały rysunki
- **THEN** rysunki są nadal na wykresie i nadal dają się odczytać

#### Scenario: Sufit rysunków na instrumencie

- **WHEN** agent próbuje postawić rysunek na instrumencie, który ma ich już tyle, ile wynosi sufit
- **THEN** rysunek nie powstaje, a agent dostaje odmowę mówiącą o sufitcie

### Requirement: Agent stawia i kasuje rysunki narzędziem

Moduł MUST publikować modelowi narzędzie, którym stawia rysunki i kasuje istniejące,
wskazując je identyfikatorem.

Narzędzie MUST działać **przyrostowo**, nie deklaratywnie: niesie rysunki do dołożenia
i identyfikatory do skasowania, nigdy „komplet, który ma zostać". Odwrotnie niż polecenie
wykresu (`agent-chart-control`, „Narzędzie ustawia zawartość aktywnego slotu") — bo tam
pominięcie kosztuje jedną świecę wskaźnika, a tutaj kosztowałoby wsparcia, które operator
zbierał tygodniami, skasowane przez przeoczenie modelu.

Jedno wywołanie MUST zostać wykonane w całości albo wcale: wywołanie stawiające trzy
rysunki, z których jeden jest nie do przyjęcia, MUST NOT postawić żadnego.

#### Scenario: Agent stawia wsparcie i opór

- **WHEN** operator prosi o naniesienie wsparcia i oporu, a agent woła narzędzie z dwoma poziomami
- **THEN** oba pojawiają się na wykresie tego instrumentu

#### Scenario: Agent kasuje rysunek, który sam postawił

- **WHEN** agent woła narzędzie z identyfikatorem rysunku do skasowania
- **THEN** rysunek znika z wykresu

#### Scenario: Wywołanie z jednym rysunkiem nie do przyjęcia

- **WHEN** agent woła narzędzie z trzema poziomami, z których jeden ma kolor spoza palety
- **THEN** nie powstaje żaden z nich
- **AND** agent dostaje odmowę nazywającą ten kolor

#### Scenario: Agent nie kasuje przez pominięcie

- **WHEN** agent woła narzędzie stawiające jeden poziom na instrumencie, który ma już trzy inne
- **THEN** na instrumencie są cztery poziomy

### Requirement: Agent odczytuje rysunki narzędziem

Moduł MUST publikować modelowi narzędzie odczytujące rysunki wskazanego instrumentu wraz
z ich identyfikatorami, kształtami, cenami, etykietami i chwilą powstania.

Odczyt MUST być możliwy dla instrumentu, którego terminal akurat nie pokazuje: pytanie
„co mamy naniesione na złocie" MUST NOT wymagać, żeby złoto było na ekranie.

Odczyt MUST NOT niczego zmieniać — dwa odczyty pod rząd MUST dać ten sam wynik.

Identyfikator z odczytu MUST być tym samym identyfikatorem, którym narzędzie kasujące
wskazuje rysunek. Model, który odczytał, MUST móc skasować bez zgadywania.

#### Scenario: Pytanie o naniesione poziomy

- **WHEN** operator pyta, co jest naniesione na instrumencie
- **THEN** model odczytuje rysunki i wymienia je z cenami i etykietami

#### Scenario: Odczyt instrumentu spoza ekranu

- **WHEN** model odczytuje rysunki instrumentu, którego żaden slot nie pokazuje
- **THEN** dostaje je tak samo jak dla instrumentu widocznego

#### Scenario: Odczyt, potem skasowanie

- **WHEN** model odczytuje rysunki, a następnie kasuje jeden z odczytanych identyfikatorów
- **THEN** ten rysunek znika, a pozostałe zostają

### Requirement: Odmowa rysowania nazywa, co poprawić

Narzędzie MUST odmówić rysunku, którego terminal nie mógłby narysować albo który nie
opisuje figury: instrumentu, którego archiwum nie zbiera, koloru spoza palety, strefy
o cenach równych albo odwróconych, linii trendu o dwóch punktach w tej samej chwili, ceny
niedodatniej, oraz żądania ponad sufit rysunków na instrumencie.

Narzędzie MUST odmówić skasowania identyfikatora, którego na tym instrumencie nie ma,
zamiast milczeć — rysunek skasowany w międzyczasie ręką operatora jest informacją, której
model potrzebuje, żeby nie mówić o nim dalej.

Odmowa MUST wracać do modelu jako wynik wywołania wraz ze zdaniem mówiącym, co zmienić
(`agent-tools`, „Odmowa narzędzia jest wynikiem, nie awarią tury"), i MUST NOT zostawić
żadnego śladu na wykresie.

#### Scenario: Instrument, którego archiwum nie zbiera

- **WHEN** model stawia rysunek na symbolu spoza zbieranych par
- **THEN** dostaje odmowę mówiącą, które symbole są zbierane
- **AND** nic nie powstaje

#### Scenario: Strefa o odwróconych cenach

- **WHEN** model stawia strefę, której górna cena jest niższa od dolnej
- **THEN** dostaje odmowę nazywającą obie ceny

#### Scenario: Linia trendu z dwoma punktami w tej samej chwili

- **WHEN** model stawia linię trendu, której oba punkty mają ten sam czas
- **THEN** dostaje odmowę mówiącą, że punkty muszą być rozsunięte w czasie

#### Scenario: Kasowanie nieistniejącego rysunku

- **WHEN** model kasuje identyfikator, którego na tym instrumencie nie ma
- **THEN** dostaje odmowę mówiącą, że takiego rysunku nie ma
- **AND** pozostałe rysunki zostają nietknięte

### Requirement: Operator cofa rysunek ręką

Moduł MUST publikować rysunki wskazanego instrumentu, MUST pozwalać usunąć pojedynczy
rysunek i MUST pozwalać poprawić jego ceny oraz etykietę — bez udziału modelu i bez
rozmowy.

Rysunek usunięty MUST NOT wrócić sam z siebie. Zapis agenta, którego operator nie umie
cofnąć własną ręką, jest poza tym, na co ten moduł ma pozwolenie (`agent-tools`, „Agent
zapisuje wyłącznie w widoku terminala").

Poprawienie MUST zachować tożsamość rysunku: identyfikator, którym model wskazał go przed
poprawką, MUST wskazywać go po niej.

#### Scenario: Operator kasuje poziom postawiony przez agenta

- **WHEN** operator usuwa poziom, który postawił agent
- **THEN** poziom znika i nie wraca po odświeżeniu strony

#### Scenario: Operator poprawia cenę poziomu

- **WHEN** operator zmienia cenę istniejącego poziomu
- **THEN** poziom rysuje się na nowej cenie
- **AND** model odczytujący rysunki widzi nową cenę pod tym samym identyfikatorem

#### Scenario: Odczyt rysunków instrumentu

- **WHEN** konsument pyta o rysunki instrumentu
- **THEN** dostaje wszystkie jego rysunki wraz z identyfikatorami
- **AND** nie dostaje rysunków innych instrumentów
