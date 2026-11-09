## RENAMED Requirements

- FROM: `### Requirement: Handel dotyka wyłącznie konta demo`
- TO: `### Requirement: Handel na koncie realnym jest osiągalny tylko w procesie konta realnego`

## MODIFIED Requirements

### Requirement: Handel na koncie realnym jest osiągalny tylko w procesie konta realnego

Składanie zleceń, zamykanie pozycji, zmiana i anulowanie MUST działać w procesie demo wyłącznie na koncie demo, a na
koncie realnym wyłącznie w procesie, którego konfiguracja jawnie wybrała środowisko realne, i tylko w granicach, które
ta konfiguracja niesie (`capital-live-account`). Jeden proces MUST NOT obsługiwać obu środowisk naraz.

#### Scenario: Próba handlu poza demo

- **WHEN** moduł jest skonfigurowany na host inny niż demo bez jawnego wyboru środowiska realnego
- **THEN** nie startuje, więc żadna operacja handlowa nie jest osiągalna

#### Scenario: Proces konta realnego handluje w granicach

- **WHEN** proces z jawnie wybranym środowiskiem realnym przyjmuje zlecenie
- **THEN** zlecenie trafia do dostawcy tylko wtedy, gdy mieści się w granicach z jego konfiguracji
