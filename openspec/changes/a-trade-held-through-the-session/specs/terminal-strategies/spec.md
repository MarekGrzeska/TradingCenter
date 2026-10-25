## MODIFIED Requirements

### Requirement: Raport z krzywą kapitału i transakcjami na wykresie

Raport MUST pokazywać:
- wszystkie metryki z `strategies-reports`, a metrykę pustą jako brak wartości, nigdy jako zero;
- punkty odniesienia;
- koszty według składników;
- liczbę rozstrzygnięć pesymistycznych;
- pochodzenie wyniku: rewizję i hash, wersję silnika, ziarno, zakres, koszty i wymagany depozyt, gdy był użyty;
- dzienną krzywą kapitału z obsunięciem.

Transakcje MUST być listą stronicowaną z przyczyną wyjścia, wynikiem w procentach i oznaczeniem rozstrzygnięcia
pesymistycznego. Obok MUST stać wykres ceny instrumentu na interwale strategii ze znacznikami wejść i wyjść transakcji
z bieżącej strony. Wybór transakcji MUST przesuwać wykres do niej i rysować jej wejście, wyjście i początkowy stop, gdy
transakcja go ma. Zakładka MUST NOT pokazywać oceny strategii.

#### Scenario: Wybór transakcji

- **WHEN** operator wybiera transakcję z listy
- **THEN** wykres MUST pokazać fragment osi z tą transakcją i jej wejście, wyjście oraz początkowy stop

#### Scenario: Raport bez transakcji

- **WHEN** uruchomienie nie otworzyło żadnej pozycji
- **THEN** raport MUST mówić, że transakcji nie było, a metryki zależne od transakcji MUST być pokazane jako brak wartości

#### Scenario: Uruchomienie sprzed krzywej kapitału

- **WHEN** raport pochodzi z wersji silnika, która nie zapisywała krzywej
- **THEN** zakładka MUST mówić, że to uruchomienie nie ma krzywej, zamiast rysować pusty wykres

#### Scenario: Transakcja bez stopu

- **WHEN** operator wybiera transakcję strategii bez stopu
- **THEN** wykres MUST pokazać jej wejście i wyjście bez linii stopu
- **AND** jej wynik w R MUST być pokazany jako brak wartości, a wynik w procentach jako liczba
