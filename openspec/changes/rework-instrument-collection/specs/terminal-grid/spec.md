## MODIFIED Requirements

### Requirement: Slot ma własny instrument i własny interwał

Każdy slot MUST nieść własny symbol i własną rozdzielczość, ustawiane niezależnie od pozostałych
slotów. Zmiana w jednym slocie MUST NOT ruszać żadnego innego. Rozdzielczości dostępne w slocie
MUST być ograniczone do tych, w których wybrany instrument jest archiwizowany, bo pozostałe
prowadziłyby do wykresu bez danych.

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

## ADDED Requirements

### Requirement: Slot przyjmuje wyłącznie instrument archiwizowany

Symbol w slocie MUST być wybierany z podpowiedzi, których jedynym źródłem jest lista instrumentów
archiwizowanych przez archiwum. Slot MUST NOT przyjmować symbolu wpisanego z ręki — wykres pary,
której nikt nie zbiera, nie ma czego pokazać, a operator dowiadywał się o tym dopiero z komunikatu
przy pustym wykresie.

#### Scenario: Wybór instrumentu do slotu

- **WHEN** operator otwiera pole instrumentu w slocie
- **THEN** widzi wyłącznie instrumenty archiwizowane
- **AND** wybranie jednego z nich ustawia go w slocie

#### Scenario: Instrument spoza archiwizowanych

- **WHEN** operator wpisuje frazę pasującą do instrumentu, którego archiwum nie zbiera
- **THEN** podpowiedzi go nie zawierają
- **AND** terminal wskazuje zakładkę `Instruments` jako miejsce, gdzie dokłada się instrument do
  archiwizowanych

#### Scenario: Nic nie jest archiwizowane

- **WHEN** archiwum nie zbiera ani jednego instrumentu
- **THEN** pole instrumentu mówi to wprost i kieruje do zakładki `Instruments`
- **AND** MUST NOT pokazywać pustych podpowiedzi bez wyjaśnienia

#### Scenario: Listy archiwizowanych nie da się odczytać

- **WHEN** archiwum nie odpowiada na pytanie, co zbiera
- **THEN** pole instrumentu mówi, że nie da się teraz wybrać instrumentu, wraz z możliwością
  ponowienia
- **AND** slot zachowuje instrument już w nim ustawiony

### Requirement: Slot zapamiętany traci ważność, gdy instrument przestaje być archiwizowany

Zawartość slotu przeżywa sesję, więc slot może wrócić z symbolem, którego archiwum już nie zbiera.
Terminal MUST rozpoznać taki slot i powiedzieć, co się stało, zamiast pokazywać pusty wykres albo
pętlę wznawiania połączenia.

#### Scenario: Zapamiętany instrument został zdjęty z archiwizowanych

- **WHEN** slot wraca z sesji z symbolem, który przestał być archiwizowany
- **THEN** slot stwierdza, że ten instrument nie jest już zbierany, i wskazuje, gdzie to zmienić
- **AND** pozostałe sloty działają dalej
