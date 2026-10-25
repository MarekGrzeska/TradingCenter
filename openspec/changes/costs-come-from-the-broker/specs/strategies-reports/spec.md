## ADDED Requirements

### Requirement: Raport mówi, skąd są koszty

Raport MUST podawać źródło kosztów uruchomienia: żądanie, profil od brokera (z chwilą pobrania), profil operatora albo
„bez kosztów”. Uruchomienie bez kosztów MUST być w raporcie oznaczone jako takie, którego wynik pomija spread,
poślizg i finansowanie. Oznaczenie MUST NOT być oceną strategii.

#### Scenario: Raport uruchomienia bez kosztów

- **WHEN** uruchomienie było bez kosztów
- **THEN** raport MUST mieć oznaczenie „bez kosztów” i źródło kosztów „bez kosztów”

#### Scenario: Raport z kosztami od brokera

- **WHEN** uruchomienie korzystało z profilu pobranego od brokera
- **THEN** raport MUST podawać źródło „broker” i chwilę pobrania profilu
