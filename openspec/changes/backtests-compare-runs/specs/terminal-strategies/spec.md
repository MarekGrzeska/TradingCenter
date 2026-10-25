## ADDED Requirements

### Requirement: Porównanie zaznaczonych uruchomień w Backtests

Lista uruchomień w zakładce Backtests MUST pozwalać zaznaczyć zakończone uruchomienia, także różnych strategii, gdy
pokazuje wszystkie. Porównanie MUST być dostępne, gdy zaznaczone są od dwóch do pięciu, i MUST pokazywać tabelę: kolumnę
na uruchomienie z nazwą strategii, rewizją i parametrami oraz wiersz na metrykę. Gdy pakiet odmawia, zakładka MUST
pokazać każdą różnicę, którą odmowa nazywa, zamiast tabeli. Tabela MUST NOT wyróżniać lepszej wartości ani lepszego
uruchomienia. Uruchomienie niezakończone MUST NOT dać się zaznaczyć.

#### Scenario: Dwa warianty obok siebie

- **WHEN** operator zaznacza dwa zakończone uruchomienia o tym samym zakresie i kosztach i wybiera „Porównaj”
- **THEN** zakładka MUST pokazać tabelę z kolumną dla każdego, z nazwą strategii, rewizją i parametrami

#### Scenario: Różne koszty

- **WHEN** operator porównuje dwa uruchomienia, które różnią się kosztami
- **THEN** zakładka MUST pokazać odmowę nazywającą różnicę w kosztach, a MUST NOT pokazać tabeli
