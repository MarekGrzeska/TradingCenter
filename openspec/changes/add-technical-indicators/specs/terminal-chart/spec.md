## ADDED Requirements

### Requirement: Operator wybiera wskaźniki z tego, co oferuje źródło

Wykres MUST budować listę dostępnych wskaźników z katalogu podanego przez źródło danych, a MUST NOT
nieść własnej, wpisanej na sztywno listy. Wskaźnik dodany po stronie źródła, o kształcie wyjścia
i sposobie rysowania już obsługiwanym, MUST pojawić się do wyboru bez zmiany w terminalu.

Wybrany wskaźnik MUST dać się usunąć z wykresu, a jego parametry MUST dać się ustawić w granicach,
które podaje katalog.

#### Scenario: Lista pochodzi ze źródła

- **WHEN** operator otwiera wybór wskaźników
- **THEN** widzi to, co oferuje katalog źródła, wraz z parametrami i ich wartościami domyślnymi

#### Scenario: Wskaźnik dołożony po stronie źródła

- **WHEN** źródło zaczyna oferować kolejny wskaźnik rysowany jako linia
- **THEN** pojawia się on w wyborze bez wydania nowej wersji terminala

#### Scenario: Parametr poza zakresem

- **WHEN** operator próbuje ustawić parametr poza zakresem podanym w katalogu
- **THEN** wykres go nie przyjmuje i mówi, jaki zakres obowiązuje

### Requirement: Wskaźnik rysuje się tam, gdzie należy

Wykres MUST rysować wskaźnik zgodnie z podpowiedzią z katalogu: nakładkę na panelu ceny albo
osobny panel pod wykresem, dzielący oś czasu z wykresem ceny. Oscylator o ustalonym zakresie MUST
mieć narysowane poziomy odniesienia, które podaje katalog.

Nakładka MUST NOT zniekształcać skali ceny, gdy katalog mówi, że nie ma w niej uczestniczyć —
inaczej jedna długa średnia potrafi ścisnąć świece do paska.

#### Scenario: Nakładka i oscylator

- **WHEN** operator włącza średnią i oscylator naraz
- **THEN** średnia rysuje się na świecach, a oscylator w osobnym panelu pod nimi

#### Scenario: Wspólna oś czasu

- **WHEN** operator przewija albo skaluje wykres
- **THEN** panele wskaźników przesuwają się razem z ceną, pokazując ten sam przedział czasu

#### Scenario: Nakładka poza skalą ceny

- **WHEN** rysowana jest nakładka oznaczona w katalogu jako nieuczestnicząca w skalowaniu
- **THEN** zakres osi ceny pozostaje wyznaczony przez świece

### Requirement: Wskaźnik bez wartości nie jest rysowany jako zero

Okres, dla którego źródło nie podaje wartości, MUST być przerwą w linii. Wykres MUST NOT rysować
w tym miejscu zera ani łączyć linii ponad przerwą.

Wykres MUST także pokazywać, gdy wartości w widocznym zakresie nie są jeszcze ustabilizowane, bo
archiwum nie sięga dość głęboko wstecz.

#### Scenario: Okres przed rozgrzewką

- **WHEN** początek widocznego zakresu wypada przed rozgrzewką wskaźnika
- **THEN** linia zaczyna się dopiero tam, gdzie wartości istnieją

#### Scenario: Za płytka historia

- **WHEN** źródło mówi, że wartości nie są ustabilizowane
- **THEN** wykres to sygnalizuje, zamiast pokazywać je jako pewne

### Requirement: Wykres podaje wartości wskaźników spod kursora

Wykres MUST pokazywać wartości włączonych wskaźników dla świecy wskazywanej kursorem, obok wartości
tej świecy, i MUST wiązać każdą z nazwą wskaźnika wraz z jego parametrami. Kilka linii bez podpisu
MUST NOT być jedynym opisem tego, co jest narysowane.

#### Scenario: Kursor nad świecą

- **WHEN** operator najeżdża na świecę mając włączone wskaźniki
- **THEN** widzi ich wartości dla tej świecy, każdą podpisaną nazwą i parametrami

#### Scenario: Kursor poza serią

- **WHEN** kursor opuszcza obszar danych
- **THEN** odczyt wraca do wartości ostatniej świecy, zamiast zostawać na ostatnio wskazanej

### Requirement: Strefy i poziomy rysują się jako obszary, nie jako linie serii

Wykres MUST rysować strefę cenową jako obszar rozpięty między jej granicami i czasem jej trwania,
a poziom jako odcinek zaczynający się w momencie, od którego obowiązuje. Strefa niedomknięta MUST
sięgać prawej krawędzi i podążać za nią przy przewijaniu.

Liczba stref widocznych naraz MUST NOT psuć płynności przewijania — poza widocznym zakresem strefy
MUST NOT być rysowane.

#### Scenario: Strefa otwarta

- **WHEN** rysowana jest strefa, której koniec jest nieustalony
- **THEN** ciągnie się do prawej krawędzi i przesuwa razem z nią

#### Scenario: Poziom z wyższego interwału

- **WHEN** rysowany jest poziom obowiązujący od zamknięcia poprzedniego dnia
- **THEN** zaczyna się w tym momencie, a nie na lewej krawędzi wykresu

#### Scenario: Wiele stref naraz

- **WHEN** w widocznym zakresie jest kilkaset stref
- **THEN** przewijanie pozostaje płynne

### Requirement: Wskaźniki znikają razem z serią, której dotyczą

Zmiana symbolu, rozdzielczości albo źródła MUST usunąć z wykresu wszystkie narysowane wskaźniki
razem ze świecami. Wskaźnik policzony dla poprzedniej serii MUST NOT zostać na ekranie ani przez
chwilę, w której nowa seria się ładuje.

#### Scenario: Zmiana rozdzielczości

- **WHEN** operator zmienia rozdzielczość
- **THEN** wskaźniki są przeliczone dla nowej serii, a stare wartości nie są widoczne w międzyczasie

#### Scenario: Wybór wskaźników po zmianie symbolu

- **WHEN** operator zmienia symbol
- **THEN** te same wskaźniki pozostają włączone, policzone dla nowego instrumentu

### Requirement: Wykres mówi, gdy wskaźników nie da się policzyć

Nieudany odczyt wskaźników MUST NOT ukrywać świec, które przyszły. Wykres MUST pokazywać serię
i osobno mówić, że wskaźników nie udało się policzyć, wraz z możliwością ponowienia.

Odmowa źródła — na przykład przekroczony sufit żądania albo brak serii w wymaganej rozdzielczości
— MUST być pokazana jako powód, który da się usunąć, a nie jako awaria.

#### Scenario: Odczyt wskaźników zawiódł

- **WHEN** świece przyszły, a odczyt wskaźników się nie powiódł
- **THEN** wykres rysuje świece i mówi, że wskaźniki są niedostępne, dając ponowić

#### Scenario: Odmowa z powodu sufitu

- **WHEN** źródło odmawia, bo zamówiono zbyt wiele wskaźników naraz
- **THEN** wykres podaje ten powód, zamiast zgłaszać ogólny błąd
