## ADDED Requirements

### Requirement: Wycofany zespół przestaje działać sam

Wycofanie zespołu MUST w tej samej transakcji wyłączyć każdy jego harmonogram i każdy wyzwalacz, zostawiając
powód „zespół wycofany z katalogu”. Po wycofaniu nic MUST NOT uruchomić przebiegu tego zespołu bez ręcznego
działania operatora.

Operator rozumie wycofanie jako „ten zespół już nic nie robi”. Zespół na koncie realnym, który po wycofaniu
nadal składa zlecenia z harmonogramu, jest dokładnie tym, przed czym ta decyzja miała chronić.

#### Scenario: Wycofanie zespołu z włączonymi harmonogramami

- **WHEN** operator wycofuje zespół, który ma włączone harmonogramy i wyzwalacze
- **THEN** każdy z nich jest wyłączony z powodem „zespół wycofany z katalogu”
- **AND** zegar nie uruchamia już żadnego przebiegu tego zespołu

### Requirement: Wycofany zespół da się odnaleźć i przywrócić

Moduł MUST udostępniać listę wycofanych zespołów właściciela, każdy z momentem wycofania, i MUST pozwalać
przywrócić wycofany zespół do katalogu. Przywrócenie MUST NOT włączyć żadnego harmonogramu ani wyzwalacza —
operator włącza każdy z nich sam. Zespół cudzy albo niewycofany MUST odpowiadać na przywrócenie tak jak
nieistniejący.

Przywrócenie zespołu na koncie realnym, które samo wznawia handel, byłoby drugim skutkiem ukrytym za jednym
kliknięciem — tym samym błędem co wycofanie, które go nie zatrzymywało.

#### Scenario: Przywrócenie pomyłkowo wycofanego zespołu

- **WHEN** operator przywraca wycofany zespół
- **THEN** zespół wraca do katalogu z tymi samymi rewizjami i przebiegami
- **AND** jego harmonogramy i wyzwalacze pozostają wyłączone

#### Scenario: Lista wycofanych

- **WHEN** terminal pyta o wycofane zespoły
- **THEN** dostaje tylko zespoły tego operatora, które są wycofane, z momentem wycofania
