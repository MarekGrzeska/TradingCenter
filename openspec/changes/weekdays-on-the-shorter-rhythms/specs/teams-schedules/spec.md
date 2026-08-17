## MODIFIED Requirements

### Requirement: Harmonogram da się opisać rytmem, a moduł zna oba zapisy

Moduł MUST przyjmować opis harmonogramu podany jako rytm — odstęp w minutach, godzina doby,
dni tygodnia albo dzień miesiąca — i MUST sam zamienić go na wyrażenie czasowe, które
wykonuje. Moduł MUST publikować ten rytm przy harmonogramie, obok wyrażenia czasowego.
Harmonogram, którego wyrażenia nie da się wyrazić żadnym z rytmów, MUST zostać opublikowany
z rytmem pustym i MUST nadal dać się odczytać oraz wyzwalać.

Rytm powtarzający się częściej niż raz na dobę MUST móc nieść dni tygodnia. Rynek stoi dwa
dni w tygodniu, a rytm bez tych dni każe pytać o niego także wtedy — kosztem przebiegu,
który nie ma o co zapytać. Dni tygodnia przy takim rytmie MUST być opcjonalne, a ich brak
MUST znaczyć każdy dzień.

Komplet siedmiu dni MUST być zapisany tak samo jak brak dni. Jedno wyzwolenie opisane na
dwa sposoby zabiera odczytowi jednoznaczność: moduł, który zapisze oba, przy odczycie
odpowie jednym z nich i operator zobaczy rytm, którego nie ułożył.

Rytm dobowy MUST NOT nieść dni tygodnia. Dobowy z dniami tygodnia znaczy dokładnie to, co
rytm tygodniowy, i te same dwa zapisy jednego wyzwolenia MUST NOT powstać.

Zamiana rytmu na wyrażenie czasowe istnieje raz — w module. Odbiorca kontraktu, który
musiałby ją powtórzyć u siebie, żeby pokazać operatorowi jego własny harmonogram, prędzej
czy później pokaże co innego, niż moduł wykona.

#### Scenario: Harmonogram zapisany rytmem

- **WHEN** operator zapisuje harmonogram jako „codziennie o 9:00"
- **THEN** moduł zapisuje harmonogram wyzwalający się o 9:00 czasu polskiego
- **AND** odczyt tego harmonogramu zwraca ten sam rytm

#### Scenario: Rytm godzinowy ograniczony do dni handlowych

- **WHEN** operator zapisuje harmonogram jako „co godzinę o :35, od poniedziałku do piątku"
- **THEN** moduł zapisuje harmonogram, który w sobotę i w niedzielę się nie wyzwala
- **AND** odczyt tego harmonogramu zwraca ten sam rytm wraz z tymi dniami

#### Scenario: Rytm krótszy niż godzina bez dni tygodnia

- **WHEN** operator zapisuje rytm „co 15 minut" bez wskazania dni
- **THEN** harmonogram wyzwala się każdego dnia tygodnia
- **AND** odczyt zwraca rytm bez dni tygodnia, a nie z kompletem siedmiu

#### Scenario: Wszystkie dni tygodnia wskazane

- **WHEN** operator zapisuje rytm godzinowy, wskazując wszystkie siedem dni
- **THEN** zapisany harmonogram jest tym samym, co harmonogram zapisany bez wskazania dni
- **AND** odczyt zwraca rytm bez dni tygodnia

#### Scenario: Dni tygodnia przy rytmie dobowym

- **WHEN** opis harmonogramu niesie rytm dobowy razem z dniami tygodnia
- **THEN** moduł odmawia zapisu, nazywając rytm tygodniowy jako miejsce na te dni

#### Scenario: Wyrażenie spoza rytmów kreatora

- **WHEN** harmonogram niesie wyrażenie czasowe, którego nie da się opisać żadnym z rytmów
- **THEN** odczyt zwraca ten harmonogram z pustym rytmem i z jego wyrażeniem
- **AND** harmonogram wyzwala się dalej
