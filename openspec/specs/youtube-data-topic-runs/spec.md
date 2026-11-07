# youtube-data-topic-runs Specification

## Purpose

Daje operatorowi historię przebiegów wyszukiwania tematów wraz z raportem — co zwróciło źródło, co z tego zostało
kandydatem, a gdy przebieg się nie udał, dlaczego — żeby cisza tematu miała wyjaśnienie.
## Requirements
### Requirement: Każda próba wyszukiwania tematu zostawia wpis z wynikiem i raportem

Moduł MUST zapisać wpis przebiegu przy każdej próbie wyszukiwania tematu, z wynikiem `found` (zapisano co najmniej jednego
nowego kandydata), `nothing_new` (źródło odpowiedziało i nie ma nic nowego), `failed` (źródło zawiodło) albo `skipped`
(dzień źródła nie starcza na wyszukiwanie). Wpis MUST nieść temat (identyfikator i frazę z chwili przebiegu), moment oraz
liczby: wyniki zwrócone przez źródło, wyniki pominięte jako już znane lub z kanałów rozstrzygniętych, wyniki poza granicami
długości, nowych kandydatów proponowanych, odrzuconych i nieprzesianych. Wpis przebiegu `failed` i `skipped` MUST niezmiennie
nieść przyczynę. Wpis MUST przetrwać usunięcie tematu z listy.

Porażka, za którą źródło policzyło przydział — odmowa, odpowiedź z kodem błędu, odpowiedź bezużyteczna albo wyczerpany limit —
MUST odroczyć następną próbę tego tematu o jego własny odstęp, licząc od porażki. Porażka bez odpowiedzi źródła (błąd sieci)
MUST NOT odraczać tematu, który jest wtedy próbowany w następnym przebiegu pętli. Odroczenie MUST NOT przesuwać początku okna
wyszukiwania: następne udane wyszukiwanie MUST szukać filmów od ostatniego udanego wyszukiwania. Udane wyszukiwanie MUST znieść odroczenie.

#### Scenario: Przebieg znajduje nowe filmy

- **WHEN** wyszukiwanie tematu zwraca pięć wyników, z których dwa są już znane, a trzy stają się kandydatami
- **THEN** wpis MUST mieć wynik `found`, liczbę wyników 5, znanych 2 i trzech kandydatów rozbitych na proponowanych, odrzuconych i nieprzesianych

#### Scenario: Przebieg nie znajduje niczego nowego

- **WHEN** wyszukiwanie tematu zwraca wyłącznie filmy już znane
- **THEN** wpis MUST mieć wynik `nothing_new` i zerowych kandydatów, a wpis MUST istnieć

#### Scenario: Źródło zawodzi

- **WHEN** źródło odpowiada odmową albo informuje, że jego limit jest wyczerpany
- **THEN** wpis MUST mieć wynik `failed` i przyczynę podaną przez źródło
- **AND** temat MUST NOT być próbowany ponownie, zanim upłynie jego odstęp od tej porażki

#### Scenario: Źródło nie odpowiada

- **WHEN** wyszukiwanie tematu kończy się błędem sieci, bez odpowiedzi źródła
- **THEN** wpis MUST mieć wynik `failed` z przyczyną
- **AND** temat MUST zostać spróbowany ponownie w następnym przebiegu pętli

#### Scenario: Udane wyszukiwanie po porażce

- **WHEN** temat odroczony po odmowie źródła doczekał końca odstępu, a wyszukiwanie się udaje
- **THEN** odroczenie MUST zniknąć, a wyszukiwanie MUST szukać filmów od ostatniego udanego wyszukiwania sprzed porażki

#### Scenario: Usunięty temat

- **WHEN** operator zdejmuje temat z listy
- **THEN** wpisy jego przebiegów MUST pozostać w historii

### Requirement: Pominięcie z powodu dnia źródła jest zapisywane raz na temat na dobę

Gdy dzień źródła nie starcza na wyszukiwanie, moduł MUST zapisać wpis `skipped` z przyczyną. Porażka i pominięcie powtarzają
się, dopóki trwa ich przyczyna, więc moduł MUST NOT zapisywać wpisu `failed` albo `skipped`, który powtarza poprzedni wpis
tego tematu — ten sam wynik i tę samą przyczynę — jeśli poprzedni wpis jest z tej samej doby UTC. Porażka z inną przyczyną
oraz porażka albo pominięcie następujące po wpisie o innym wyniku MUST zostać zapisane.

#### Scenario: Dzień źródła nie starcza przez wiele przebiegów

- **WHEN** dzień źródła nie starcza na wyszukiwanie, a pętla przechodzi przez temat kilkanaście razy w tej samej dobie
- **THEN** historia tematu MUST zawierać z tej doby jeden wpis `skipped`

#### Scenario: Nowa doba

- **WHEN** dzień źródła nadal nie starcza po północy UTC
- **THEN** moduł MUST zapisać nowy wpis `skipped`

#### Scenario: Źródło zawodzi z tą samą przyczyną w kolejnych próbach

- **WHEN** źródło odpowiada tym samym błędem w kolejnych próbach tematu tej samej doby
- **THEN** historia tematu MUST zawierać jeden wpis `failed` z tej doby

#### Scenario: Źródło zmienia przyczynę porażki

- **WHEN** po porażce z jedną przyczyną źródło zawodzi z inną
- **THEN** moduł MUST zapisać drugi wpis `failed` z nową przyczyną

#### Scenario: Pominięcie po przebiegu, który się udał

