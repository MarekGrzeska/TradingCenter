## MODIFIED Requirements

### Requirement: Kontrakt czyta archiwum i zarządza listą obserwacji

Kontrakt MUST pozwalać odczytać filmy oknem czasu z zawężeniem po kanale, temacie, najniższej ocenie i stanie, w
porządku określonym przez kontrakt; odczytać jeden film ze wszystkimi jego odczytami; odczytać transkrypcję filmu
stronami; odczytać, dopisać, spauzować i zdjąć kanały oraz tematy i zmienić ich prompt; wskazać film do analizy
adresem, opcjonalnie z promptem; zamówić odczyt filmu wybranym promptem; zarządzać promptami. Zawężenie po
instrumencie MUST NOT być częścią kontraktu. Lista filmów MUST NOT nieść treści transkrypcji ani tekstu odczytu.

#### Scenario: Okno bez sensu

- **WHEN** klient podaje okno, którego koniec jest wcześniejszy niż początek
- **THEN** kontrakt MUST odmówić z powodem, a nie zwrócić pustą listę

#### Scenario: Lista filmów

- **WHEN** klient odczytuje listę filmów
- **THEN** każdy film MUST nieść streszczenie i ocenę odczytu swoim promptem, bez tekstu odczytu

### Requirement: Pola odczytu są zawsze obecne

Pola odczytu modelu MUST być w odpowiedzi zawsze, a ich brak MUST być wartością pustą. Film MUST nieść swój prompt
oraz listę odczytów, każdy z promptem, wersją, modelem i momentem powstania; odczyt promptem filmu MUST być
rozpoznawalny bez porównywania nazw.

#### Scenario: Film nieodczytany

- **WHEN** klient odczytuje film bez odczytu
- **THEN** pola odczytu MUST być obecne i puste, a lista odczytów MUST być pusta
