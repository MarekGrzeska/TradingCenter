# strategy-catalogue Specification

## Purpose
Kontrakt, który czyni ze strategii wpis katalogu, a nie projekt: co strategia deklaruje,
co zwraca, i czego nie wolno jej robić — tak, żeby dodanie kolejnej nie dotykało maszynerii
wokół.
## Requirements
### Requirement: Strategia jest wpisem katalogu, nie zmianą platformy

Strategia MUST być wpisem katalogu deklarującym: fakty, których potrzebuje (wskaźnik
z katalogu archiwum, rozdzielczość, parametry), własne parametry z zakresami oraz funkcję
oceny. Dodanie nowego wpisu MUST NOT wymagać zmiany we wspólnym runtime — pętli, bramkach,
zapisie decyzji, powierzchniach. Wymóg ten MUST być sprawdzany testem, nie pilnowany przy
review.

To jest ten sam ruch, którym archiwum rozwiązało wskaźniki: kontrakt wpisu raz, maszyneria
raz, każdy kolejny wpis to jeden plik. Platforma, w której druga strategia wymaga poprawek
w pętli, nie jest platformą — jest pierwszą strategią z ambicjami.

#### Scenario: Druga strategia wchodzi do katalogu

- **WHEN** do katalogu zostaje dodany drugi wpis strategii
- **THEN** żaden plik wspólnego runtime nie zmienia się
- **AND** obie strategie pracują równolegle na tych samych zasadach

#### Scenario: Parametr poza zadeklarowanym zakresem

- **WHEN** zestaw parametrów niesie wartość poza zakresem zadeklarowanym we wpisie
- **THEN** zestaw zostaje odrzucony z powodem nazywającym parametr i zakres

### Requirement: Ocena jest czystą funkcją

Funkcja oceny strategii MUST wyliczać decyzję wyłącznie z podanych faktów i parametrów:
MUST NOT wykonywać we/wy, MUST NOT czytać zegara ani innego stanu spoza argumentów. Te same
fakty i te same parametry MUST dawać tę samą decyzję.

Na tej własności stoi wszystko dalej: test jednostkowy na ręcznych faktach, odtworzenie
decyzji z zapisu i backtest wołający tę samą funkcję. Strategia, która „doczytuje" cokolwiek
sama, jest nietestowalna i nieodtwarzalna — czyli nie do przyjęcia w całości, nie w części.

#### Scenario: Dwa wywołania na tych samych wejściach

- **WHEN** funkcja oceny zostaje wywołana dwukrotnie z identycznymi faktami i parametrami
- **THEN** obie decyzje są identyczne

#### Scenario: Wpis sięga poza argumenty

- **WHEN** funkcja oceny wpisu wykonuje we/wy lub czyta zegar
- **THEN** MUST to wywrócić testy modułu, zanim zmiana zostanie wdrożona

### Requirement: Decyzja zawsze niesie powód i pochodzenie

Wynikiem oceny MUST być decyzja: wejście albo odmowa. Odmowa MUST nieść powód. Decyzja
o wejściu MUST nieść kierunek, poziomy (wejście, obrona, cel) oraz nazwane cechy, z których
powstała jej punktacja. Każda decyzja MUST wskazywać strategię i wersję zestawu parametrów,
którą została policzona.

„System nie handlował trzy tygodnie" musi być diagnozowalne jednym zapytaniem, a raport
z backtestu musi umieć powiedzieć, które cechy niosą przewagę — obie rzeczy stoją na tym
wymogu.

#### Scenario: Setup odrzucony przez bramkę strategii

- **WHEN** ocena kończy się odmową
- **THEN** decyzja niesie powód odmowy nazywający bramkę, która ją ucięła

#### Scenario: Decyzja wraca do swojego zestawu parametrów

- **WHEN** operator czyta zapisaną decyzję
- **THEN** decyzja wskazuje wersję zestawu parametrów, którą była policzona
- **AND** ten zestaw jest odczytywalny w brzmieniu z chwili decyzji

### Requirement: Pierwszym wpisem jest strategia odniesienia

Katalog MUST zawierać strategię odniesienia — celowo prostą, zbudowaną wyłącznie na
wskaźnikach już obecnych w katalogu archiwum — zanim wejdzie do niego jakakolwiek strategia
właściwa. Strategia odniesienia MUST przechodzić przez tę samą pętlę, ten sam zapis decyzji
i ten sam backtest co każda inna.

Baseline robi trzy rzeczy naraz: testuje szczerość kontraktu (banalna strategia wymagająca
zmian w runtime obnaża zły kontrakt), przeciera całą rurę przed napisaniem pierwszego
detektora nowej strategii i daje punkt odniesienia, z którym strategia właściwa musi wygrać,
żeby uzasadnić swoją złożoność.

#### Scenario: Katalog przed pierwszą strategią właściwą

- **WHEN** platforma rusza po raz pierwszy
- **THEN** katalog zawiera strategię odniesienia
- **AND** jej fakty nazywają wyłącznie wskaźniki już obecne w katalogu archiwum

