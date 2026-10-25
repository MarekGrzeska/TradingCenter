# strategies-api Specification

## Purpose
Kontrakt REST pakietu strategii, kto może go wołać i czego pakiet nie robi: jest narzędziem badawczym bez
żadnej drogi do rachunku.
## Requirements
### Requirement: Kontrakt REST pakietu

Pakiet MUST publikować pod `/strategies` trasy: `GET /language` (opis języka), `POST /validate` (walidacja
bez zapisu), `GET` i `POST /strategies` (lista z licznikiem prób i utworzenie), `GET /strategies/{id}`,
`POST /strategies/{id}/revisions`, `GET /strategies/{id}/revisions/{n}`, `POST /strategies/{id}/archive` i
`/restore`, `POST /runs` (zakolejkowanie), `GET /runs` (lista, z filtrem strategii), `GET /runs/{id}` (stan i
raport), `GET /runs/{id}/trades` (transakcje stronami), `POST /runs/{id}/cancel` oraz `GET /health` (baza,
długość kolejki, uruchomienie w toku). Odmowa MUST nazywać swoją przyczynę i MUST NOT zdradzać błędu bazy.

#### Scenario: Zakolejkowanie uruchomienia

- **WHEN** operator wysyła `POST /runs` z rewizją, zakresem, parametrami i modelem kosztów
- **THEN** odpowiedź MUST przyjść od razu z identyfikatorem uruchomienia w stanie zakolejkowanym

### Requirement: Opis języka z tego samego źródła co walidacja

`GET /language` MUST opisywać sekcje dokumentu, dozwolone konstrukcje, funkcje własne z sygnaturami oraz
wskaźniki katalogu dostępne w danej chwili, i MUST powstawać z tego samego rejestru, z którego korzysta
walidacja. Funkcja, którą walidacja przyjmuje, MUST być w opisie, a funkcja z opisu MUST przechodzić walidację.

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wpis z wyjściem liniowym
- **THEN** `GET /language` MUST go wymieniać bez zmiany kodu pakietu strategii

### Requirement: Walidacja bez zapisu

`POST /validate` MUST zwracać dokładnie te błędy, które zwróciłby zapis tego samego dokumentu, i MUST NOT niczego
zapisywać ani liczyć jako próby.

#### Scenario: Dokument z błędami

- **WHEN** dokument z dwoma błędami trafia do `POST /validate`
- **THEN** odpowiedź MUST zawierać oba błędy
- **AND** liczba strategii i rewizji w bazie MUST pozostać bez zmian

### Requirement: Dostęp ma operator, nie oglądający

Trasy pakietu MUST przyjmować wołających wyłącznie z listy aplikacji pakietu i, na serwerze, wyłącznie osoby z
rolą `admin`. Osoba z rolą `viewer` MUST dostać odmowę na każdej trasie pakietu, także na odczycie.

#### Scenario: Oglądający czyta listę strategii

- **WHEN** osoba z rolą `viewer` wysyła `GET /strategies/strategies`
- **THEN** odpowiedź MUST być odmową

### Requirement: Pakiet nie ma drogi do rachunku

Pakiet MUST NOT mieć klienta, adresu ani ustawienia prowadzącego do `trading-mcp` albo do bramy capital.com i
MUST NOT publikować decyzji, zdarzeń ani powiadomień. Żadna trasa pakietu MUST NOT składać, zmieniać ani anulować
zlecenia.

#### Scenario: Przegląd zależności pakietu

- **WHEN** test odczytuje importy i ustawienia pakietu strategii
- **THEN** MUST NOT znaleźć importu klienta bramy ani `trading-mcp`, ani ustawienia z ich adresem

### Requirement: Trasy ekranu i agenta

Pakiet MUST publikować dodatkowo trasy:
- `GET /strategies/{id}/revisions`: lista rewizji od najnowszej, z numerem, autorem, czasem i hashem, bez dokumentów;
- `GET /strategies/{id}/revisions/{n}/changes`: zmiany względem poprzedniej rewizji albo rewizji wskazanej w `against`;
- `GET /costs`, `GET /costs/{symbol}` i `PUT /costs/{symbol}`: profile kosztów instrumentów.

Odpowiedź `POST /validate` dla poprawnego dokumentu i każdy odczyt rewizji MUST nieść streszczenie. `POST
/strategies/{id}/revisions` MUST przyjmować rewizję bazową i odpowiadać na konflikt kodem 409 z numerem ostatniej
rewizji. Pozycje `GET /runs` MUST nieść zlecającego i główne metryki (liczbę transakcji, sumę i wartość oczekiwaną w R,
największe obsunięcie w R, Sharpe'a), ale nadal bez pełnego raportu.

#### Scenario: Lista uruchomień z metrykami

- **WHEN** wołający czyta `GET /runs` dla strategii z zakończonymi uruchomieniami
- **THEN** każda zakończona pozycja MUST nieść główne metryki i zlecającego, a MUST NOT nieść pełnego raportu

#### Scenario: Konflikt zapisu

- **WHEN** `POST /strategies/{id}/revisions` wskazuje podstawę 4, a ostatnią rewizją jest 5
- **THEN** odpowiedź MUST mieć kod 409 i numer 5

### Requirement: Raport ma kształt w kontrakcie

`GET /runs/{id}` MUST opisywać raport jako nazwany model z każdym polem z `strategies-reports`, tak żeby wygenerowany
kontrakt konsumenta znał typ każdego pola. Słownik o dowolnych kluczach MUST NOT stać w miejscu pola o znanym kształcie.

#### Scenario: Pole raportu się zmienia

- **WHEN** zmienia się nazwa albo typ pola raportu
- **THEN** sprawdzenie wygenerowanego kontraktu terminala MUST wykazać rozbieżność

### Requirement: Porównanie uruchomień przez REST

Pakiet MUST publikować `GET /runs/compare`, który przyjmuje od dwóch do pięciu różnych identyfikatorów uruchomień i
stosuje tę samą regułę porównywalności co `compare_runs`: ten sam zakres, ten sam model kosztów i ta sama wersja silnika,
każde uruchomienie zakończone. Odpowiedź MUST zestawiać, w kolejności podanej przez wołającego, dla każdego uruchomienia
jego strategię, rewizję, parametry i metryki raportu, opisane w kontrakcie nazwanym modelem. Gdy uruchomienia nie są
porównywalne, odpowiedź MUST mieć kod 422 i MUST nazywać każdą różnicę i uruchomienie, którego dotyczy. Uruchomienie,
które nie istnieje, MUST dawać 404 z jego numerem. Mniej niż dwa, więcej niż pięć albo powtórzone identyfikatory MUST
dawać 422. Odpowiedź MUST NOT wskazywać lepszego uruchomienia.

#### Scenario: Porównywalne uruchomienia dwóch strategii

- **WHEN** wołający pyta o dwa zakończone uruchomienia różnych strategii o tym samym zakresie, kosztach i silniku
- **THEN** odpowiedź MUST mieć kod 200 i zestawiać metryki obu, każde ze swoją strategią i rewizją

#### Scenario: Różny zakres

- **WHEN** wołający pyta o dwa uruchomienia o różnych zakresach
- **THEN** odpowiedź MUST mieć kod 422 i nazywać zakres każdego z nich

#### Scenario: Jedno uruchomienie

- **WHEN** wołający podaje jeden identyfikator
- **THEN** odpowiedź MUST mieć kod 422

