# market-data-database-connection Specification

## Purpose
Opisuje, na jakich warunkach `market-data` łączy się ze swoją bazą, gdy ta stoi poza maszyną modułu:
czym się przedstawia, jak radzi sobie z poświadczeniem, które wygasa, i kiedy odmawia pracy zamiast
działać w konfiguracji, która wygląda na działającą.
## Requirements
### Requirement: Połączenie z bazą jest szyfrowane

Baza stoi poza maszyną modułu, więc ruch do niej przechodzi przez sieć, której moduł nie kontroluje.
Moduł MUST nawiązywać połączenie wyłącznie szyfrowane. Konfiguracja, która szyfrowania nie wymusza,
MUST być odrzucona przy starcie — moduł MUST NOT połączyć się nieszyfrowanie ani ciszej obniżyć
wymagania, gdy szyfrowane połączenie się nie uda.

#### Scenario: Konfiguracja nie wymusza szyfrowania

- **WHEN** moduł startuje z konfiguracją połączenia, która nie wymaga szyfrowania
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje konfigurację połączenia jako przyczynę

#### Scenario: Serwer nie oferuje szyfrowania

- **WHEN** serwer bazy odrzuca zestawienie połączenia szyfrowanego
- **THEN** moduł nie nawiązuje połączenia nieszyfrowanego
- **AND** zgłasza błąd połączenia

### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Moduł MUST uwierzytelniać się w bazie poświadczeniem wystawianym dla jego tożsamości i pobieranym
przy nawiązywaniu połączenia. Trwałe hasło do bazy MUST NOT być wymagane do pracy modułu ani
przechowywane w jego konfiguracji.

#### Scenario: Poświadczenia nie da się uzyskać

- **WHEN** moduł startuje, a wystawca poświadczeń jest nieosiągalny lub odmawia
- **THEN** moduł odmawia startu z komunikatem wskazującym uzyskanie poświadczenia jako przyczynę
- **AND** MUST NOT sięgać po zapasowe hasło ani ponawiać w nieskończonej pętli bez zgłoszenia błędu

### Requirement: Wygasające poświadczenie jest odnawiane

Poświadczenie ma ograniczoną ważność, krótszą niż czas pracy modułu. Moduł MUST odnawiać je tak, by
połączenie nawiązywane po jego wygaśnięciu zestawiało się poprawnie. Wygaśnięcie poświadczenia
MUST NOT objawiać się jako trwałe zatrzymanie zapisu świec.

#### Scenario: Nowe połączenie po wygaśnięciu poświadczenia

- **WHEN** moduł pracuje dłużej niż okres ważności poświadczenia i potrzebuje nawiązać nowe
  połączenie z bazą
- **THEN** połączenie zestawia się na odnowionym poświadczeniu
- **AND** zapis świec trwa nieprzerwanie

#### Scenario: Odnowienie nie powiodło się

- **WHEN** odnowienie poświadczenia nie powiodło się
- **THEN** moduł zgłasza błąd wskazujący poświadczenie jako przyczynę
- **AND** MUST NOT raportować się jako zdrowy, dopóki nie odzyska połączenia z bazą

### Requirement: Poświadczenie nie wycieka do logów

Poświadczenie do bazy jest sekretem o krótkiej ważności, ale sekretem. Moduł MUST NOT umieszczać go
w logach, komunikatach błędów ani w odpowiedziach swoich tras — w szczególności tam, gdzie loguje
adres połączenia.

#### Scenario: Błąd połączenia trafia do logu

- **WHEN** nawiązanie połączenia z bazą kończy się błędem, a moduł loguje jego okoliczności
- **THEN** log zawiera host, port i nazwę bazy
- **AND** nie zawiera poświadczenia ani jego fragmentu
