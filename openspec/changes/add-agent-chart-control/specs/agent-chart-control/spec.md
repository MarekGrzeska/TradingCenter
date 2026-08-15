## Purpose

Narzędzie, którym agent ustawia to, co terminal rysuje, i trwały ślad tego ustawienia:
kształt polecenia, jego numerację, sposób odczytu przez terminal oraz to, czego narzędzie
odmawia i jak tę odmowę uzasadnia.

## ADDED Requirements

### Requirement: Narzędzie ustawia zawartość aktywnego slotu

Moduł MUST publikować modelowi narzędzie, które ustawia zawartość aktywnego slotu
terminala: zestaw wskaźników wraz z parametrami i kolorami, symbol oraz interwał.

Polecenie MUST być **deklaratywne**: niesie stan, który ma być widoczny, a nie różnicę
wobec stanu poprzedniego. Pole pominięte MUST znaczyć „zostaw jak jest", nigdy „wyczyść" —
model proszony o dołożenie średniej nie ma jak wyzerować symbolu przez przeoczenie.

Wskaźnik w poleceniu MUST być identyfikowany tak, jak nazywa go katalog archiwum, a jego
parametry MUST mieścić się w granicach, które katalog podaje. Kolor MUST pochodzić
z palety terminala albo być pominięty.

#### Scenario: Model pokazuje średnią

- **WHEN** model woła narzędzie z jednym wskaźnikiem i jego okresem
- **THEN** aktywny slot rysuje ten wskaźnik z tym okresem

#### Scenario: Model zmienia sam interwał

- **WHEN** model woła narzędzie podając wyłącznie interwał
- **THEN** interwał slotu się zmienia, a jego wskaźniki i symbol zostają

#### Scenario: Model podaje pełny zestaw wskaźników

- **WHEN** model woła narzędzie z trzema wskaźnikami, a slot rysował dwa inne
- **THEN** slot rysuje te trzy, bo polecenie niesie stan, a nie różnicę

### Requirement: Ustawienie jest zapisane i ponumerowane

Każde wykonane polecenie MUST zostać zapisane w bazie modułu z rosnącym numerem
kolejnym, znacznikiem czasu i sesją rozmowy, w której padło.

Numer MUST rosnąć w obrębie całego modułu, nie w obrębie sesji: terminal ma jeden wykres i
czyta jeden ciąg poleceń, choćby rozmów było kilka.

Zapis MUST przeżyć restart modułu i odświeżenie przeglądarki — polecenie sprzed godziny
MUST dać się odczytać tak samo jak sprzed sekundy.

#### Scenario: Polecenie przeżywa odświeżenie strony

- **WHEN** operator odświeża terminal po tym, jak agent ustawił wykres
- **THEN** ostatnie polecenie jest nadal czytelne i wykres nadal je pokazuje

#### Scenario: Dwie rozmowy, jeden ciąg

- **WHEN** agent ustawia wykres w jednej rozmowie, a potem w drugiej
- **THEN** drugie polecenie ma wyższy numer niż pierwsze

### Requirement: Konsument czyta tylko to, czego jeszcze nie zastosował

Moduł MUST publikować ostatnie polecenie wraz z jego numerem, a konsument MUST móc
zapytać o polecenia nowsze niż numer, który już zastosował.

Odczyt MUST być bezpieczny do powtórzenia: dwa odczyty bez nowego polecenia MUST dać ten
sam wynik i MUST NOT zmienić niczego po stronie modułu.

Moduł MUST NOT wymagać od konsumenta, żeby ogłaszał, co zastosował — numer ostatnio
zastosowanego polecenia należy do konsumenta, nie do modułu. Terminal nic nie publikuje
i to wymaganie tego nie zmienia.

#### Scenario: Nic nowego od ostatniego odczytu

- **WHEN** konsument pyta o polecenia nowsze niż numer, który już ma
- **THEN** dostaje pustą odpowiedź, a nie ostatnie polecenie po raz drugi

#### Scenario: Konsument wraca po przerwie

- **WHEN** konsument, który był wyłączony, pyta o polecenia nowsze niż jego numer
- **THEN** dostaje ostatnie polecenie, bez konieczności odtwarzania wszystkich pominiętych

### Requirement: Odmowa narzędzia nazywa, co poprawić

Narzędzie MUST odmówić polecenia, którego terminal nie mógłby wykonać: nieznanego
wskaźnika, parametru poza granicami katalogu, symbolu albo interwału, w którym archiwum
nie zbiera danych, oraz koloru spoza palety.

Odmowa MUST wracać do modelu jako wynik wywołania wraz ze zdaniem mówiącym, co zmienić —
tak samo jak odmowa serwera narzędzi (`agent-tools`, „Odmowa narzędzia jest wynikiem, nie
awarią tury"). Odmowa MUST NOT zapisać polecenia ani zmienić czegokolwiek na wykresie.

#### Scenario: Symbol, którego archiwum nie zbiera

- **WHEN** model woła narzędzie z symbolem spoza zbieranych par
- **THEN** dostaje odmowę mówiącą, które symbole są zbierane
- **AND** wykres zostaje bez zmian

#### Scenario: Parametr poza granicami katalogu

- **WHEN** model woła narzędzie z okresem spoza zakresu, który podaje katalog
- **THEN** dostaje odmowę nazywającą ten zakres i może zawołać ponownie

#### Scenario: Odmowa nie zostawia śladu na wykresie

- **WHEN** narzędzie odmawia polecenia niosącego trzy wskaźniki, z których jeden jest nieznany
- **THEN** nie zostaje zastosowany żaden z nich, a numer ostatniego polecenia się nie zmienia
