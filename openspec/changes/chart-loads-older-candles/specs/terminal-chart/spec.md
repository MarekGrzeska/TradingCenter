## ADDED Requirements

### Requirement: Wykres dociąga starszą historię przy przewijaniu w lewo

Wykres MUST dociągać starsze świece z archiwum, gdy operator przewija poza najstarszą narysowaną świecę,
i MUST doklejać je na początek serii bez przesuwania tego, co operator ma przed oczami. Dociągane MUST być
wyłącznie okresy starsze niż najstarsza narysowana świeca — prawą krawędź serii nadal wyznacza snapshot
subskrypcji, więc dociąganie MUST NOT dotykać okresu w budowie ani odtwarzać szwu między historią a
strumieniem. Dwa odczyty naraz dla tego samego wykresu MUST NOT być zlecane.

#### Scenario: Przewinięcie poza najstarszą świecę

- **WHEN** operator przewija wykres w lewo, aż dochodzi do początku narysowanej serii
- **THEN** wykres prosi archiwum o zakres kończący się na najstarszej narysowanej świecy
- **AND** dokleja otrzymane świece na początek serii

#### Scenario: Kadr nie ucieka spod kursora

- **WHEN** starsze świece zostają doklejone na początek serii
- **THEN** widoczny fragment wykresu pokazuje te same świece co przed doklejeniem

#### Scenario: Przewijanie w trakcie odczytu

- **WHEN** operator przewija dalej, zanim wróci poprzedni odczyt
- **THEN** wykres nie zleca drugiego odczytu tego samego zakresu

#### Scenario: Zmiana symbolu albo rozdzielczości w trakcie dociągania

- **WHEN** wykres dostaje inny symbol albo inną rozdzielczość, zanim wróci odczyt starszej historii
- **THEN** spóźniona odpowiedź MUST NOT trafić do serii, która jest teraz na ekranie

### Requirement: Wykres mówi, co się dzieje ze starszą historią

Dociąganie MUST być widoczne na ekranie, a jego koniec MUST być odróżnialny od trwającego odczytu:
wykres MUST stwierdzić, że starszej historii już nie ma, i MUST stwierdzić, gdy odczyt się nie powiódł,
zamiast zostawiać operatora przy pustym marginesie bez wyjaśnienia. Nieudany odczyt MUST NOT usuwać
świec już narysowanych.

#### Scenario: Trwa dociąganie

- **WHEN** odczyt starszych świec jest w toku
- **THEN** wykres pokazuje, że dociąga historię

#### Scenario: Archiwum nie ma nic starszego

- **WHEN** archiwum odpowiada, że dla okresów starszych nie ma już świec
- **THEN** wykres stwierdza, że to początek dostępnej historii
- **AND** dalsze przewijanie w lewo MUST NOT ponawiać odczytu

#### Scenario: Odczyt starszej historii się nie powiódł

- **WHEN** odczyt starszych świec kończy się błędem
- **THEN** wykres mówi, że nie udało się dociągnąć historii, wraz z możliwością ponowienia
- **AND** świece już narysowane zostają na ekranie
