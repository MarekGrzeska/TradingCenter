## MODIFIED Requirements

### Requirement: Lista uruchomień i ich stan

Zakładka MUST wymieniać uruchomienia otwartej strategii ze wszystkich rewizji, od najnowszego. Każde MUST pokazywać stan,
rewizję, zakres, zlecającego (operator albo agent) i główne metryki, wśród nich zwrot całkowity i zwrot roczny.
Lista MUST dawać się sortować po każdej metryce przy każdej szerokości panelu: jako tabela z nagłówkami, gdy panel jest
szeroki, i wyborem sortowania nad kartami, gdy jest wąski. Nieudane MUST pokazywać przyczynę. Dopóki
któreś uruchomienie czeka albo się liczy, zakładka MUST odświeżać ich stan, a gdy żadne nie czeka, MUST przestać.
Uruchomienie czekające albo liczone MUST dać się anulować.

#### Scenario: Uruchomienie się kończy

- **WHEN** liczone uruchomienie się kończy, gdy zakładka jest otwarta
- **THEN** jego stan i główne metryki MUST pojawić się bez przeładowania strony

#### Scenario: Uruchomienia o różnych zakresach

- **WHEN** lista zawiera uruchomienie z jedenastu lat i uruchomienie z niecałych trzech
- **THEN** każde MUST pokazywać zwrot roczny obok całkowitego, a sortowanie po zwrocie rocznym MUST je porządkować według niego

#### Scenario: Wąski panel

- **WHEN** panel jest za wąski na tabelę i lista pokazuje karty
- **THEN** nad kartami MUST stać wybór sortowania z tymi samymi metrykami co nagłówki tabeli
