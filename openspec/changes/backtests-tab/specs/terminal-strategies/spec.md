## ADDED Requirements

### Requirement: Backtesty mają własną zakładkę

Formularz uruchomienia, lista uruchomień i raport MUST stać w osobnej zakładce Backtests, a nie w zakładce Strategies.
Zakładka Backtests MUST pozwalać wybrać strategię albo pokazać uruchomienia wszystkich strategii. Lista wszystkich MUST
nazywać strategię każdego uruchomienia. Formularz MUST być dostępny dla wybranej strategii. Raport MUST być rysowany na
instrumencie i interwale rewizji, z której powstało uruchomienie. Zakładka Strategies MUST mieć przy otwartej strategii
odnośnik, który otwiera Backtests z tą strategią wybraną. Po każdej turze agenta zakładka Backtests MUST na nowo
przeczytać uruchomienia.

#### Scenario: Uruchomienia dwóch strategii obok siebie

- **WHEN** operator otwiera Backtests bez wybranej strategii
- **THEN** lista MUST pokazywać uruchomienia wszystkich strategii, każde z nazwą swojej strategii

#### Scenario: Z zakładki Strategies do backtestów

- **WHEN** operator klika „Backtesty tej strategii” przy otwartej strategii
- **THEN** zakładka Backtests MUST się otworzyć z tą strategią wybraną i jej formularzem uruchomienia
