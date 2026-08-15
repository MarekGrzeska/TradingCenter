## MODIFIED Requirements

### Requirement: Operator wybiera wskaźniki z tego, co oferuje źródło

Wykres MUST budować listę dostępnych wskaźników z katalogu podanego przez źródło danych, a MUST NOT
nieść własnej, wpisanej na sztywno listy. Wskaźnik dodany po stronie źródła, o kształcie wyjścia
i sposobie rysowania już obsługiwanym, MUST pojawić się do wyboru bez zmiany w terminalu.

Wybrany wskaźnik MUST dać się usunąć z wykresu, a jego parametry MUST dać się ustawić w granicach,
które podaje katalog.

Jeden wpis katalogu MUST dać się włączyć więcej niż raz. Każde włączenie jest osobną **instancją**
z własnymi parametrami: zmiana parametru jednej instancji MUST NOT ruszać pozostałych, a usunięcie
jednej MUST zostawić pozostałe narysowane. Wykres MUST rysować każdą instancję osobno, także wtedy,
gdy dwie instancje tego samego wpisu mają identyczne parametry.

#### Scenario: Lista pochodzi ze źródła

- **WHEN** operator otwiera wybór wskaźników
- **THEN** widzi to, co oferuje katalog źródła, wraz z parametrami i ich wartościami domyślnymi

#### Scenario: Wskaźnik dołożony po stronie źródła

- **WHEN** źródło zaczyna oferować kolejny wskaźnik rysowany jako linia
- **THEN** pojawia się on w wyborze bez wydania nowej wersji terminala

#### Scenario: Parametr poza zakresem

- **WHEN** operator próbuje ustawić parametr poza zakresem podanym w katalogu
- **THEN** wykres go nie przyjmuje i mówi, jaki zakres obowiązuje

#### Scenario: Ta sama średnia w kilku okresach

- **WHEN** operator dokłada trzy instancje tego samego wpisu katalogu i ustawia im różne okresy
- **THEN** wykres rysuje trzy osobne linie, każdą policzoną ze swoim okresem

#### Scenario: Parametr jednej instancji

- **WHEN** operator zmienia okres jednej z włączonych instancji tego samego wpisu
- **THEN** pozostałe instancje zostają przy swoich okresach

#### Scenario: Usunięcie jednej instancji

- **WHEN** operator usuwa jedną z kilku instancji tego samego wpisu
- **THEN** znika z wykresu tylko ona, a pozostałe rysują się dalej

### Requirement: Wykres podaje wartości wskaźników spod kursora

Wykres MUST pokazywać wartości włączonych wskaźników dla świecy wskazywanej kursorem, obok wartości
tej świecy, i MUST wiązać każdą z nazwą wskaźnika wraz z jego parametrami. Kilka linii bez podpisu
MUST NOT być jedynym opisem tego, co jest narysowane.

Gdy włączona jest więcej niż jedna instancja tego samego wpisu katalogu, odczyt MUST dawać się
przypisać do konkretnej instancji — po jej parametrach, a gdy i te są identyczne, po jej kolorze.

#### Scenario: Kursor nad świecą

- **WHEN** operator najeżdża na świecę mając włączone wskaźniki
- **THEN** widzi ich wartości dla tej świecy, każdą podpisaną nazwą i parametrami

#### Scenario: Kursor poza serią

- **WHEN** kursor opuszcza obszar danych
- **THEN** odczyt wraca do wartości ostatniej świecy, zamiast zostawać na ostatnio wskazanej

#### Scenario: Kursor przy kilku instancjach jednego wpisu

- **WHEN** operator najeżdża na świecę mając włączone dwie instancje tego samego wpisu
- **THEN** widzi dwie wartości, każdą podpisaną parametrami swojej instancji

## ADDED Requirements

### Requirement: Kolor wskaźnika wybiera operator

Wykres MUST pozwalać przypisać instancji wskaźnika kolor i MUST rysować ją tym kolorem, dopóki
operator go nie zmieni. Kolory do wyboru MUST pochodzić z palety motywu terminala, żeby wybrana
linia była czytelna w obu motywach; wykres MUST NOT przyjmować koloru spoza tej palety.

Instancja bez wybranego koloru MUST dostać kolor sam z siebie, tak jak dotąd. Kolor wybrany
MUST NOT zmieniać się przy włączaniu, wyłączaniu ani przeliczaniu innych wskaźników.

Kolor MUST dotyczyć instancji, a nie wpisu katalogu: dwie instancje tego samego wpisu MUST móc mieć
różne kolory.

#### Scenario: Operator ustawia kolor

- **WHEN** operator wybiera kolor dla włączonej instancji wskaźnika
- **THEN** jej linia jest rysowana tym kolorem

#### Scenario: Kolor przeżywa dołożenie innego wskaźnika

- **WHEN** operator włącza kolejny wskaźnik po ustawieniu koloru wcześniejszej instancji
- **THEN** kolor tamtej instancji zostaje ten sam

#### Scenario: Instancja bez wybranego koloru

- **WHEN** operator włącza wskaźnik i nie wybiera koloru
- **THEN** wykres rysuje go kolorem przydzielonym samoczynnie, odróżnialnym od pozostałych

#### Scenario: Dwie instancje w różnych kolorach

- **WHEN** operator ma dwie instancje tego samego wpisu i ustawia każdej inny kolor
- **THEN** obie linie rysują się swoimi kolorami
