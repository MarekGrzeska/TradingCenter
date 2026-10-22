## Purpose

Kandydaci z tematów: filmy, które wyszukiwanie tematu znalazło, a model po metadanych uznał za warte obejrzenia. Służą
do odkrywania nowych autorów. Archiwum ich nie czyta. Co z nimi zrobić, decyduje operator.

## ADDED Requirements

### Requirement: Wynik wyszukiwania tematu jest kandydatem, nie filmem archiwum

Każdy wynik wyszukiwania tematu, który przeszedł progi długości i nie jest trwającą transmisją, MUST zostać zapisany
jako kandydat z frazą tematu, momentem znalezienia, tytułem, kanałem, datą publikacji, długością i odnośnikiem do
filmu na YouTube. Kandydat MUST NOT być transkrybowany, czytany ani przekazany pakietowi alertów. Tożsamością
kandydata MUST być identyfikator filmu YouTube: ten sam film znaleziony drugi raz, przez ten sam albo inny temat,
MUST NOT tworzyć drugiego kandydata.

#### Scenario: Wyszukiwanie znajduje nowy film

- **WHEN** wyszukiwanie tematu zwraca film, którego nie ma ani w archiwum, ani wśród kandydatów
- **THEN** film MUST pojawić się wśród kandydatów
- **AND** żaden dostawca transkrypcji MUST NOT zostać o niego zapytany

#### Scenario: Ten sam film z dwóch tematów

- **WHEN** dwa tematy znajdują ten sam film
- **THEN** MUST istnieć jeden kandydat, a jego tematem MUST być ten, który znalazł go pierwszy

### Requirement: Kandydatem nie zostaje film, który archiwum już ma albo którego operator nie chce

Wynik wyszukiwania MUST NOT zostać kandydatem, gdy zachodzi któryś z warunków:

- film jest już w archiwum filmów;
- film pochodzi z kanału na liście obserwacji;
- film pochodzi z kanału ignorowanego;
- operator odrzucił już ten film.

#### Scenario: Film z obserwowanego kanału

- **WHEN** wyszukiwanie tematu zwraca film z kanału, który jest obserwowany
- **THEN** film MUST NOT pojawić się wśród kandydatów

#### Scenario: Odrzucony film wraca w wynikach

- **WHEN** wyszukiwanie zwraca film, który operator odrzucił
- **THEN** film MUST NOT pojawić się ponownie jako proponowany

### Requirement: Model przesiewa wyniki po metadanych

Przed zapisem wyniki jednego wyszukiwania MUST zostać przesiane jednym wywołaniem modelu. Model widzi frazę tematu
oraz tytuł, opis, kanał i długość każdego wyniku. Model MUST NOT dostać transkrypcji ani narzędzi. Tytuł i opis MUST
być oznaczone jako dane obce, nie polecenie. Dla każdego wyniku model MUST zwrócić werdykt (proponowany albo
odrzucony) i jedno zdanie uzasadnienia po polsku. Wynik bez poprawnego werdyktu MUST zostać zapisany jako
nieprzesiany, a nie pominięty. Kandydat odrzucony przez model MUST zostać zapisany ze swoim uzasadnieniem, ale MUST
NOT być proponowany.

#### Scenario: Szum odrzucony

- **WHEN** model uznaje wynik za niezwiązany z tematem
- **THEN** kandydat MUST mieć werdykt „odrzucony” z uzasadnieniem i MUST NOT być na domyślnej liście

#### Scenario: Opis próbuje sterować modelem

- **WHEN** opis filmu zawiera polecenie skierowane do modelu
- **THEN** werdykt MUST wynikać z instrukcji przesiewu, nie z polecenia w opisie

### Requirement: Przesiew mieści się w dziennym limicie tokenów, a jego brak jest stanem wspieranym

Tokeny przesiewu MUST być liczone w zużyciu i w tym samym dziennym limicie tokenów co odczyty. Gdy model nie jest
skonfigurowany, odpoczywa po odmowie albo dzień nie ma już tokenów, wyniki MUST zostać zapisane jako nieprzesiane i
proponowane bez uzasadnienia. Stan modułu MUST mówić, dlaczego przesiew nie działa. Przesiew MUST NOT zatrzymywać
wyszukiwania ani innych kroków pętli.

#### Scenario: Brak klucza modelu

- **WHEN** model nie jest skonfigurowany, a temat jest wyszukiwany
- **THEN** jego wyniki MUST pojawić się wśród kandydatów jako nieprzesiane
- **AND** stan modułu MUST to nazywać

#### Scenario: Dzień bez tokenów

- **WHEN** dzienny limit tokenów jest wyczerpany
- **THEN** model MUST NOT zostać wywołany, a kandydaci MUST zostać zapisani jako nieprzesiani

### Requirement: Operator decyduje o kandydacie

Kontrakt MUST pozwalać na cztery decyzje o kandydacie:

- **obserwuj kanał**: kanał kandydata trafia na listę obserwacji z opcjonalnym promptem, pod tym samym sufitem i
  regułami co każde dopisanie;
- **analizuj film**: film staje się filmem wskazanym ręcznie, z opcjonalnym promptem;
- **odrzuć**: kandydat znika z listy proponowanych i nie wraca;
- **ignoruj kanał**: filmy tego kanału przestają być kandydatami, a dotychczasowi kandydaci z tego kanału znikają z
  listy proponowanych.

Każda decyzja MUST zostać zapisana na kandydacie z momentem podjęcia. Ignorowanie kanału MUST dać się cofnąć. Żadna
decyzja MUST NOT kasować kandydata.

#### Scenario: Obserwacja kanału z kandydata

- **WHEN** operator wybiera „obserwuj kanał” przy kandydacie
- **THEN** kanał MUST pojawić się na liście obserwacji
- **AND** pozostali proponowani kandydaci z tego kanału MUST zniknąć z listy proponowanych

#### Scenario: Analiza z kandydata

- **WHEN** operator wybiera „analizuj film”
- **THEN** film MUST zostać przetworzony jak film wskazany ręcznie
- **AND** kandydat MUST nieść decyzję „analizowany”

#### Scenario: Sufit kanałów

- **WHEN** operator wybiera „obserwuj kanał”, a lista jest pełna
- **THEN** kontrakt MUST odmówić z powodem nazywającym sufit, a kandydat MUST zostać bez decyzji

#### Scenario: Cofnięcie ignorowania

- **WHEN** operator cofa ignorowanie kanału
- **THEN** nowe filmy tego kanału MUST móc znów zostać kandydatami

### Requirement: Lista kandydatów ma porządek i zawężenie

Kontrakt MUST zwracać kandydatów w porządku malejącym po momencie znalezienia albo po dacie publikacji, zależnie od
wyboru klienta. Domyślnym porządkiem MUST być moment znalezienia. Domyślnie lista MUST nieść tylko kandydatów
proponowanych i bez decyzji. Klient MUST móc zawęzić listę do tematu oraz poprosić o odrzuconych przez model albo o
tych z decyzją. Odczyt listy MUST NOT wywoływać żadnego dostawcy.

#### Scenario: Porządek po publikacji

- **WHEN** klient prosi o kandydatów w porządku po dacie publikacji
- **THEN** najnowszy opublikowany film MUST być pierwszy, niezależnie od tego, kiedy go znaleziono

#### Scenario: Wgląd w odrzuconych przez model

- **WHEN** klient prosi o kandydatów odrzuconych przez model
- **THEN** każdy MUST nieść uzasadnienie odrzucenia
