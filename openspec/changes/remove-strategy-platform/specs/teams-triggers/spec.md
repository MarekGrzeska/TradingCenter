## REMOVED Requirements

### Requirement: Decyzja platformy strategii jest źródłem warunku

**Reason**: Platforma strategii zostaje usunięta (`remove-strategy-platform`), a z nią `pending_setups` — jedyne narzędzie, dla którego to wymaganie istniało. Mechanizm, którym wyzwalacz czyta liczbę po nazwie narzędzia i ścieżce pola, opisuje „Warunek jest czytany narzędziami serwera narzędzi” i zostaje bez zmian.

**Migration**: Wyzwalacz zapisany wcześniej na `pending_setups` zgłasza przy sprawdzeniu, że żadne skonfigurowane źródło nie ogłasza tej nazwy, i nie budzi zespołu. Operator usuwa go albo przepina na inne narzędzie; nowa platforma, jeśli zechce budzić zespoły, wniesie własne wymaganie.
