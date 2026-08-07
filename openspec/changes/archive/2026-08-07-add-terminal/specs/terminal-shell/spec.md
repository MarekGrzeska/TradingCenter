## Purpose

Powłoka terminala: co operator widzi po otwarciu aplikacji, jak przechodzi między zakładkami, jak
dokłada się kolejną zakładkę bez ruszania istniejących i skąd wiadomo, że źródło danych przestało
odpowiadać.

## ADDED Requirements

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

#### Scenario: Dołożenie zakładki

- **WHEN** do rejestru dochodzi nowy wpis
- **THEN** zakładka pojawia się w pasku nawigacji i jest osiągalna pod swoim adresem, bez zmian
  w kodzie pozostałych zakładek

#### Scenario: Zakładka jeszcze niezaimplementowana

- **WHEN** rejestr zawiera zakładkę oznaczoną jako przygotowaną na przyszłość
- **THEN** jej otwarcie pokazuje jawną informację, że ta część terminala jeszcze nie działa
- **AND** nawigacja do pozostałych zakładek działa dalej

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
