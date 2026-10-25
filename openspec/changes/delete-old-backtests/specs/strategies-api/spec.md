## ADDED Requirements

### Requirement: Usuwanie uruchomień przez REST

Pakiet MUST publikować `DELETE /runs`, który przyjmuje od jednego do dwudziestu różnych identyfikatorów uruchomień jako
powtórzony parametr `run_id` i usuwa je według `strategies-backtest`. Odpowiedź MUST nieść identyfikatory usuniętych
uruchomień. Uruchomienie, które nie istnieje, MUST dawać 404 z jego numerem. Uruchomienie czekające albo liczone MUST
dawać 409 z jego numerem i stanem. Brak identyfikatorów, więcej niż dwadzieścia albo powtórzone MUST dawać 422. Przy
każdej odmowie MUST NOT zostać usunięte żadne uruchomienie. Trasa MUST podlegać tej samej liście wołających i tej samej
roli co reszta tras pakietu.

#### Scenario: Usunięcie dwóch uruchomień

- **WHEN** operator wysyła `DELETE /runs?run_id=3&run_id=5` dla dwóch zakończonych uruchomień
- **THEN** odpowiedź MUST mieć kod 200 i wymieniać 3 i 5
- **AND** `GET /runs/3` MUST dawać 404

#### Scenario: Uruchomienie w toku

- **WHEN** jedno z podanych uruchomień jest w stanie `queued`
- **THEN** odpowiedź MUST mieć kod 409, nazywać to uruchomienie i jego stan, a pozostałe MUST NOT zostać usunięte

#### Scenario: Oglądający

- **WHEN** wołający z rolą `viewer` wysyła `DELETE /runs`
- **THEN** odpowiedź MUST być odmową dostępu i MUST NOT zostać usunięte żadne uruchomienie
