## MODIFIED Requirements

### Requirement: Obserwacja jest jawną decyzją operatora albo agenta

Moduł MUST czytać wyłącznie dwa rodzaje filmów: filmy z kanałów na liście obserwacji oraz filmy wskazane pojedynczo
do analizy. Temat na liście MUST tylko proponować kandydatów i MUST NOT wprowadzać filmów do archiwum. Kanał MUST
dać się dopisać na trzy sposoby: adresem kanału, uchwytem `@nazwa` albo identyfikatorem. Moduł MUST rozwiązać każdą
z tych form do jednego identyfikatora kanału, zanim zapisze obserwację.

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

Temat MUST nieść cztery granice:

- frazę;
- język;
- odstęp między wyszukiwaniami;
- największą liczbę wyników, które jedno wyszukiwanie może skierować do przesiewu.

Temat bez tych granic MUST NOT dać się zapisać. Wartości domyślne MUST pochodzić z ustawień modułu i MUST być
widoczne w odpowiedzi. Temat MUST NOT nieść promptu.

#### Scenario: Dopisanie tematu bez granic

- **WHEN** temat zostaje dopisany samą frazą
- **THEN** zapis MUST nieść granice domyślne, a odpowiedź MUST je pokazywać
