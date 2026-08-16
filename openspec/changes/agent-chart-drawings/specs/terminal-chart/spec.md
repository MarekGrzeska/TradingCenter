## ADDED Requirements

### Requirement: Wykres rysuje obiekty naniesione na instrument

Wykres MUST rysować obiekty naniesione na instrument, niezależnie od wskaźników — nie
pochodzą z katalogu, nie są liczone ze świec i nie znikają razem z serią przy zmianie
rozdzielczości, bo należą do instrumentu, a nie do widoku (`agent-chart-drawings`,
„Rysunek należy do instrumentu, nie do widoku").

Wykres MUST umieć narysować wszystkie trzy kształty: poziom, strefę oraz **linię trendu**
rozpiętą między dwoma punktami czas–cena. Poziom i strefa MUST rysować się tak samo jak te
pochodzące ze wskaźników (patrz „Strefy i poziomy rysują się jako obszary, nie jako linie
serii"). Linia trendu MUST być odcinkiem między swoimi punktami — MUST NOT być przedłużana
poza nie ani przycinana do widocznego zakresu.

Obiekt MUST nieść etykietę, jeśli ją ma, i MUST być narysowany kolorem, który mu nadano;
obiekt bez koloru MUST dostać kolor od wykresu.

Wykres MUST odświeżyć naniesione obiekty po zakończonej turze agenta i po zmianie symbolu.
Nieudany odczyt obiektów MUST NOT ukryć świec ani wskaźników: wykres MUST rysować serię
dalej i osobno powiedzieć, że obiektów nie udało się odczytać.

Zmiana rozdzielczości MUST zachować narysowane obiekty. Zmiana symbolu MUST je wymienić na
obiekty nowego instrumentu.

#### Scenario: Poziom po zmianie interwału

- **WHEN** operator zmienia rozdzielczość wykresu z naniesionym poziomem
- **THEN** poziom jest nadal narysowany, na tej samej cenie

#### Scenario: Linia trendu między dwoma punktami

- **WHEN** rysowana jest linia trendu rozpięta między dwoma punktami czas–cena
- **THEN** odcinek zaczyna się i kończy w tych punktach, bez przedłużania

#### Scenario: Zmiana symbolu

- **WHEN** operator zmienia symbol slotu
- **THEN** obiekty poprzedniego instrumentu znikają, a pojawiają się obiekty nowego

#### Scenario: Nieudany odczyt obiektów

- **WHEN** odczyt naniesionych obiektów się nie powiódł
- **THEN** wykres pokazuje świece i wskaźniki dalej
- **AND** mówi osobno, że obiektów nie udało się odczytać

### Requirement: Operator zarządza naniesionymi obiektami z listy

Terminal MUST pokazywać listę obiektów naniesionych na instrument aktywnego slotu: kształt,
ceny, etykietę i to, kiedy powstały. Lista jest jedyną drogą, którą operator cofa to, co
narysował agent (`agent-tools`, „Agent zapisuje wyłącznie w widoku terminala"), więc MUST
być dostępna bez rozmowy z agentem.

Operator MUST móc z listy usunąć pojedynczy obiekt oraz poprawić jego ceny i etykietę.
Skutek MUST być widoczny na wykresie od razu, bez przeładowania strony.

Nieudane usunięcie albo nieudana poprawka MUST zostać powiedziane, a lista i wykres MUST
zostać takie, jakie były — obiekt, który zniknął z ekranu, ale nie z zapisu, wróciłby przy
następnym odczycie i czytałby się jak usterka.

Instrument bez naniesionych obiektów MUST dawać pustą listę mówiącą, że nic nie jest
naniesione — a nie brak listy, którego nie da się odróżnić od nieudanego odczytu.

#### Scenario: Operator usuwa poziom z listy

- **WHEN** operator usuwa poziom z listy obiektów
- **THEN** poziom znika z wykresu od razu
- **AND** nie wraca po odświeżeniu strony

#### Scenario: Operator poprawia cenę z listy

- **WHEN** operator zmienia cenę obiektu na liście
- **THEN** obiekt rysuje się na nowej cenie

#### Scenario: Usunięcie się nie powiodło

- **WHEN** usunięcie obiektu kończy się błędem
- **THEN** obiekt zostaje na liście i na wykresie
- **AND** terminal mówi, że usunięcie się nie powiodło

#### Scenario: Instrument bez obiektów

- **WHEN** aktywny slot pokazuje instrument, na który nic nie naniesiono
- **THEN** lista mówi, że nic nie jest naniesione
