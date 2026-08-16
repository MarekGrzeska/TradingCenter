## MODIFIED Requirements

### Requirement: Tura wie, co terminal właśnie rysuje

Żądanie tury MAY nieść migawkę tego, co konsument rysuje: symbol, interwał, włączone
wskaźniki wraz z parametrami oraz **widoczny fragment osi czasu** — od kiedy do kiedy
sięga to, co operator ma przed oczami. Moduł MUST podać ją modelowi jako kontekst tury.

Widoczny fragment MUST być podany w skali absolutnej, tak jak kadr w poleceniu wykresu
(`agent-chart-control`, „Narzędzie ustawia zawartość aktywnego slotu"). Bez niego model
proszony o przesunięcie wykresu nie wie, skąd przesuwa, i „cofnij się o dzień" nie ma
punktu odniesienia.

Migawka MUST być opcjonalna: żądanie bez niej MUST działać tak jak dotąd, bo konsument bez
wykresu — a taki jest każdy inny niż terminal — nie ma czego wysłać. Poszczególne pola
migawki MUST być opcjonalne osobno: konsument, który rysuje wykres, ale nie umie powiedzieć,
co z niego widać, MUST móc przysłać samą resztę.

Migawka MUST NOT być zapisywana jako wiadomość w transkrypcie ani MUST NOT zmieniać
niczego po stronie modułu. Jest opisem chwili, w której padło pytanie, a nie stanem, który
moduł miałby odtąd trzymać.

#### Scenario: Pytanie o to, co widać

- **WHEN** operator pyta „co widzisz na tym wykresie", mając włączone dwa wskaźniki
- **THEN** model odpowiada z symbolu, interwału i tych dwóch wskaźników

#### Scenario: Pytanie o przesunięcie względem tego, co widać

- **WHEN** operator prosi „cofnij się o dzień", a migawka niosła widoczny fragment osi
- **THEN** model liczy nowy kadr od tego fragmentu, a nie od końca serii

#### Scenario: Żądanie bez migawki

- **WHEN** konsument wysyła turę bez migawki wykresu
- **THEN** tura toczy się jak dotąd

#### Scenario: Migawka bez widocznego fragmentu

- **WHEN** konsument wysyła migawkę z symbolem i interwałem, ale bez widocznego fragmentu osi
- **THEN** model dostaje symbol i interwał, a o kadrze nie dostaje nic — zamiast kadru zmyślonego

#### Scenario: Migawka nie trafia do transkryptu

- **WHEN** tura niosła migawkę wykresu
- **THEN** transkrypt niesie pytanie operatora i wypowiedź agenta, bez migawki
