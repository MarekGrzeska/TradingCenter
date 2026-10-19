## Why

Zdanie tworzy regułę, ale zmienić istniejącą trzeba ręcznie w formularzu: „podnieś próg do 1,12”, „niech raz na dwie
godziny”, „powiadamiaj przez drugiego bota” to dziś kilka kliknięć i przepisanie wartości. Szkic z zdania już umie
wypełnić formularz; brakuje tylko powiedzenia modelowi, **którą regułę** zdanie zmienia.

## What Changes

- **`POST /drafts` przyjmuje opcjonalne `rule_id`.** Z nim zdanie jest zmianą tej reguły: model dostaje jej obecną
  postać, zwraca regułę w całości, a wszystko, czego zdanie nie rusza, zostaje takie jak było — także pola, których
  model w ogóle nie wypełnia (`bot`, `max_per_hour`, `enabled`). Odpowiedź ma ten sam kształt `DraftOut` i przechodzi tę
  samą walidację co zapis. Nic nie jest zapisywane; koszt idzie na ten sam dobowy sufit tokenów szkiców.
- **Terminal.** Przy regule przycisk „Zmień zdaniem…” otwiera pole na zdanie; odpowiedź otwiera formularz „Edytuj”
  wypełniony zmienioną regułą. Zapisuje go operator, istniejącym `PUT /rules/{id}`.
- Nieznane `rule_id` to 404.

**Poza zakresem (następna zmiana):** to samo z rozmowy — narzędzie agenta zwracające szkic zmiany. Zmieni wymaganie
„Rozmowa widzi reguły i odpalenia, nie zmienia ich” z `alerts-api` (do czasu archiwizacji `alerts-package` nie ma go
jeszcze w `openspec/specs`, więc tu jest tylko dopisywanie). Poza zakresem także widok różnic starej i nowej reguły.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `alerts-drafts`: zdanie MAY zmieniać istniejącą regułę; szkic zmiany zachowuje to, czego zdanie nie dotyczy.
- `terminal-alerts`: reguła ma „Zmień zdaniem…”, które otwiera formularz edycji ze zmienioną regułą.

Kontrakt `contract.alerts` terminala jest regenerowany (`DraftIn.rule_id`).
