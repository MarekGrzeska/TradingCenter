## Purpose

Opisuje, na jakich warunkach moduł agenta łączy się ze swoją bazą: czym się przedstawia
wobec bazy zdalnej, kiedy wolno mu użyć hasła, i kiedy MUST odmówić pracy zamiast działać
w konfiguracji, która wygląda na działającą.

## ADDED Requirements

### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Wobec bazy zdalnej moduł MUST uwierzytelniać się poświadczeniem wystawianym dla jego
tożsamości i pobieranym przy nawiązywaniu połączenia; trwałe hasło do bazy zdalnej MUST NOT
być wymagane do pracy modułu ani przechowywane w jego konfiguracji. Tryb tożsamości wybiera
skonfigurowana nazwa roli; konfiguracja trybu tożsamości, której adres bazy niesie własne
poświadczenie, MUST być odrzucona przy starcie.

Poświadczenie ma ważność krótszą niż czas pracy modułu i MUST być odnawiane tak, by
połączenie nawiązywane po jego wygaśnięciu zestawiało się poprawnie.

#### Scenario: Poświadczenia nie da się uzyskać

- **WHEN** moduł startuje w trybie tożsamości, a wystawca poświadczeń jest nieosiągalny lub
  odmawia
- **THEN** moduł odmawia startu, wskazując uzyskanie poświadczenia jako przyczynę
- **AND** MUST NOT sięgać po zapasowe hasło

#### Scenario: Poświadczenie w adresie obok tożsamości

- **WHEN** moduł startuje w trybie tożsamości, a adres bazy niesie nazwę użytkownika lub
  hasło
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że poświadczenie z adresu nie byłoby użyte

#### Scenario: Nowe połączenie po wygaśnięciu poświadczenia

- **WHEN** moduł pracuje dłużej niż okres ważności poświadczenia i potrzebuje nowego
  połączenia
- **THEN** połączenie zestawia się na odnowionym poświadczeniu

### Requirement: Połączenie z bazą zdalną jest szyfrowane

Gdy baza stoi poza maszyną modułu, ruch do niej przechodzi przez sieć, której moduł nie
kontroluje — takie połączenie MUST być wyłącznie szyfrowane. Konfiguracja wskazująca hosta
zdalnego, która szyfrowania nie wymusza, MUST być odrzucona przy starcie, a moduł MUST NOT
obniżyć wymagania, gdy połączenie szyfrowane się nie uda. Baza na pętli zwrotnej tej samej
maszyny MAY być osiągana bez szyfrowania.

#### Scenario: Konfiguracja nie wymusza szyfrowania

- **WHEN** moduł startuje w trybie tożsamości z adresem hosta zdalnego, który nie wymaga
  szyfrowania
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje konfigurację połączenia jako przyczynę

#### Scenario: Baza lokalna bez szyfrowania

- **WHEN** moduł startuje bez skonfigurowanej tożsamości, a adres wskazuje pętlę zwrotną bez
  wymogu szyfrowania
- **THEN** moduł startuje i łączy się z bazą

### Requirement: Praca bez tożsamości nie wychodzi poza maszynę

Baza lokalna — w kontenerze na maszynie deweloperskiej — MAY być osiągana hasłem niesionym
w adresie. Ta furtka MUST być ograniczona do pętli zwrotnej: bez skonfigurowanej tożsamości
moduł MUST NOT nawiązać połączenia z hostem innym niż pętla zwrotna i MUST odmówić startu z
taką konfiguracją. Chroni to przed lokalnym modułem piszącym do produkcji i przed
poświadczeniem ambientowym maszyny, które uwierzytelniłoby moduł jako kogoś, kim nie jest.

#### Scenario: Host zdalny bez tożsamości

- **WHEN** moduł startuje bez skonfigurowanej roli, a adres wskazuje hosta spoza pętli
  zwrotnej
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że praca bez tożsamości jest ograniczona do bazy lokalnej

#### Scenario: Narzędzie deweloperskie odmawia wcześniej

- **WHEN** skrypt uruchamiający środowisko lokalne czyta konfigurację wskazującą hosta spoza
  pętli zwrotnej
- **THEN** skrypt odmawia startu przed uruchomieniem czegokolwiek

### Requirement: Moduł nie dzieli bazy z innym modułem

Baza modułu agenta MUST być odrębna od bazy archiwum świec: moduł MUST NOT czytać ani pisać
w tabelach należących do innego modułu, a jego migracje MUST NOT dotykać niczego poza jego
własną bazą. Dwa moduły w jednej bazie logicznej nie dają się osobno wdrożyć, przywrócić z
kopii ani usunąć, a to właśnie te trzy rzeczy czynią moduł niezależnym.

#### Scenario: Migracje modułu

- **WHEN** migracje modułu agenta zostają wykonane
- **THEN** dotyczą wyłącznie jego własnej bazy
- **AND** żadna tabela archiwum świec nie zostaje zmieniona

#### Scenario: Poświadczenie nie sięga dalej

- **WHEN** moduł agenta łączy się w trybie tożsamości
- **THEN** jego rola MUST NOT mieć dostępu do bazy archiwum świec

### Requirement: Poświadczenie nie wycieka do logów

Poświadczenie do bazy jest sekretem o krótkiej ważności, ale sekretem. Moduł MUST NOT
umieszczać go w logach, komunikatach błędów ani w odpowiedziach swoich tras — w
szczególności tam, gdzie loguje adres połączenia.

#### Scenario: Błąd połączenia trafia do logu

- **WHEN** nawiązanie połączenia z bazą kończy się błędem, a moduł loguje jego okoliczności
- **THEN** log zawiera host, port i nazwę bazy
- **AND** nie zawiera poświadczenia ani jego fragmentu
