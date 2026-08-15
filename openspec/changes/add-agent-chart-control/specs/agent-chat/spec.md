## ADDED Requirements

### Requirement: Tura wie, co terminal właśnie rysuje

Żądanie tury MAY nieść migawkę tego, co konsument rysuje: symbol, interwał i włączone
wskaźniki wraz z parametrami. Moduł MUST podać ją modelowi jako kontekst tury.

Migawka MUST być opcjonalna: żądanie bez niej MUST działać tak jak dotąd, bo konsument bez
wykresu — a taki jest każdy inny niż terminal — nie ma czego wysłać.

Migawka MUST NOT być zapisywana jako wiadomość w transkrypcie ani MUST NOT zmieniać
niczego po stronie modułu. Jest opisem chwili, w której padło pytanie, a nie stanem, który
moduł miałby odtąd trzymać.

#### Scenario: Pytanie o to, co widać

- **WHEN** operator pyta „co widzisz na tym wykresie", mając włączone dwa wskaźniki
- **THEN** model odpowiada z symbolu, interwału i tych dwóch wskaźników

#### Scenario: Żądanie bez migawki

- **WHEN** konsument wysyła turę bez migawki wykresu
- **THEN** tura toczy się jak dotąd

#### Scenario: Migawka nie trafia do transkryptu

- **WHEN** tura niosła migawkę wykresu
- **THEN** transkrypt niesie pytanie operatora i wypowiedź agenta, bez migawki
