## MODIFIED Requirements

### Requirement: Slot ma własny instrument i własny interwał

Każdy slot MUST nieść własny symbol, własną rozdzielczość i własny zestaw wskaźników, ustawiane
niezależnie od pozostałych slotów. Zmiana w jednym slocie MUST NOT ruszać żadnego innego.
Rozdzielczości dostępne w slocie MUST być ograniczone do tych, w których wybrany instrument jest
archiwizowany, bo pozostałe prowadziłyby do wykresu bez danych.

Zestaw wskaźników slotu MUST być zapamiętywany razem z resztą jego zawartości, wraz z podziałem na
instancje i kolorem każdej z nich. Wskaźnik zapamiętany, którego bieżące źródło już nie oferuje,
MUST zostać pominięty przy odtwarzaniu slotu, a pozostałe wskaźniki tego slotu MUST zostać
narysowane.

Zestaw zapisany, zanim wskaźniki dzieliły się na instancje i niosły kolor, MUST dać się odtworzyć:
każdy zapamiętany wpis MUST wrócić jako jedna instancja bez wybranego koloru, zamiast unieważniać
cały slot.

#### Scenario: Ten sam instrument w kilku interwałach

- **WHEN** operator ustawia w kilku slotach ten sam symbol z różnymi rozdzielczościami
- **THEN** każdy slot pokazuje własną serię
- **AND** zmiana rozdzielczości w jednym z nich nie zmienia pozostałych

#### Scenario: Rozdzielczości do wyboru w slocie

- **WHEN** slot ma przypisany instrument archiwizowany w dwóch rozdzielczościach
- **THEN** do wyboru są te dwie rozdzielczości
- **AND** rozdzielczości, w których ten instrument nie jest archiwizowany, nie są oferowane

#### Scenario: Slot pusty

- **WHEN** slot nie ma jeszcze przypisanego instrumentu
- **THEN** pokazuje zaproszenie do wybrania instrumentu, a nie pusty wykres ani błąd

#### Scenario: Różne wskaźniki w dwóch slotach

- **WHEN** operator włącza inny zestaw wskaźników w dwóch slotach
- **THEN** każdy slot rysuje własny zestaw
- **AND** włączenie wskaźnika w jednym z nich nie zmienia drugiego

#### Scenario: Powrót do terminala z zapisanymi wskaźnikami

- **WHEN** operator zamyka terminal i otwiera go ponownie
- **THEN** każdy slot ma z powrotem swój zestaw wskaźników z tymi samymi parametrami

#### Scenario: Powrót do terminala z kilkoma instancjami jednego wpisu

- **WHEN** operator zamyka terminal, mając w slocie trzy instancje tego samego wpisu w różnych
  kolorach, i otwiera go ponownie
- **THEN** slot ma z powrotem te trzy instancje, każdą ze swoimi parametrami i swoim kolorem

#### Scenario: Slot zapisany przed instancjami i kolorami

- **WHEN** odtwarzany jest slot zapisany, gdy wskaźniki nie dzieliły się jeszcze na instancje ani
  nie niosły koloru
- **THEN** każdy jego wskaźnik wraca jako jedna instancja bez wybranego koloru

#### Scenario: Zapamiętany wskaźnik zniknął z katalogu

- **WHEN** odtwarzany slot wskazuje wskaźnik, którego bieżące źródło nie oferuje
- **THEN** slot rysuje pozostałe swoje wskaźniki i mówi, którego nie dało się przywrócić
