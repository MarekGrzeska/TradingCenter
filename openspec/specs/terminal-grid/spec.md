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

Symbol w slocie MUST być wybierany z listy, której jedynym źródłem jest lista instrumentów
archiwizowanych przez archiwum, i która MUST pokazywać je wszystkie naraz — lista jest z założenia
krótka, bo ogranicza ją pułap par zbieranych przez archiwum. Slot MUST NOT przyjmować symbolu wpisanego
z ręki ani wymagać wpisania frazy, żeby zobaczyć, co jest do wyboru — wykres pary, której nikt nie
zbiera, nie ma czego pokazać, a operator dowiadywał się o tym dopiero z komunikatu przy pustym wykresie.

#### Scenario: Wybór instrumentu do slotu

- **WHEN** operator otwiera pole instrumentu w slocie
- **THEN** widzi wszystkie instrumenty archiwizowane i wyłącznie je
- **AND** wybranie jednego z nich ustawia go w slocie

#### Scenario: Instrument spoza archiwizowanych

- **WHEN** archiwum nie zbiera danego instrumentu
- **THEN** lista wyboru go nie zawiera
- **AND** terminal wskazuje zakładkę `Instruments` jako miejsce, gdzie dokłada się instrument do
  archiwizowanych

#### Scenario: Nic nie jest archiwizowane

- **WHEN** archiwum nie zbiera ani jednego instrumentu
- **THEN** pole instrumentu mówi to wprost i kieruje do zakładki `Instruments`
- **AND** MUST NOT pokazywać pustej listy bez wyjaśnienia

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

### Requirement: Aktywny slot stosuje to, co ustawił agent

Terminal MUST stosować polecenie agenta do **aktywnego slotu**: jego zestaw wskaźników,
symbol i interwał. Pozostałe sloty MUST zostać nietknięte, tak samo jak przy zmianie
ręcznej.

Zastosowane polecenie MUST być zapamiętane tak samo jak zmiana ręczna — slot po
odświeżeniu MUST rysować to, co agent ustawił, aż operator to zmieni.

Terminal MUST pamiętać numer ostatnio zastosowanego polecenia i MUST NOT stosować tego
samego polecenia dwa razy. Zmiana ręczna po poleceniu agenta MUST zostać, a nie zostać
cofnięta przy następnym odczycie.

Polecenie MUST być stosowane w granicach, które slot już ma: symbol MUST być
instrumentem archiwizowanym, a interwał MUST być rozdzielczością, w której ten instrument
jest zbierany. Polecenie spoza tych granic MUST NOT zostać zastosowane — moduł agenta
odmawia go wcześniej, a terminal, gdyby takie do niego dotarło, MUST je pominąć i
powiedzieć o tym, zamiast pokazywać wykres bez danych.

Aktywny slot pusty MUST przyjąć symbol z polecenia jak każdy inny — polecenie jest właśnie
wyborem instrumentu.

#### Scenario: Agent ustawia wskaźniki aktywnego slotu

- **WHEN** agent ustawia zestaw wskaźników, a operator ma aktywny slot z instrumentem
- **THEN** ten slot rysuje ten zestaw
- **AND** pozostałe sloty rysują to, co rysowały

#### Scenario: Ustawienie agenta przeżywa odświeżenie

- **WHEN** operator odświeża stronę po tym, jak agent ustawił wskaźniki
- **THEN** slot rysuje je dalej

#### Scenario: To samo polecenie nie stosuje się dwa razy

- **WHEN** operator wyłącza wybierakiem wskaźnik ustawiony przez agenta i odświeża stronę
- **THEN** wskaźnik zostaje wyłączony, bo tamto polecenie zostało już zastosowane

#### Scenario: Agent zmienia symbol i interwał

- **WHEN** agent ustawia symbol i interwał, w których archiwum zbiera dane
- **THEN** aktywny slot pokazuje ten instrument w tym interwale

