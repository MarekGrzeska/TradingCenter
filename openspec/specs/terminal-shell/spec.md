## Purpose

Powłoka terminala: co operator widzi po otwarciu aplikacji, jak przechodzi między zakładkami, jak
dokłada się kolejną zakładkę bez ruszania istniejących i skąd wiadomo, że źródło danych przestało
odpowiadać.

## Requirements

### Requirement: Zakładki są adresowalne

Każda zakładka MUST mieć własny adres, a otwarcie adresu wprost MUST pokazać tę zakładkę. Terminal
MUST odtwarzać zakładkę z adresu przy odświeżeniu strony, żeby przeładowanie nie odrzucało operatora
na początek.

#### Scenario: Przejście między zakładkami

- **WHEN** operator wybiera zakładkę z paska nawigacji
- **THEN** terminal pokazuje jej zawartość
- **AND** adres w przeglądarce wskazuje tę zakładkę

#### Scenario: Odświeżenie strony

- **WHEN** operator odświeża stronę stojąc na zakładce innej niż domyślna
- **THEN** po załadowaniu widzi tę samą zakładkę

#### Scenario: Nieznany adres

- **WHEN** operator otwiera adres, któremu nie odpowiada żadna zakładka
- **THEN** terminal pokazuje stronę mówiącą, że takiej zakładki nie ma, wraz z drogą powrotną do
  zakładki domyślnej
- **AND** MUST NOT pokazywać pustego ekranu ani surowego błędu środowiska

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

### Requirement: Motyw jest ciemny i wyprowadzony z tokenów

Terminal MUST używać ciemnego motywu opisanego zestawem nazwanych tokenów — kolory tła, tekstu,
akcentu oraz kolory wzrostu i spadku. Wykresy i reszta interfejsu MUST czerpać kolory z tego samego
zestawu, żeby świeca i etykieta obok niej nie rozjeżdżały się kolorystycznie.

#### Scenario: Zmiana wartości tokenu

- **WHEN** zmieni się wartość tokenu koloru
- **THEN** zmiana obejmuje zarówno interfejs, jak i wykresy, bez edycji każdego z osobna

### Requirement: Stan źródła danych jest widoczny globalnie

Terminal MUST pokazywać w stałym miejscu, z jakiego źródła danych korzysta i czy to źródło
odpowiada. Cisza na strumieniu MUST być odróżnialna od rynku, który stoi.

#### Scenario: Źródło odpowiada

- **WHEN** źródło danych jest osiągalne
- **THEN** wskaźnik nazywa źródło i stwierdza, że połączenie działa

#### Scenario: Źródło nie odpowiada

- **WHEN** żądania do źródła danych zawodzą albo strumień się zrywa
- **THEN** wskaźnik mówi, że źródło nie odpowiada
- **AND** terminal MUST NOT wyglądać na działający normalnie — dane na ekranie są opisane jako
  nieaktualne

#### Scenario: Awaria pojedynczego widoku

- **WHEN** jeden widok wywraca się na błędzie
- **THEN** terminal pokazuje w jego miejscu komunikat błędu z możliwością ponowienia
- **AND** pozostałe zakładki i widoki działają dalej
