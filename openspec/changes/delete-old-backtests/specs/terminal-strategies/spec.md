## ADDED Requirements

### Requirement: Usuwanie uruchomień w Backtests

Lista uruchomień w zakładce Backtests MUST pozwalać zaznaczyć uruchomienia zakończone, nieudane i anulowane do usunięcia
i MUST oferować „Usuń” dla zaznaczonych, po potwierdzeniu, które mówi, ile uruchomień zniknie, że nie da się tego cofnąć
i że licznik prób strategii zostaje. Uruchomienie czekające albo liczone MUST NOT dać się zaznaczyć do usunięcia. Po
usunięciu lista MUST odświeżyć się bez przeładowania strony, a otwarty raport usuniętego uruchomienia MUST się zamknąć.
Odmowa pakietu MUST być pokazana słowami, bez usunięcia czegokolwiek.

#### Scenario: Usunięcie zaznaczonych

- **WHEN** operator zaznacza dwa zakończone uruchomienia, wybiera „Usuń” i potwierdza
- **THEN** oba MUST zniknąć z listy
- **AND** licznik prób strategii MUST pozostać taki, jaki był

#### Scenario: Uruchomienie w toku

- **WHEN** na liście jest uruchomienie w stanie `running`
- **THEN** jego pole zaznaczenia do usunięcia MUST być wyłączone

#### Scenario: Otwarty raport usuniętego uruchomienia

- **WHEN** operator ma otwarty raport uruchomienia, które usuwa
- **THEN** raport MUST się zamknąć po usunięciu

#### Scenario: Odmowa pakietu

- **WHEN** pakiet odmawia usunięcia, bo jedno z uruchomień zaczęło się liczyć
- **THEN** zakładka MUST pokazać odmowę nazywającą to uruchomienie, a lista MUST pozostać nietknięta
