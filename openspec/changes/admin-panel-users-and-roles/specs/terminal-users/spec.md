## Purpose

Daje operatorowi miejsce w terminalu, z którego zaprasza ludzi do aplikacji po adresie e-mail i decyduje, co
mogą — bez wchodzenia do portalu Entra i bez dawania serwerowi prawa zapisu do katalogu.

## ADDED Requirements

### Requirement: Zakładka Użytkownicy jest tylko dla admina

Terminal MUST pokazywać zakładkę Użytkownicy wyłącznie osobie z rolą `admin`. Wywołania Microsoft Graph MUST iść
tokenem zalogowanego admina, z zakresem proszonym dopiero przy wejściu na zakładkę. Terminal MUST NOT wysyłać
tokenu Graph do żadnego modułu aplikacji, a moduły aplikacji MUST NOT mieć poświadczenia z prawem zapisu do katalogu.

#### Scenario: Admin otwiera zakładkę

- **WHEN** `admin` otwiera Użytkowników po raz pierwszy
- **THEN** terminal prosi o zakres Graph i pokazuje listę osób z rolami

#### Scenario: Brak zgody na zakres Graph

- **WHEN** admin odmawia zakresu albo Graph odmawia z braku uprawnień katalogowych
- **THEN** zakładka mówi, czego brakuje, i nie pokazuje pustej listy jako „nikogo nie ma"

### Requirement: Zaproszenie po adresie e-mail

Admin MUST móc zaprosić osobę, wpisując jej adres e-mail i wybierając rolę. Adres może być dowolny — nie musi być
kontem Microsoft. Zaproszona osoba MUST dostać wiadomość z linkiem prowadzącym do pocket (dla `viewera`) albo do
terminala (dla `admina`), a rola MUST zostać nadana od razu, przy zaproszeniu, nie po jej pierwszym logowaniu.
Terminal MUST odrzucić pusty lub niepoprawny adres przed wywołaniem Graph.

#### Scenario: Zaproszenie viewera

- **WHEN** admin zaprasza `ktos@gmail.com` z rolą `viewer`
- **THEN** powstaje gość tenanta z rolą `viewer` na workbenchu i bez żadnej roli na gatewayu
- **AND** lista pokazuje go jako zaproszonego

#### Scenario: Zaproszenie admina

- **WHEN** admin zaprasza osobę z rolą `admin`
- **THEN** rola `admin` zostaje nadana na workbenchu i na gatewayu

#### Scenario: Zły adres

- **WHEN** admin wpisuje tekst, który nie jest adresem e-mail
- **THEN** terminal odmawia i nie woła Graph

### Requirement: Lista, zmiana roli i odebranie dostępu

Zakładka MUST pokazywać każdą osobę mającą rolę razem z adresem, rolą i tym, czy zaproszenie zostało przyjęte.
Admin MUST móc zmienić rolę osoby i odebrać jej dostęp (usunąć przypisania ról). Terminal MUST NOT pozwolić
usunąć ostatniego admina ani odebrać własnej roli `admin` — taka operacja zostawiłaby aplikację bez nikogo, kto
może ją naprawić. Zmiana ma skutek po odnowieniu tokenu osoby, i zakładka MUST to powiedzieć.

#### Scenario: Awans viewera

- **WHEN** admin zmienia rolę `viewer` na `admin`
- **THEN** osoba dostaje przypisania `admin` na obu rejestracjach, a `viewer` znika

#### Scenario: Odebranie dostępu

- **WHEN** admin odbiera dostęp osobie
- **THEN** jej przypisania ról znikają, a lista przestaje ją pokazywać jako mającą dostęp

#### Scenario: Ostatni admin

- **WHEN** admin próbuje odebrać rolę `admin` sobie albo ostatniemu adminowi
- **THEN** terminal odmawia z wyjaśnieniem
