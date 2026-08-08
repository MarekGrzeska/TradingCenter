## Purpose

Publikowany kontrakt archiwum: jak konsument czyta świece, jak subskrybuje bieżące, skąd wie, czego
w archiwum brakuje, i jak zarządza tym, co jest zbierane.

## Requirements

### Requirement: Odczyt świec po zakresie czasu

Moduł MUST udostępniać świece śledzonej pary dla wskazanego przedziału czasu, uporządkowane od
najstarszej, bez powtórzonych znaczników. Odpowiedź MUST nieść rozdzielczość i stronę ceny, żeby
seria była samoopisująca się.

#### Scenario: Odczyt zakresu

- **WHEN** konsument prosi o świece pary w przedziale czasu
- **THEN** dostaje serię uporządkowaną od najstarszej, bez powtórzonych znaczników czasu
- **AND** odpowiedź niesie rozdzielczość i stronę ceny

#### Scenario: Przedział wychodzi poza pokrycie

- **WHEN** żądany przedział wykracza poza to, co archiwum zebrało
- **THEN** odpowiedź zawiera świece z części pokrytej
- **AND** stwierdza, która część przedziału nie jest pokryta

### Requirement: Subskrypcja zaczyna się od snapshotu

Konsument, który najpierw odczytuje historię, a potem subskrybuje, ma między tymi krokami okno, w
którym świeca może mu uciec. Moduł MUST rozpoczynać subskrypcję wiadomością niosącą ostatnie świece
zamknięte oraz świecę w budowie, jeśli taka jest, i dopiero po niej wysyłać zmiany.

#### Scenario: Konsument subskrybuje

- **WHEN** konsument otwiera subskrypcję pary
- **THEN** pierwsza wiadomość niesie ostatnie świece zamknięte oraz świecę w budowie, jeśli istnieje
- **AND** kolejne wiadomości niosą wyłącznie zmiany

#### Scenario: Świeca zamyka się w trakcie subskrypcji

- **WHEN** okres, który był w budowie, zostaje zamknięty
- **THEN** konsument dostaje tę świecę oznaczoną jako zamkniętą
- **AND** znacznik czasu jest ten sam co w świecy w budowie, żeby podmiana nie utworzyła drugiej
  świecy

#### Scenario: Subskrypcja nieśledzonej pary

- **WHEN** konsument subskrybuje parę, która nie jest śledzona
- **THEN** moduł odmawia i stwierdza, że para nie jest śledzona

### Requirement: Świeca w budowie jest oznaczona

Świeca w budowie zmienia się przy każdym kwotowaniu i nie jest utrwalana. Każda wiadomość niosąca
świecę MUST stwierdzać, czy jest ona zamknięta, czy w budowie, żeby konsument mógł je odróżnić.

#### Scenario: Odbiorca rozróżnia świece

- **WHEN** konsument odbiera świecę z subskrypcji
- **THEN** wiadomość stwierdza, czy świeca jest zamknięta, czy w budowie

### Requirement: Pokrycie jest odczytywalne

Konsument MUST móc dowiedzieć się, jaki przedział czasu archiwum pokrywa dla danej pary, zanim
zbuduje na tych danych wykres albo backtest.

#### Scenario: Odczyt pokrycia

- **WHEN** konsument pyta o pokrycie pary
- **THEN** dostaje najstarszy i najnowszy zweryfikowany znacznik czasu
- **AND** informację, czy najstarsza granica wynika z końca historii u providera

### Requirement: Śledzone pary są zarządzalne przez kontrakt

Moduł MUST udostępniać przez swój kontrakt dodanie pary do śledzonych, usunięcie jej oraz odczyt
listy wraz ze stanem każdej pary. Konfiguracja MUST NOT wymagać dostępu do plików ani restartu.

#### Scenario: Dodanie pary

- **WHEN** konsument dodaje parę przez kontrakt
- **THEN** para zostaje zapisana jako śledzona, a odpowiedź to potwierdza

#### Scenario: Dodanie pary nieznanej providerowi

- **WHEN** konsument dodaje parę, której symbolu provider nie zna
- **THEN** moduł odmawia i nazywa symbol jako nieznaleziony

#### Scenario: Usunięcie pary

- **WHEN** konsument usuwa parę ze śledzonych
- **THEN** zbieranie ustaje, a zebrane świece pozostają odczytywalne

### Requirement: Odpowiedzi nazywają swoje porażki

Każda porażka MUST być opisana w sposób, który da się pokazać operatorowi: nieznany symbol,
nieobsługiwana rozdzielczość, para nieśledzona, źródło nieosiągalne. Odpowiedź MUST NOT być surowym
błędem bazy ani sieci i MUST NOT nieść poświadczeń żadnego systemu.

#### Scenario: Baza nieosiągalna

- **WHEN** archiwum nie może sięgnąć do własnej bazy
- **THEN** konsument dostaje błąd mówiący, że archiwum jest niedostępne, a nie pustą serię świec

#### Scenario: Nieobsługiwana rozdzielczość

- **WHEN** konsument prosi o rozdzielczość spoza obsługiwanych
- **THEN** moduł odmawia i wylicza rozdzielczości, które obsługuje
