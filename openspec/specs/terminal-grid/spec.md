## Purpose

Siatka wykresów na zakładce Graph: ile wykresów widać naraz, co pokazuje każdy z nich i dlaczego
ten sam układ zastaje się po powrocie do terminala następnego dnia.
## Requirements
### Requirement: Układ siatki wybiera operator

Zakładka wykresów MUST pozwalać wybrać układ z zestawu `1x1`, `2x1`, `2x2` i `3x2`, gdzie liczby
oznaczają kolumny i wiersze. Sloty MUST wypełniać dostępną wysokość, a wykresy MUST przerysować się
do nowego rozmiaru po zmianie układu.

#### Scenario: Wybór układu

- **WHEN** operator wybiera układ z paska
- **THEN** siatka pokazuje dokładnie tyle slotów, ile wynika z układu
- **AND** każdy wykres dopasowuje się do nowego rozmiaru slotu

#### Scenario: Przejście na mniejszy układ

- **WHEN** operator przechodzi z układu większego na mniejszy
- **THEN** widoczne pozostają sloty mieszczące się w nowym układzie, licząc od pierwszego
- **AND** konfiguracja slotów, które zniknęły, zostaje zapamiętana i wraca po powrocie do
  większego układu

### Requirement: Slot ma własny instrument i własny interwał

Każdy slot MUST nieść własny symbol, własną rozdzielczość i własny zestaw wskaźników, ustawiane
niezależnie od pozostałych slotów. Zmiana w jednym slocie MUST NOT ruszać żadnego innego.
Rozdzielczości dostępne w slocie MUST być ograniczone do tych, w których wybrany instrument jest
archiwizowany, bo pozostałe prowadziłyby do wykresu bez danych.

Zestaw wskaźników slotu MUST być zapamiętywany razem z resztą jego zawartości. Wskaźnik zapamiętany,
którego bieżące źródło już nie oferuje, MUST zostać pominięty przy odtwarzaniu slotu, a pozostałe
wskaźniki tego slotu MUST zostać narysowane.

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

#### Scenario: Zapamiętany wskaźnik zniknął z katalogu

- **WHEN** odtwarzany slot wskazuje wskaźnik, którego bieżące źródło nie oferuje
- **THEN** slot rysuje pozostałe swoje wskaźniki i mówi, którego nie dało się przywrócić

### Requirement: Konfiguracja siatki przeżywa sesję

Wybrany układ oraz zawartość każdego slotu MUST być zapisywane po stronie przeglądarki i MUST być
odtwarzane przy kolejnym otwarciu terminala. Zapis MUST NOT wymagać żadnej akcji operatora.

#### Scenario: Powrót do terminala

- **WHEN** operator zamyka terminal i otwiera go ponownie
- **THEN** widzi ten sam układ i te same instrumenty z tymi samymi rozdzielczościami

#### Scenario: Zapisany stan jest nieczytelny

- **WHEN** zapisana konfiguracja jest uszkodzona albo pochodzi z niezgodnej wersji
- **THEN** terminal startuje z układem domyślnym, zamiast odmówić uruchomienia

#### Scenario: Zapisany symbol jest nieznany źródłu

- **WHEN** odtwarzany slot wskazuje symbol, którego bieżące źródło danych nie zna
- **THEN** slot mówi, że tego instrumentu nie ma w wybranym źródle, i pozwala wybrać inny
- **AND** pozostałe sloty działają dalej

### Requirement: Slot wskazuje, czego dotyczy

Każdy slot MUST nieść widoczny nagłówek z symbolem i rozdzielczością oraz MUST pozwalać zmienić
jedno i drugie bez opuszczania siatki.

#### Scenario: Zmiana instrumentu w slocie

- **WHEN** operator zmienia instrument z poziomu nagłówka slotu
- **THEN** slot pokazuje serię nowego instrumentu, a nagłówek jego symbol

#### Scenario: Który slot jest aktywny

- **WHEN** operator wskazuje slot
- **THEN** siatka oznacza go jako aktywny, żeby akcje kierowane do slotu miały jawny cel

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