- **WHEN** temat został pominięty rano, wyszukał poprawnie w południe, a wieczorem dzień źródła znów nie starcza
- **THEN** moduł MUST zapisać wieczorny wpis `skipped`, tak żeby ostatni wpis tematu mówił prawdę

### Requirement: Wpis mówi, dlaczego kandydaci nie zostali przesiani

Gdy przesiew wyników modelem nie mógł się odbyć albo nie dał odpowiedzi — brak skonfigurowanego modelu, wyczerpany dzienny
limit tokenów, odpowiedź poza schematem albo błąd dostawcy modelu — wpis MUST niezmiennie nieść przyczynę, a kandydaci MUST
być policzeni jako nieprzesiani.

#### Scenario: Brak modelu

- **WHEN** wyszukiwanie znajduje filmy, a moduł nie ma skonfigurowanego modelu
- **THEN** wpis MUST liczyć ich jako nieprzesianych i MUST wskazać brak modelu jako przyczynę

### Requirement: Wpisy starsze niż 30 dni są usuwane

Moduł MUST usuwać wpisy przebiegów starsze niż 30 dni, bez udziału operatora, tak żeby historia nie rosła bez końca.

#### Scenario: Stary wpis

- **WHEN** moduł zapisuje nowy wpis, a w historii jest wpis sprzed 31 dni
- **THEN** stary wpis MUST zniknąć, a wpisy młodsze MUST pozostać

### Requirement: Historia jest do odczytu przez REST, a ostatni wynik niesie temat

Moduł MUST udostępniać odczyt historii od najnowszego wpisu, z możliwością zawężenia do jednego tematu i do zakresu czasu
oraz z ograniczoną liczbą wpisów. Początek zakresu MUST być włączony, a koniec wyłączony; znacznik czasu bez strefy MUST być
rozumiany jako UTC; zakres, w którym koniec nie następuje po początku, MUST zostać odrzucony z powodem. Zawężenia MUST się
łączyć. Odczyt MUST NOT niczego zapisywać ani pytać źródła. Lista tematów MUST nieść wynik ostatniego przebiegu każdego tematu
albo jego brak. Agent MUST NOT dostać do historii osobnego narzędzia.

#### Scenario: Zawężenie do tematu

- **WHEN** operator czyta historię tematu A, a w historii są też przebiegi tematu B
- **THEN** odpowiedź MUST zawierać wyłącznie przebiegi tematu A, najnowszy pierwszy

#### Scenario: Zawężenie do zakresu czasu

- **WHEN** operator czyta historię z zakresem obejmującym dwa z pięciu przebiegów
- **THEN** odpowiedź MUST zawierać wyłącznie te dwa, najnowszy pierwszy, a przebieg dokładnie na końcu zakresu MUST zostać pominięty

#### Scenario: Zakres i temat razem

- **WHEN** operator zawęża historię jednocześnie do tematu i do zakresu czasu
- **THEN** odpowiedź MUST zawierać wyłącznie przebiegi tego tematu z tego zakresu

#### Scenario: Zakres odwrócony

- **WHEN** operator prosi o historię, w której koniec zakresu nie następuje po jego początku
- **THEN** moduł MUST odmówić z powodem i MUST NOT zwrócić żadnych wpisów

#### Scenario: Temat bez przebiegu

- **WHEN** temat został dodany i jeszcze nie był szukany
- **THEN** lista tematów MUST pokazać brak ostatniego przebiegu

### Requirement: Terminal pokazuje historię przebiegów

Zakładka Kandydaci w terminalu MUST mieć widok Historia, pokazujący przebiegi od najnowszego, z możliwością zawężenia do
tematu i do dni: moment, temat, wynik, liczby raportu, a dla przebiegu `failed` i `skipped` przyczynę po polsku. Dni MUST
być wybierane w czasie lokalnym operatora, oba końce włącznie, a widok MUST pozwalać zawężenie wyczyścić. Zakładka Tematy MUST
pokazywać przy każdym temacie wynik jego ostatniego przebiegu.

#### Scenario: Przebieg, który się nie udał

- **WHEN** operator otwiera Historię, a ostatni przebieg tematu zakończył się błędem źródła
- **THEN** wiersz MUST pokazywać wynik „nieudany” i przyczynę

#### Scenario: Pusta historia

- **WHEN** żaden temat nie był jeszcze szukany
- **THEN** widok MUST powiedzieć, że nie było jeszcze przebiegów, a nie pozostać pusty bez słowa

#### Scenario: Wybór dni

- **WHEN** operator wybiera dzień początkowy i końcowy
- **THEN** widok MUST pokazać przebiegi od początku pierwszego do końca ostatniego z tych dni w jego czasie lokalnym

#### Scenario: Pusty zakres

- **WHEN** w wybranych dniach nie było przebiegów
- **THEN** widok MUST powiedzieć, że w tych dniach nie było przebiegów, i pozwolić zawężenie wyczyścić

### Requirement: Temat odroczony po porażce mówi, do kiedy

Lista tematów MUST podawać przy każdym temacie moment, przed którym nie zostanie on wyszukany z powodu odroczenia po porażce,
albo jego brak. Zakładka Tematy w terminalu MUST pokazywać ten moment przy temacie, dopóki nie minął.

#### Scenario: Temat odroczony

- **WHEN** wyszukiwanie tematu z odstępem 6 godzin zostało odrzucone przez źródło o 10:00
- **THEN** lista tematów MUST podawać 16:00 jako najwcześniejszą następną próbę, a terminal MUST to pokazać przy temacie

#### Scenario: Temat bez odroczenia

- **WHEN** temat nigdy nie zawiódł albo jego ostatnie wyszukiwanie się udało
- **THEN** lista tematów MUST podawać brak odroczenia

