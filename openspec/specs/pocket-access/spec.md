# pocket-access Specification

## Purpose

Co pocket pokazuje osobie zależnie od jej roli: viewer widzi archiwum bez akcji zapisu, admin wszystko, osoba bez roli tylko ekran braku dostępu.

## Requirements
### Requirement: Viewer widzi trzy zakładki i żadnej akcji zapisu

Pocket MUST po zalogowaniu zapytać workbench o rolę (`GET /me`). Dla `viewera` MUST ukryć zakładkę Agent i MUST
NOT pokazywać żadnej akcji zapisu: śledzenia, usuwania i przenoszenia eventów, grup oraz „keep" w newsach.
Zapamiętana zakładka Agent MUST NOT otworzyć się viewerowi — pocket wraca na pierwszą dozwoloną. Ukrycie jest
wygodą; obroną jest bramka serwera.

#### Scenario: Viewer otwiera pocket

- **WHEN** zalogowany `viewer` otwiera pocket
- **THEN** pasek zakładek ma Polymarket, Posty i News
- **AND** karty eventów nie mają akcji edycji

#### Scenario: Zapamiętana zakładka Agent

- **WHEN** pocket pamiętał zakładkę Agent, a użytkownik jest teraz `viewerem`
- **THEN** pocket otwiera pierwszą dozwoloną zakładkę

#### Scenario: Admin w pocket

- **WHEN** zalogowany `admin` otwiera pocket
- **THEN** widzi wszystko jak dotąd

### Requirement: Osoba bez roli widzi ekran braku dostępu

Gdy `GET /me` zwraca pustą listę ról, albo workbench odmawia `403`, pocket MUST pokazać ekran „brak dostępu"
z możliwością wylogowania, a nie puste zakładki ani błędy źródeł.

#### Scenario: Gość bez roli

- **WHEN** gość bez roli loguje się do pocket
- **THEN** widzi ekran braku dostępu i przycisk wylogowania

