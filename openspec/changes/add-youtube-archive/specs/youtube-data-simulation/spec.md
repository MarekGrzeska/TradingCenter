## Purpose

Symulowani dostawcy archiwum YouTube: pozwalają ćwiczyć lokalnie i w testach całą drogę filmu —
z zachowaniami prawdziwych dostawców, także tymi złymi — bez sieci i bez kosztu, i nigdy nie
udają danych prawdziwych.

## ADDED Requirements

### Requirement: Symulacja odtwarza zachowania prawdziwych dostawców

Moduł MUST mieć symulowane źródło filmów, symulowanego dostawcę transkrypcji i symulowany model,
wybierane tym samym ustawieniem co prawdziwe. Ich zachowanie MUST wynikać ze scenariusza, który
MUST umieć opisać co najmniej: filmy pojawiające się w czasie od startu, napisy dostępne od razu,
po zadanym czasie albo nigdy, blokadę dostawcy (stałą albo z zadanym odsetkiem), odpowiedź
odroczoną jako zadanie do odpytania, opóźnienie odpowiedzi, koszt każdego wywołania w jednostce
dostawcy (w tym płatny brak napisów), wyczerpanie dziennego limitu, wyszukiwanie po frazie oraz
model zwracający odpowiedź niezgodną ze schematem.

#### Scenario: Napisy po dwóch godzinach

- **WHEN** scenariusz mówi, że napisy filmu pojawiają się dwie godziny po publikacji
- **THEN** próby przed tym momentem MUST kończyć się brakiem napisów, a pierwsza po nim — tekstem

#### Scenario: Blokada w co dziesiątym zapytaniu

- **WHEN** scenariusz ustawia blokadę z odsetkiem 10%
- **THEN** dostawca MUST odpowiadać blokadą w przybliżeniu co dziesiątym zapytaniem, powtarzalnie
  dla tego samego ziarna losowania

#### Scenario: Wyszukiwanie tematu

- **WHEN** temat wyszukuje frazę, a scenariusz ma pasujące filmy
- **THEN** źródło MUST je zwrócić i MUST policzyć koszt wyszukiwania w jednostkach źródła

### Requirement: Czas symulacji jest sterowalny

Symulacja MUST dać się przyspieszyć ustawieniem, a testy MUST móc podać własny zegar. Ten sam
scenariusz, ziarno i zegar MUST dawać ten sam przebieg.

#### Scenario: Doba w kwadrans

- **WHEN** przyspieszenie jest ustawione tak, że doba scenariusza mija w kwadrans
- **THEN** filmy, napisy i odnowienie dziennych limitów MUST pojawiać się w tym tempie

### Requirement: Dane symulowane są oznaczone wszędzie

Każdy film, transkrypcja i odczyt pochodzący z symulacji MUST nieść oznaczenie symulacji w
kontrakcie REST, w odpowiedziach narzędzi i na ekranie. Alert o filmie symulowanym MUST być
wyraźnie oznaczony w treści wiadomości.

#### Scenario: Agent czyta symulowany film

- **WHEN** narzędzie zwraca odczyt filmu z symulacji
- **THEN** odpowiedź MUST mówić, że dane są symulowane

### Requirement: Symulacja nie rusza w trybie produkcyjnym

Moduł MUST odmówić startu, gdy którykolwiek wybrany dostawca jest symulowany, a proces działa w
trybie produkcyjnym (z tożsamością bazy danych zamiast lokalnego trybu). Komunikat MUST nazywać
ustawienie.

#### Scenario: Symulacja w ustawieniach produkcji

- **WHEN** proces startuje w trybie produkcyjnym z symulowanym dostawcą w ustawieniach
- **THEN** MUST odmówić startu, nazywając ustawienie dostawcy

### Requirement: Treści symulacji są syntetyczne

Transkrypcje w scenariuszach dołączonych do repozytorium MUST być napisane na potrzeby symulacji
i MUST NOT być kopiami cudzych filmów. Scenariusz MUST zawierać co najmniej jedną transkrypcję
polską, jedną angielską, jedną pustą i jedną z próbą wstrzyknięcia polecenia.

#### Scenario: Przegląd scenariusza domyślnego

- **WHEN** ktoś otwiera scenariusz domyślny
- **THEN** MUST znaleźć w nim wymienione rodzaje transkrypcji i żadnej skopiowanej z YouTube
