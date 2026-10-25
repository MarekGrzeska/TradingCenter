## MODIFIED Requirements

### Requirement: Porównanie uruchomień przez REST

Pakiet MUST publikować `GET /runs/compare`, który przyjmuje od dwóch do pięciu różnych identyfikatorów uruchomień i
stosuje tę samą regułę porównywalności co `compare_runs`: ten sam zakres, ten sam model kosztów, ten sam wymagany depozyt i ta sama wersja silnika,
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
