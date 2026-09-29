## Purpose

Lista obserwacji archiwum YouTube: kanały i tematy wyszukiwania, które decydują, jakie filmy moduł
w ogóle zauważa — kto je dopisuje, ile ich może być i jak się z listy wychodzi.

## ADDED Requirements

### Requirement: Obserwacja jest jawną decyzją operatora albo agenta

Moduł MUST zauważać wyłącznie filmy z kanałów na liście obserwacji, filmy znalezione przez temat na
tej liście oraz filmy wskazane pojedynczo do analizy. Kanał MUST dać się dopisać adresem kanału,
uchwytem `@nazwa` albo identyfikatorem; moduł MUST rozwiązać każdą z tych form do jednego
identyfikatora kanału, zanim zapisze obserwację.

#### Scenario: Dopisanie kanału uchwytem

- **WHEN** operator dopisuje kanał podając `@nazwa`
- **THEN** obserwacja MUST zostać zapisana pod identyfikatorem kanału, z jego tytułem

#### Scenario: Ten sam kanał dopisany drugi raz

- **WHEN** kanał już obserwowany zostaje dopisany inną formą adresu
- **THEN** lista MUST NOT urosnąć, a odpowiedź MUST wskazać istniejącą obserwację

#### Scenario: Kanał nie istnieje

- **WHEN** podany adres nie rozwiązuje się do żadnego kanału
- **THEN** moduł MUST odmówić z powodem i MUST NOT zapisać niczego

### Requirement: Temat niesie własne granice kosztu

Temat MUST nieść frazę, język, odstęp między wyszukiwaniami i największą liczbę filmów, które
jeden przebieg wyszukiwania może skierować do analizy. Temat bez tych granic MUST NOT dać się
zapisać — wartości domyślne MUST pochodzić z ustawień modułu i MUST być widoczne w odpowiedzi.

#### Scenario: Dopisanie tematu bez granic

- **WHEN** temat zostaje dopisany samą frazą
- **THEN** zapis MUST nieść granice domyślne, a odpowiedź MUST je pokazywać

### Requirement: Lista ma znany sufit, wspólny dla obu powierzchni

Liczba obserwowanych kanałów i liczba tematów MUST mieć sufit z ustawień. Dopisanie ponad sufit
MUST być odmówione z powodem nazywającym sufit — tak samo przez REST, jak przez narzędzie.

#### Scenario: Agent uderza w sufit

- **WHEN** narzędzie próbuje dopisać kanał ponad sufit
- **THEN** MUST dostać odmowę odsyłającą do operatora
- **AND** MUST NOT robić miejsca kosztem obserwacji, której nie zakładało

### Requirement: Zdjęcie z listy jest wyłącznie drogą operatora

Zdjęcie kanału albo tematu z listy MUST być osiągalne wyłącznie trasą REST. Pauza obserwacji MUST
zatrzymywać odkrywanie bez usuwania czegokolwiek. Zdjęcie z listy MUST NOT kasować filmów ani
odczytów, które już zebrano.

#### Scenario: Operator zdejmuje kanał

- **WHEN** operator zdejmuje kanał z listy
- **THEN** moduł MUST przestać odkrywać jego filmy
- **AND** filmy i odczyty tego kanału MUST zostać osiągalne

#### Scenario: Agent szuka drogi do zdjęcia kanału

- **WHEN** model przegląda narzędzia modułu
- **THEN** MUST NOT znaleźć narzędzia zdejmującego obserwację
