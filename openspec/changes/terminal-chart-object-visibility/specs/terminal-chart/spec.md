## MODIFIED Requirements

### Requirement: Wykres rysuje obiekty naniesione na instrument

Wykres MUST rysować obiekty naniesione na instrument, niezależnie od wskaźników — nie
pochodzą z katalogu, nie są liczone ze świec i nie znikają razem z serią przy zmianie
rozdzielczości, bo należą do instrumentu, a nie do widoku (`agent-chart-drawings`,
„Rysunek należy do instrumentu, nie do widoku").

Wykres MUST rysować obiekty **zapalone** i MUST NOT rysować zgaszonych. Zgaszony obiekt
MUST być nieobecny na płótnie tak samo jak obiekt, którego nie ma: MUST NOT zasłaniać
świec, MUST NOT nieść etykiety przy osi cen i MUST NOT dać się wskazać kliknięciem
(`terminal-chart-objects`, „Operator wskazuje obiekt na wykresie"). Zgaszony obiekt
rysowany blado byłby dalej obiektem na wykresie, a operator gasi go po to, żeby go tam nie
było.

Wykres MUST umieć narysować wszystkie trzy kształty: poziom, strefę oraz **linię trendu**
rozpiętą między dwoma punktami czas–cena. Linia trendu MUST być odcinkiem między swoimi
punktami — MUST NOT być przedłużana poza nie ani przycinana do widocznego zakresu.

Naniesiony obiekt MUST być odróżnialny od wyniku wskaźnika o tym samym kształcie. Poziom
postawiony przez operatora i poziom policzony przez katalog są dwiema różnymi rzeczami:
jedno jest ustaleniem, drugie odczytem, i wykres, na którym wyglądają identycznie, nie
pozwala powiedzieć, którą z nich się właśnie ogląda.

Obiekt MUST nieść etykietę, jeśli ją ma, i MUST być narysowany kolorem, który mu nadano.
Etykieta MUST być czytelna nad świecami — sam tekst położony na wykresie ginie w knotach.
Etykieta obiektu, którego początek leży poza widokiem, MUST pozostać widoczna: obiekt
przecinający ekran bez etykiety jest kreską, o której nie wiadomo nic.

Obiekt MUST nieść przy osi cen etykietę ze swoją ceną, żeby dało się odczytać jego
położenie względem ceny bieżącej bez mierzenia wzrokiem.

Obiekt bez własnego koloru MUST dostać kolor od wykresu, a ten kolor MUST być trwały:
MUST NOT zmieniać się dlatego, że inny obiekt na tym instrumencie powstał, został usunięty
albo zgaszony. Kolor, który przeskakuje po skasowaniu sąsiada, każe operatorowi
rozpoznawać obiekty od nowa.

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

#### Scenario: Naniesiony poziom obok policzonego

- **WHEN** na wykresie są jednocześnie poziom naniesiony na instrument i poziom pochodzący ze wskaźnika
- **THEN** da się je od siebie odróżnić bez sprawdzania, który jest który

#### Scenario: Zgaszony obiekt nie jest rysowany

- **WHEN** operator gasi jeden z naniesionych obiektów
- **THEN** nie ma go na wykresie ani przy osi cen
- **AND** pozostałe są narysowane tak, jak były

#### Scenario: Kliknięcie tam, gdzie stał zgaszony obiekt

- **WHEN** operator klika miejsce, w którym zgaszony obiekt był narysowany
- **THEN** nic nie zostaje wskazane

#### Scenario: Etykieta ceny przy osi

- **WHEN** na wykresie stoi naniesiony obiekt
- **THEN** jego cena jest widoczna przy osi cen

#### Scenario: Obiekt zaczynający się poza widokiem

- **WHEN** operator przewinie wykres tak, że początek obiektu jest poza ekranem, a sam obiekt nadal go przecina
- **THEN** etykieta obiektu jest nadal widoczna

#### Scenario: Kolor obiektu po usunięciu innego

- **WHEN** operator usuwa jeden z kilku obiektów, którym wykres sam nadał kolory
- **THEN** pozostałe zachowują kolory, które miały

#### Scenario: Kolor obiektu po zgaszeniu innego

- **WHEN** operator gasi jeden z kilku obiektów, którym wykres sam nadał kolory
- **THEN** pozostałe zachowują kolory, które miały

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

Operator MUST móc z listy **zgasić i zapalić** pojedynczy obiekt, nie usuwając go. Lista
MUST pokazywać obiekty zgaszone razem z zapalonymi i MUST mówić, które są które: obiekt
zgaszony nie jest rysowany, więc lista jest jedyną drogą, którą da się go zapalić
z powrotem, a lista, która go pomija, gasi go bezpowrotnie.

Nieudane usunięcie, nieudana poprawka albo nieudane zgaszenie MUST zostać powiedziane,
a lista i wykres MUST zostać takie, jakie były — obiekt, który zniknął z ekranu, ale nie
z zapisu, wróciłby przy następnym odczycie i czytałby się jak usterka.

Instrument bez naniesionych obiektów MUST dawać pustą listę mówiącą, że nic nie jest
naniesione — a nie brak listy, którego nie da się odróżnić od nieudanego odczytu.
Instrument, na którym wszystko jest zgaszone, MUST NOT czytać się jak instrument bez
obiektów.

#### Scenario: Operator usuwa poziom z listy

- **WHEN** operator usuwa poziom z listy obiektów
- **THEN** poziom znika z wykresu od razu
- **AND** nie wraca po odświeżeniu strony

#### Scenario: Operator poprawia cenę z listy

- **WHEN** operator zmienia cenę obiektu na liście
- **THEN** obiekt rysuje się na nowej cenie

#### Scenario: Operator gasi poziom z listy

- **WHEN** operator gasi poziom na liście obiektów
- **THEN** poziom znika z wykresu od razu
- **AND** zostaje na liście, oznaczony jako zgaszony

#### Scenario: Operator zapala poziom z listy

- **WHEN** operator zapala zgaszony poziom na liście obiektów
- **THEN** poziom jest znowu na wykresie

#### Scenario: Usunięcie się nie powiodło

- **WHEN** usunięcie obiektu kończy się błędem
- **THEN** obiekt zostaje na liście i na wykresie
- **AND** terminal mówi, że usunięcie się nie powiodło

#### Scenario: Zgaszenie się nie powiodło

- **WHEN** zgaszenie obiektu kończy się błędem
- **THEN** obiekt jest nadal zapalony na liście i na wykresie
- **AND** terminal mówi, że się nie powiodło

#### Scenario: Instrument bez obiektów

- **WHEN** aktywny slot pokazuje instrument, na który nic nie naniesiono
- **THEN** lista mówi, że nic nie jest naniesione

#### Scenario: Instrument z samymi zgaszonymi obiektami

- **WHEN** aktywny slot pokazuje instrument, na którym wszystkie obiekty są zgaszone
- **THEN** lista pokazuje je wszystkie jako zgaszone
- **AND** nie mówi, że nic nie jest naniesione
