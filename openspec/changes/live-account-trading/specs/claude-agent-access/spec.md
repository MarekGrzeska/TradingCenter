## ADDED Requirements

### Requirement: Zapis na koncie realnym ma własny przełącznik

Narzędzia serwera konta realnego, które zmieniają rachunek, MUST być zabronione, dopóki konfiguracja wdrożenia jawnie
nie włączy zapisu na koncie realnym — osobnym ustawieniem, niezależnym od włączenia zapisu na demo. Włączenie zapisu na
demo MUST NOT otwierać zapisu na koncie realnym. Odczyt konta realnego MAY być dozwolony bez przełącznika. Po włączeniu
agent MUST wołać narzędzie zapisujące konto realne dopiero po potwierdzeniu operatora w tej samej rozmowie, które nazywa
konto realne, instrument, kierunek i wielkość.

#### Scenario: Zapis na demo włączony, na koncie realnym nie

- **WHEN** zapis na demo jest włączony, zapis na koncie realnym nie, a operator prosi o zlecenie na koncie realnym
- **THEN** wywołanie narzędzia konta realnego jest odrzucone, a agent mówi, że zapis na koncie realnym jest wyłączony

#### Scenario: Zapis na koncie realnym włączony

- **WHEN** zapis na koncie realnym jest włączony, a agent proponuje zlecenie
- **THEN** agent podaje konto realne, instrument, kierunek i wielkość i czeka na potwierdzenie operatora
- **AND** woła narzędzie dopiero po nim
