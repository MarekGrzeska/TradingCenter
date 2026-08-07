## Purpose

Trzyma świece, które przeleciały strumieniem albo zostały dociągnięte z historii, i wie o sobie
tyle, żeby odróżnić okres, w którym rynek był zamknięty, od okresu, którego po prostu nie zebrał.

## ADDED Requirements

### Requirement: Świecę identyfikuje symbol, rozdzielczość i początek okresu

Archiwum MUST identyfikować świecę trójką: symbol, rozdzielczość, znacznik czasu początku okresu.
Dla jednej trójki MUST istnieć najwyżej jedna świeca. Powtórny zapis tej samej trójki MUST
nadpisać wpis, a nie dołożyć drugi.

#### Scenario: Ta sama świeca przychodzi dwa razy

- **WHEN** ingest zapisuje świecę o symbolu, rozdzielczości i początku okresu już obecnych
  w archiwum
- **THEN** archiwum trzyma nadal dokładnie jedną świecę tego okresu
- **AND** odczyt zakresu nie zwraca powtórzonego znacznika czasu

#### Scenario: Odczyt zachowuje porządek

- **WHEN** konsument odczytuje zakres świec
- **THEN** dostaje je uporządkowane od najstarszej

### Requirement: Zapisywana jest wyłącznie świeca zamknięta

Świeca w budowie zmienia się przy każdym kwotowaniu i po restarcie źródła zaniża swój zakres.
Archiwum MUST NOT utrwalać świecy oznaczonej jako w budowie. Trafia do niego wyłącznie świeca
zamknięta.

#### Scenario: Strumień niesie świecę w budowie

- **WHEN** ze strumienia przychodzi świeca oznaczona jako w budowie
- **THEN** archiwum nie zapisuje jej
- **AND** świeca pozostaje dostępna konsumentom jako wartość ulotna, nieutrwalona

#### Scenario: Okres się zamyka

- **WHEN** dla okresu, który był w budowie, przychodzi świeca zamknięta
- **THEN** archiwum zapisuje wartości ze świecy zamkniętej

### Requirement: Wartość od providera jest autorytatywna

Ta sama świeca może dotrzeć dwiema drogami — ze strumienia oraz z uzupełniania wstecz. Gdy wartości
się różnią, archiwum MUST zachować tę pochodzącą z odczytu historii providera, bo strumień mógł
przegapić kwotowania w czasie przerwy w połączeniu.

#### Scenario: Uzupełnianie wstecz trafia na świecę ze strumienia

- **WHEN** uzupełnianie wstecz przynosi świecę okresu zapisanego wcześniej ze strumienia
- **THEN** archiwum zastępuje wartości tymi z odczytu historii

#### Scenario: Strumień trafia na świecę z uzupełniania

- **WHEN** ze strumienia przychodzi zamknięta świeca okresu pochodzącego z odczytu historii
- **THEN** archiwum zachowuje wartości już zapisane

### Requirement: Jedna strona ceny w całym archiwum

Świece MUST być przechowywane po tej samej stronie ceny, której używa `capital-gateway`, czyli po
stronie bid. Strona ceny MUST być zapisana wprost przy danych, a nie dorozumiana, żeby dołożenie
kiedyś drugiej strony nie zmieszało obu w jednej serii.

#### Scenario: Odczyt nazywa stronę ceny

- **WHEN** konsument odczytuje świece
- **THEN** odpowiedź stwierdza, po której stronie ceny są zbudowane

### Requirement: Archiwum wie, co pokrywa

Brak świecy o 3:00 w sobotę i brak świecy, bo ingest nie działał, wyglądają w danych identycznie.
Archiwum MUST przechowywać dla każdej śledzonej pary zakresy czasu, dla których dane zostały
zweryfikowane, żeby te dwa przypadki dało się rozróżnić.

#### Scenario: Brak świecy wewnątrz pokrycia

- **WHEN** w zweryfikowanym zakresie nie ma świecy dla danego okresu
- **THEN** archiwum stwierdza, że rynek był wtedy zamknięty, a nie że brakuje danych

#### Scenario: Brak świecy poza pokryciem

- **WHEN** żądany okres wypada poza jakimkolwiek zweryfikowanym zakresem
- **THEN** archiwum stwierdza, że tego okresu nie zebrało

#### Scenario: Historia instrumentu się skończyła

- **WHEN** uzupełnianie wstecz dochodzi do miejsca, w którym provider nie ma starszych danych
- **THEN** ten punkt zostaje zapisany jako najstarsza możliwa granica pokrycia
- **AND** kolejne uzupełnianie nie sięga już przed tę granicę

### Requirement: Rozdzielczości pochodne są wyliczane, nie pobierane

Provider oddaje najwyżej tysiąc świec na żądanie i jest ograniczony do dziesięciu żądań na sekundę,
więc pobieranie ośmiu rozdzielczości osobno kosztuje ośmiokrotność ruchu. Archiwum MUST wyliczać
rozdzielczości o stałej długości okresu z serii minutowej. `DAY` i `WEEK` MUST pochodzić
z providera, bo ich granica zależy od sesji rynku, a nie od zegara.

#### Scenario: Odczyt rozdzielczości pochodnej

- **WHEN** konsument prosi o świece w rozdzielczości wyliczalnej z serii minutowej
- **THEN** dostaje serię zbudowaną z otwarcia pierwszej świecy okresu, maksimum i minimum
  wszystkich oraz zamknięcia ostatniej

#### Scenario: Rozdzielczość dzienna albo tygodniowa

- **WHEN** konsument prosi o świece dzienne albo tygodniowe
- **THEN** archiwum oddaje wartości pochodzące z providera, a nie wyliczone z serii minutowej

#### Scenario: Okres niepełny

- **WHEN** dla okresu rozdzielczości pochodnej archiwum ma tylko część świec minutowych
- **THEN** wyliczona świeca stwierdza, że powstała z niepełnego okresu
