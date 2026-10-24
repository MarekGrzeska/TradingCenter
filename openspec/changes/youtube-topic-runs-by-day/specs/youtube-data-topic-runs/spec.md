## MODIFIED Requirements

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
