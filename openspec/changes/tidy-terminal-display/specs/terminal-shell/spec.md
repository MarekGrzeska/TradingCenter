## MODIFIED Requirements

### Requirement: Rejestr zakładek jest otwarty

Zestaw zakładek MUST być deklarowany w jednym miejscu — nazwa, adres i widok — a pasek nawigacji
MUST być z niego wyprowadzany. Dołożenie zakładki MUST NOT wymagać zmian w istniejących zakładkach
ani w samym pasku.

Rejestr MUST zawierać wyłącznie zakładki, które coś pokazują. Zakładka bez widoku MUST NOT mieć
wpisu w rejestrze ani miejsca w pasku: pusta pozycja w nawigacji obiecuje część terminala, która nie
istnieje, i operator płaci za tę obietnicę kliknięciem za każdym razem, gdy o niej zapomni.

#### Scenario: Dołożenie zakładki

- **WHEN** do rejestru dochodzi nowy wpis
- **THEN** zakładka pojawia się w pasku nawigacji i jest osiągalna pod swoim adresem, bez zmian
  w kodzie pozostałych zakładek

#### Scenario: Część terminala jeszcze nie istnieje

- **WHEN** jakaś część terminala jest zaplanowana, ale nie ma widoku
- **THEN** nie ma dla niej wpisu w rejestrze ani pozycji w pasku nawigacji
- **AND** jej adres zachowuje się jak każdy inny nieznany adres

## ADDED Requirements

### Requirement: Interwały nazywają się jednakowo w całym terminalu

Terminal MUST nazywać interwały świec `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `day`, `week` — w polu
wyboru na wykresie, na liście archiwizowanych instrumentów, w kreatorze dodawania, w historii
dociągania i w każdym komunikacie, który interwał wymienia. Nazwy, jakimi interwały jeżdżą po
drucie (`MINUTE_5`, `HOUR_4`), MUST NOT docierać na ekran: ten sam interwał pod dwiema nazwami
w dwóch zakładkach każe operatorowi tłumaczyć jedną na drugą w głowie.

#### Scenario: Wybór interwału na wykresie

- **WHEN** operator otwiera pole wyboru interwału
- **THEN** widzi `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `day`, `week`
- **AND** MUST NOT widzieć nazwy z kontraktu

#### Scenario: Ten sam interwał w dwóch zakładkach

- **WHEN** ten sam interwał jest pokazany na wykresie i na liście archiwizowanych instrumentów
- **THEN** w obu miejscach nazywa się tak samo

### Requirement: Czas jest pokazywany w polskiej strefie czasowej

Każda data i godzina pokazana operatorowi — oś czasu wykresu, czas świecy pod kursorem, daty
w Instruments, w kreatorze dodawania i w historii dociągania — MUST być przeliczona na strefę
`Europe/Warsaw`, niezależnie od strefy przeglądarki, na której terminal jest otwarty. Terminal
odpalony z laptopa w innej strefie MUST pokazywać te same godziny co ten w Polsce.

Pokazany czas MUST nieść widoczną nazwę strefy, żeby nie dało się go pomylić z UTC. Przejście czasu
letniego na zimowy MUST być uwzględnione — przesunięcie MUST NOT być stałą liczbą godzin.

Wewnętrzna postać czasu MUST pozostać niezmieniona: terminal liczy w sekundach od epoki i tak też
rozmawia z archiwum. Strefa jest sprawą wyświetlania, a nie danych.

#### Scenario: Oś czasu wykresu

- **WHEN** operator patrzy na oś czasu wykresu
- **THEN** godziny są godzinami polskimi, a nie UTC

#### Scenario: Terminal otwarty poza Polską

- **WHEN** przeglądarka jest ustawiona na inną strefę niż polska
- **THEN** pokazane daty i godziny są nadal polskie

#### Scenario: Zmiana czasu letniego na zimowy

- **WHEN** pokazywana jest data sprzed zmiany czasu i data po niej
- **THEN** każda jest przeliczona z obowiązującym wtedy przesunięciem

#### Scenario: Data podana przez operatora

- **WHEN** operator wskazuje datę, od której historia ma być dociągnięta
- **THEN** jest ona rozumiana jako początek tego dnia w strefie polskiej
