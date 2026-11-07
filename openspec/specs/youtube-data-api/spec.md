# youtube-data-api Specification

## Purpose
TBD - created by archiving change add-youtube-archive. Update Purpose after archive.
## Requirements
### Requirement: Kontrakt czyta archiwum i zarządza listą obserwacji

Kontrakt MUST pozwalać na:

- odczyt filmów oknem czasu z zawężeniem po kanale, temacie, najniższej ocenie i stanie, w porządku określonym przez
  kontrakt;
- odczyt jednego filmu ze wszystkimi jego odczytami;
- odczyt transkrypcji filmu stronami;
- odczyt, dopisanie, spauzowanie i zdjęcie kanałów oraz tematów, a także zmianę promptu kanału;
- wskazanie filmu do analizy adresem, opcjonalnie z promptem;
- zamówienie odczytu filmu wybranym promptem;
- zarządzanie promptami;
- odczyt kandydatów i podjęcie decyzji o kandydacie;
- odczyt, dopisanie i zdjęcie ignorowanych kanałów.

Zawężenie po instrumencie MUST NOT być częścią kontraktu. Temat MUST NOT nieść promptu ani przyjmować go w zapisie.
Lista filmów MUST NOT nieść treści transkrypcji ani tekstu odczytu.

#### Scenario: Okno bez sensu

- **WHEN** klient podaje okno, którego koniec jest wcześniejszy niż początek
- **THEN** kontrakt MUST odmówić z powodem, a nie zwrócić pustą listę

#### Scenario: Lista filmów

- **WHEN** klient odczytuje listę filmów
- **THEN** każdy film MUST nieść streszczenie i ocenę odczytu swoim promptem, bez tekstu odczytu

#### Scenario: Temat z promptem

- **WHEN** klient dopisuje temat, podając prompt
- **THEN** kontrakt MUST odmówić z powodem, że temat nie ma promptu

### Requirement: Pola odczytu są zawsze obecne

Pola odczytu modelu MUST być w odpowiedzi zawsze, a ich brak MUST być wartością pustą. Film MUST nieść swój prompt
oraz listę odczytów, każdy z promptem, wersją, modelem i momentem powstania; odczyt promptem filmu MUST być
rozpoznawalny bez porównywania nazw.

#### Scenario: Film nieodczytany

- **WHEN** klient odczytuje film bez odczytu
- **THEN** pola odczytu MUST być obecne i puste, a lista odczytów MUST być pusta

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

