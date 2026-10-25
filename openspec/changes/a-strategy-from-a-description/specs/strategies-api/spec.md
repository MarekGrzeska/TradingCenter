## ADDED Requirements

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
