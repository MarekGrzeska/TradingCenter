## Purpose

Zakładka YouTube w terminalu: filmy z odczytami, lista kanałów i tematów do ręcznej edycji oraz
pasek mówiący, czy archiwum pracuje i ile kosztuje.

## ADDED Requirements

### Requirement: Zakładka pokazuje filmy z odczytem

Zakładka MUST pokazywać ostatnie filmy, najnowsze najpierw, z kanałem, stanem, oceną wpływu i
kierunkiem sentymentu per instrument, oraz nazywać okno i liczbę filmów. Szczegół filmu MUST
pokazywać streszczenie, tezy, prognozy, zwiniętą transkrypcję i odnośnik do filmu na YouTube.
Film nieodczytany MUST NOT pokazywać oceny zastępczej.

#### Scenario: Film bez odczytu

- **WHEN** film nie ma odczytu
- **THEN** karta MUST pokazać jego stan zamiast oceny

### Requirement: Operator edytuje listę obserwacji

Zakładka MUST pozwalać dopisać kanał adresem albo uchwytem, dopisać temat, zmienić regułę alertu,
spauzować i zdjąć obserwację oraz wskazać pojedynczy film do analizy. Odmowa kontraktu — sufit,
nieznany kanał — MUST być pokazana z powodem.

#### Scenario: Kanał nie istnieje

- **WHEN** operator dopisuje adres, który nie jest kanałem
- **THEN** ekran MUST pokazać powód odmowy i MUST NOT dodać pozycji do listy

### Requirement: Pasek stanu nazywa to, czego lista nie powie

Zakładka MUST pokazywać zużycie każdego dostawcy wobec sufitu, dostawcę zablokowanego, model
nieskonfigurowany, archiwum nieświeże oraz pracę na symulacji. Pusta lista MUST NOT być jedyną
odpowiedzią na którykolwiek z tych stanów.

#### Scenario: Praca na symulacji

- **WHEN** moduł działa na symulowanych dostawcach
- **THEN** zakładka MUST to pokazywać stale, a nie tylko przy pojedynczym filmie

### Requirement: Nieudane odświeżenie nie czyści ekranu

Zakładka MUST odświeżać się sama, a nieudane odświeżenie MUST NOT kasować tego, co jest na ekranie.

#### Scenario: Odświeżenie nie dochodzi

- **WHEN** odświeżenie kończy się błędem, a lista jest wypełniona
- **THEN** poprzednie filmy MUST zostać na ekranie
