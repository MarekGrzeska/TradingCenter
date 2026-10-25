## ADDED Requirements

### Requirement: Koszty od brokera przez archiwum w procesie

Pakiet MUST publikować `POST /costs/{symbol}/from-broker`, które pobiera profil kosztów od brokera i zapisuje go w
miejsce dotychczasowego, oraz MUST podawać w każdym odczycie profilu jego źródło, chwilę ustalenia i surowe wartości
brokera. Pakiet MUST czytać warunki i ceny instrumentu wyłącznie przez REST archiwum `/market` w tym procesie, a wymaganie
„Pakiet nie ma drogi do rachunku” zostaje w mocy.

#### Scenario: Odświeżenie profilu z brokera

- **WHEN** operator prosi o profil instrumentu od brokera
- **THEN** profil MUST zostać zastąpiony wartościami brokera ze źródłem „broker” i chwilą pobrania

#### Scenario: Broker nie odpowiada

- **WHEN** archiwum nie może zapytać brokera
- **THEN** odpowiedź MUST być odmową nazywającą przyczynę, a dotychczasowy profil MUST pozostać bez zmian
