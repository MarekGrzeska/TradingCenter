## Purpose

Wykres świecowy jako jeden komponent używany wszędzie tak samo: dostaje symbol i rozdzielczość,
rysuje historię, dokleja to, co przychodzi na żywo, i uczciwie mówi, gdy nie ma czego narysować.

## Requirements

### Requirement: Wykres jest sterowany symbolem i rozdzielczością

Wykres MUST przyjmować symbol i rozdzielczość jako wejście i MUST być tym w pełni określony — ten
sam komponent MUST działać zarówno jako pojedynczy wykres, jak i jako zawartość slotu siatki, bez
osobnego wariantu dla każdego z tych zastosowań.

#### Scenario: Ten sam komponent w dwóch miejscach

- **WHEN** ten sam wykres zostaje umieszczony solo i w slocie siatki
- **THEN** zachowuje się identycznie, różniąc się wyłącznie rozmiarem

#### Scenario: Zmiana symbolu

- **WHEN** wykres dostaje inny symbol
- **THEN** rysuje historię nowego symbolu i porzuca subskrypcję poprzedniego

### Requirement: Rozdzielczość zmienia się bez przeładowania

Wykres MUST pozwalać wybrać rozdzielczość z listy `MINUTE`, `MINUTE_5`, `MINUTE_15`, `MINUTE_30`,
`HOUR`, `HOUR_4`, `DAY`, `WEEK`. Zmiana MUST zaciągać historię w nowej rozdzielczości i
przepinać subskrypcję na żywo, bez przeładowania strony i bez utraty pozostałych widoków.

#### Scenario: Wybór innego interwału

- **WHEN** operator wybiera inną rozdzielczość
- **THEN** wykres pokazuje serię w tej rozdzielczości
- **AND** subskrypcja na żywo dotyczy już nowej rozdzielczości, a nie poprzedniej

#### Scenario: Szybka zmiana kilku rozdzielczości pod rząd

- **WHEN** operator przełącza rozdzielczość kilka razy szybciej, niż wraca odpowiedź
- **THEN** wykres pokazuje serię ostatnio wybranej rozdzielczości
- **AND** spóźniona odpowiedź na wcześniejszy wybór MUST NOT nadpisać tego, co widać

### Requirement: Świeca na żywo dokłada się do historii

Wykres MUST wstawiać świece przychodzące na żywo do serii po znaczniku czasu: świeca z okresu już
narysowanego podmienia istniejącą, świeca z okresu nowego dopisuje się na końcu. Seria MUST NOT
zawierać dwóch świec o tym samym znaczniku czasu.

#### Scenario: Ruch wewnątrz bieżącej świecy

- **WHEN** przychodzi świeca w budowie dla bieżącego okresu
- **THEN** ostatnia świeca na wykresie zmienia się, zamiast pojawić się jako kolejna

#### Scenario: Otwarcie nowego okresu

- **WHEN** przychodzi świeca dla okresu późniejszego niż ostatnia narysowana
- **THEN** wykres dokłada ją na końcu serii

### Requirement: Wykres mówi, w jakim jest stanie

Wykres MUST rozróżniać na ekranie: trwa ładowanie historii, seria jest pusta, odczyt się nie
powiódł, strumień jest zerwany. Pusty prostokąt MUST NOT być odpowiedzią na żaden z tych stanów.

#### Scenario: Trwa zaciąganie historii

- **WHEN** historia jeszcze nie przyszła
- **THEN** wykres pokazuje, że trwa ładowanie

#### Scenario: Odczyt się nie powiódł

- **WHEN** odczyt historii kończy się błędem
- **THEN** wykres pokazuje komunikat mówiący, co zawiodło, wraz z możliwością ponowienia

#### Scenario: Instrument nie ma świec

- **WHEN** źródło zwraca pustą serię
- **THEN** wykres stwierdza, że dla tego instrumentu i tej rozdzielczości nie ma danych

#### Scenario: Strumień zerwany

- **WHEN** strumień przestaje odpowiadać
- **THEN** wykres oznacza dane jako nieaktualne, zamiast pokazywać zastygłą świecę bez komentarza

### Requirement: Wykres podaje wartości spod kursora

Wykres MUST pokazywać otwarcie, maksimum, minimum, zamknięcie i czas świecy wskazywanej kursorem.

Wolumen MUST NOT być pokazywany. Provider podaje dla kontraktów CFD wolumen własnego instrumentu,
a nie rynku bazowego, więc jest to liczba, której nie da się uczciwie przeczytać: pokazana obok
ceny wygląda na wolumen rynkowy i tym nie jest.

#### Scenario: Kursor nad świecą

- **WHEN** operator najeżdża na świecę
- **THEN** wykres pokazuje jej otwarcie, maksimum, minimum, zamknięcie i czas

#### Scenario: Świeca z wolumenem od źródła

- **WHEN** świeca pochodzi ze źródła, które wolumen niesie
- **THEN** wykres i tak go nie pokazuje

### Requirement: Wykres sprząta po sobie

Wykres MUST zwalniać swoje zasoby, gdy znika z ekranu: kończyć subskrypcję i usuwać nasłuchy.
Zmiana układu siatki MUST NOT zostawiać działających subskrypcji po slotach, których już nie ma.

#### Scenario: Slot znika po zmianie układu

- **WHEN** układ siatki zmienia się na mniejszy i część slotów przestaje istnieć
- **THEN** subskrypcje tych slotów zostają zakończone

#### Scenario: Zmiana rozmiaru okna

- **WHEN** okno przeglądarki zmienia rozmiar
- **THEN** wykres dopasowuje się do nowego rozmiaru kontenera

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
