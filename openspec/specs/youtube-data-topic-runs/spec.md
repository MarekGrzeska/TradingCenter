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

#### Scenario: Przebieg znajduje nowe filmy

- **WHEN** wyszukiwanie tematu zwraca pięć wyników, z których dwa są już znane, a trzy stają się kandydatami
- **THEN** wpis MUST mieć wynik `found`, liczbę wyników 5, znanych 2 i trzech kandydatów rozbitych na proponowanych, odrzuconych i nieprzesianych

#### Scenario: Przebieg nie znajduje niczego nowego

- **WHEN** wyszukiwanie tematu zwraca wyłącznie filmy już znane
- **THEN** wpis MUST mieć wynik `nothing_new` i zerowych kandydatów, a wpis MUST istnieć

#### Scenario: Źródło zawodzi

- **WHEN** źródło odpowiada błędem albo informuje, że jego limit jest wyczerpany
- **THEN** wpis MUST mieć wynik `failed` i przyczynę podaną przez źródło
- **AND** termin następnego wyszukiwania tego tematu MUST pozostać taki, jak był, tak że temat jest próbowany ponownie w następnym przebiegu pętli

#### Scenario: Usunięty temat

- **WHEN** operator zdejmuje temat z listy
- **THEN** wpisy jego przebiegów MUST pozostać w historii

### Requirement: Pominięcie z powodu dnia źródła jest zapisywane raz na temat na dobę

Gdy dzień źródła nie starcza na wyszukiwanie, moduł MUST zapisać wpis `skipped` z przyczyną, ale MUST NOT zapisywać
kolejnego takiego wpisu dla tego samego tematu w tej samej dobie UTC. Wpis `failed` MUST być zapisywany przy każdej porażce.

#### Scenario: Dzień źródła nie starcza przez wiele przebiegów

- **WHEN** dzień źródła nie starcza na wyszukiwanie, a pętla przechodzi przez temat kilkanaście razy w tej samej dobie
- **THEN** historia tematu MUST zawierać z tej doby jeden wpis `skipped`

#### Scenario: Nowa doba

- **WHEN** dzień źródła nadal nie starcza po północy UTC
- **THEN** moduł MUST zapisać nowy wpis `skipped`

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

Moduł MUST udostępniać odczyt historii od najnowszego wpisu, z możliwością zawężenia do jednego tematu i z ograniczoną
liczbą wpisów. Odczyt MUST NOT niczego zapisywać ani pytać źródła. Lista tematów MUST nieść wynik ostatniego przebiegu
każdego tematu albo jego brak. Agent MUST NOT dostać do historii osobnego narzędzia.

#### Scenario: Zawężenie do tematu

- **WHEN** operator czyta historię tematu A, a w historii są też przebiegi tematu B
- **THEN** odpowiedź MUST zawierać wyłącznie przebiegi tematu A, najnowszy pierwszy

#### Scenario: Temat bez przebiegu

- **WHEN** temat został dodany i jeszcze nie był szukany
- **THEN** lista tematów MUST pokazać brak ostatniego przebiegu

### Requirement: Terminal pokazuje historię przebiegów

Zakładka Kandydaci w terminalu MUST mieć widok Historia, pokazujący przebiegi od najnowszego, z możliwością zawężenia do
tematu: moment, temat, wynik, liczby raportu, a dla przebiegu `failed` i `skipped` przyczynę po polsku. Zakładka Tematy MUST
pokazywać przy każdym temacie wynik jego ostatniego przebiegu.

#### Scenario: Przebieg, który się nie udał

- **WHEN** operator otwiera Historię, a ostatni przebieg tematu zakończył się błędem źródła
- **THEN** wiersz MUST pokazywać wynik „nieudany” i przyczynę

#### Scenario: Pusta historia

- **WHEN** żaden temat nie był jeszcze szukany
- **THEN** widok MUST powiedzieć, że nie było jeszcze przebiegów, a nie pozostać pusty bez słowa
