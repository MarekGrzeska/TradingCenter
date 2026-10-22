## MODIFIED Requirements

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
