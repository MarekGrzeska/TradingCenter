## ADDED Requirements

### Requirement: Osoba bez roli admin nie dostaje terminala

Terminal skonfigurowany z tożsamością MUST po zalogowaniu zapytać workbench o rolę (`GET /me`) i pokazać ekran
„brak dostępu" z wylogowaniem każdemu, kto nie ma roli `admin` — także `viewerowi`, który ma pocket. Odmowa z tego
powodu MUST NOT być pokazywana jako niedostępność źródeł ani wywoływać ponownego logowania. Terminal bez
skonfigurowanej tożsamości MUST działać jak dotąd.

#### Scenario: Viewer otwiera terminal

- **WHEN** `viewer` loguje się do terminala
- **THEN** widzi ekran braku dostępu z informacją, że jego konto korzysta z pocket
- **AND** terminal nie woła żadnej trasy poza `GET /me`

#### Scenario: Praca lokalna

- **WHEN** terminal startuje bez skonfigurowanej tożsamości
- **THEN** pokazuje aplikację, bez pytania o rolę
