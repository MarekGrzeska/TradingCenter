## MODIFIED Requirements

### Requirement: Wykres rysuje obiekty naniesione na instrument

Wykres MUST rysować obiekty naniesione na instrument, niezależnie od wskaźników — nie
pochodzą z katalogu, nie są liczone ze świec i nie znikają razem z serią przy zmianie
rozdzielczości, bo należą do instrumentu, a nie do widoku (`agent-chart-drawings`,
„Rysunek należy do instrumentu, nie do widoku").

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
MUST NOT zmieniać się dlatego, że inny obiekt na tym instrumencie powstał albo został
usunięty. Kolor, który przeskakuje po skasowaniu sąsiada, każe operatorowi rozpoznawać
obiekty od nowa.

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

#### Scenario: Etykieta ceny przy osi

- **WHEN** na wykresie stoi naniesiony obiekt
- **THEN** jego cena jest widoczna przy osi cen

#### Scenario: Obiekt zaczynający się poza widokiem

- **WHEN** operator przewinie wykres tak, że początek obiektu jest poza ekranem, a sam obiekt nadal go przecina
- **THEN** etykieta obiektu jest nadal widoczna

#### Scenario: Kolor obiektu po usunięciu innego

- **WHEN** operator usuwa jeden z kilku obiektów, którym wykres sam nadał kolory
- **THEN** pozostałe zachowują kolory, które miały

#### Scenario: Zmiana symbolu

- **WHEN** operator zmienia symbol slotu
- **THEN** obiekty poprzedniego instrumentu znikają, a pojawiają się obiekty nowego

#### Scenario: Nieudany odczyt obiektów

- **WHEN** odczyt naniesionych obiektów się nie powiódł
- **THEN** wykres pokazuje świece i wskaźniki dalej
- **AND** mówi osobno, że obiektów nie udało się odczytać
