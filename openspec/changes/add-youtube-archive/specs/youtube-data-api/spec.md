## Purpose

Kontrakt REST archiwum YouTube dla terminala: odczyt filmów i listy obserwacji, jej edycja przez
operatora, trasa stanu i to, kto po którą powierzchnię może sięgnąć.

## ADDED Requirements

### Requirement: Kontrakt czyta archiwum i zarządza listą obserwacji

Kontrakt MUST pozwalać odczytać filmy oknem czasu z zawężeniem po kanale, temacie, instrumencie,
najniższej ocenie i stanie, w porządku określonym przez kontrakt; odczytać jeden film z odczytem;
odczytać transkrypcję filmu stronami; odczytać, dopisać, spauzować i zdjąć kanały oraz tematy;
wskazać film do analizy adresem. Lista filmów MUST NOT nieść treści transkrypcji.

#### Scenario: Okno bez sensu

- **WHEN** klient podaje okno, którego koniec jest wcześniejszy niż początek
- **THEN** kontrakt MUST odmówić z powodem, a nie zwrócić pustą listę

### Requirement: Pola odczytu są zawsze obecne

Pola odczytu modelu MUST być w odpowiedzi zawsze, a ich brak MUST być wartością pustą.

#### Scenario: Film nieodczytany

- **WHEN** klient odczytuje film bez odczytu
- **THEN** pola odczytu MUST być obecne i puste

### Requirement: Trasa stanu mówi, co moduł robi i czego nie może

Trasa stanu MUST nieść: wybranych dostawców i stan każdego (czynny, zablokowany, sufit osiągnięty),
dzienne zużycie i sufit każdego dostawcy, to, czy model jest skonfigurowany, to, czy alerty mają
adresata, czy działa symulacja, liczby filmów w każdym stanie oraz wiek ostatniego ukończonego
przebiegu pętli mierzony w jej interwałach. Przebieg zakończony błędem MUST NOT zerować tego wieku.

#### Scenario: Pętla stanęła

- **WHEN** pętla nie ukończyła przebiegu od wielu interwałów
- **THEN** wiek w trasie stanu MUST rosnąć, pozwalając nazwać archiwum nieświeżym

### Requirement: Dostęp rozstrzyga zapis wołających

Moduł MUST trzymać własny zapis, który identyfikator aplikacji ma prawo do której powierzchni, MUST
odmawiać ścieżkom spoza zapisu i MUST odmawiać wszystkim z sieci przy pustym zapisie. Sonda zdrowia
MUST odpowiadać bez tożsamości, nazywać moduł i MUST NOT nieść wieku przebiegu.

#### Scenario: Ścieżka spoza zapisu

- **WHEN** żądanie trafia na ścieżkę, której zapis nie wymienia
- **THEN** moduł MUST odmówić

### Requirement: Kontrakt jest źródłem typów terminala

Kształt odpowiedzi MUST być opisany dokumentem OpenAPI drukowanym z modeli modułu bez serwera i bez
bazy, a rozjazd z wygenerowanym plikiem w terminalu MUST wywracać CI.

#### Scenario: Zmiana kształtu bez odświeżenia

- **WHEN** moduł zmienia kształt odpowiedzi, a wygenerowany kontrakt w terminalu nie został
  odświeżony
- **THEN** CI MUST odmówić przejścia
