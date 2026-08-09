# market-data-database-connection — delta

## MODIFIED Requirements

### Requirement: Połączenie z bazą jest szyfrowane

Gdy baza stoi poza maszyną modułu, ruch do niej przechodzi przez sieć, której moduł nie
kontroluje — takie połączenie MUST być wyłącznie szyfrowane. Konfiguracja wskazująca hosta
zdalnego, która szyfrowania nie wymusza, MUST być odrzucona przy starcie — moduł MUST NOT
połączyć się nieszyfrowanie ani ciszej obniżyć wymagania, gdy szyfrowane połączenie się nie
uda. Baza na pętli zwrotnej tej samej maszyny MAY być osiągana bez szyfrowania — ruch do niej
sieci nie opuszcza.

#### Scenario: Konfiguracja nie wymusza szyfrowania

- **WHEN** moduł startuje w trybie tożsamości z konfiguracją połączenia do hosta zdalnego,
  która nie wymaga szyfrowania
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje konfigurację połączenia jako przyczynę

#### Scenario: Serwer nie oferuje szyfrowania

- **WHEN** serwer zdalnej bazy odrzuca zestawienie połączenia szyfrowanego
- **THEN** moduł nie nawiązuje połączenia nieszyfrowanego
- **AND** zgłasza błąd połączenia

#### Scenario: Baza lokalna bez szyfrowania

- **WHEN** moduł startuje bez skonfigurowanej tożsamości, a `DATABASE_URL` wskazuje pętlę
  zwrotną bez `sslmode`
- **THEN** moduł startuje i łączy się z bazą

### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Wobec bazy zdalnej moduł MUST uwierzytelniać się poświadczeniem wystawianym dla jego
tożsamości i pobieranym przy nawiązywaniu połączenia; trwałe hasło do bazy zdalnej MUST NOT
być wymagane do pracy modułu ani przechowywane w jego konfiguracji. Tryb tożsamości wybiera
skonfigurowana nazwa roli (`DATABASE_USER`); konfiguracja trybu tożsamości, której
`DATABASE_URL` niesie własne poświadczenie, MUST być odrzucona przy starcie.

#### Scenario: Poświadczenia nie da się uzyskać

- **WHEN** moduł startuje w trybie tożsamości, a wystawca poświadczeń jest nieosiągalny lub
  odmawia
- **THEN** moduł odmawia startu z komunikatem wskazującym uzyskanie poświadczenia jako
  przyczynę
- **AND** MUST NOT sięgać po zapasowe hasło ani ponawiać w nieskończonej pętli bez zgłoszenia
  błędu

#### Scenario: Poświadczenie w URL obok tożsamości

- **WHEN** moduł startuje w trybie tożsamości, a `DATABASE_URL` niesie nazwę użytkownika lub
  hasło
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że poświadczenie z URL nie byłoby użyte

## ADDED Requirements

### Requirement: Praca bez tożsamości nie wychodzi poza maszynę

Baza lokalna — w kontenerze na maszynie deweloperskiej — MAY być osiągana hasłem niesionym w
`DATABASE_URL`. Ta furtka MUST być ograniczona do pętli zwrotnej: bez skonfigurowanej
tożsamości moduł MUST NOT nawiązać połączenia z hostem innym niż pętla zwrotna i MUST odmówić
startu z taką konfiguracją, wskazując brak tożsamości jako przyczynę. Chroni to przed dwiema
pomyłkami naraz: lokalnym modułem piszącym do produkcji oraz poświadczeniem ambientowym
maszyny (sesją operatora), które uwierzytelniłoby moduł jako kogoś, kim nie jest.

#### Scenario: Baza lokalna na haśle

- **WHEN** moduł startuje bez `DATABASE_USER`, a `DATABASE_URL` wskazuje pętlę zwrotną i
  niesie hasło
- **THEN** moduł łączy się z bazą używając URL dosłownie

#### Scenario: Host zdalny bez tożsamości

- **WHEN** moduł startuje bez `DATABASE_USER`, a `DATABASE_URL` wskazuje hosta spoza pętli
  zwrotnej
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że praca bez tożsamości jest ograniczona do bazy lokalnej

#### Scenario: Narzędzie deweloperskie odmawia wcześniej

- **WHEN** skrypt uruchamiający środowisko lokalne czyta `.env` wskazujący hosta spoza pętli
  zwrotnej
- **THEN** skrypt odmawia startu przed uruchomieniem czegokolwiek
- **AND** komunikat wskazuje `.env` i wymaganie bazy lokalnej
