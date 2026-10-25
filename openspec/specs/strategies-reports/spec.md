# strategies-reports Specification

## Purpose
Co raport z uruchomienia mówi o strategii i z czego powstał, a czego celowo nie mówi: system liczy i pokazuje,
decyzję o strategii podejmuje operator.
## Requirements
### Requirement: Raport nie wydaje werdyktu

Raport MUST NOT zawierać pola, etykiety ani stanu, który ocenia strategię jako przechodzącą albo nieprzechodzącą,
i MUST NOT porównywać metryk z progami.

#### Scenario: Strategia z ujemnym wynikiem

- **WHEN** uruchomienie kończy się wynikiem −30 R
- **THEN** raport MUST podawać liczby tak samo jak przy wyniku dodatnim, bez oceny

### Requirement: Metryki raportu

Raport MUST podawać: liczbę transakcji, odsetek zyskownych, wartość oczekiwaną i sumę w R, profit factor,
maksymalne obsunięcie w R i w procentach kapitału nominalnego, Sharpe'a i Sortino z dziennych zwrotów kapitału
(z nazwaną metodą rocznej skali), Calmar, najdłuższą serię strat, średni czas w pozycji w świecach decyzji,
ekspozycję, wynik bez pięciu najlepszych transakcji, podział wyników na lata kalendarzowe, koszty rozbite na
składniki oraz liczbę rozstrzygnięć pesymistycznych. Metryka, której nie da się policzyć, MUST mieć wartość
pustą, a nie zero.

#### Scenario: Brak transakcji

- **WHEN** strategia nie otworzyła w zakresie żadnej pozycji
- **THEN** raport MUST mówić, że transakcji nie było, a metryki zależne od transakcji MUST być puste

#### Scenario: Brak strat

- **WHEN** każda transakcja była zyskowna
- **THEN** profit factor MUST być pusty

### Requirement: Każda transakcja jest widoczna

Raport MUST udostępniać listę transakcji, a każda MUST nieść: stronę, czas i cenę wejścia i wyjścia, wielkość,
początkowy stop, wynik w R i w pieniądzu, koszty rozbite na składniki, przyczynę wyjścia (`stop`, `target`,
`trail`, `when`, `max_bars`, „koniec zakresu”) i oznaczenie rozstrzygnięcia pesymistycznego.

#### Scenario: Transakcja zamknięta trailingiem

- **WHEN** pozycja zamyka się na przesuniętym stopie
- **THEN** jej przyczyną wyjścia MUST być `trail`, nie `stop`

### Requirement: Dwa punkty odniesienia

Raport MUST zawierać wynik „kup i trzymaj” instrumentu na tym samym zakresie i z tymi samymi kosztami oraz
wynik losowego wejścia: tyle samo wejść w losowych świecach decyzji, z tymi samymi wyjściami, rozmiarem i
kosztami, powtórzony ustaloną liczbę razy, podany jako mediana oraz 5. i 95. percentyl sumy R. Losowanie MUST
być powtarzalne z ziarna zapisanego w raporcie.

#### Scenario: Powtórzenie z tym samym ziarnem

- **WHEN** to samo uruchomienie powtarza się z tym samym ziarnem
- **THEN** wynik losowego wejścia MUST być identyczny

### Requirement: Raport mówi, z czego powstał

Raport MUST zapisywać: identyfikator strategii, rewizję i hash jej treści, użyte parametry, model kosztów,
zakres, przeczytaną rozgrzewkę, wersję silnika, ziarno oraz dla każdej przeczytanej serii odcisk danych (liczbę
punktów, pierwszą i ostatnią chwilę, hash wartości) i fragmenty zakresu, których archiwum nie potwierdziło.

#### Scenario: Dane zmieniły się między uruchomieniami

- **WHEN** dwa uruchomienia tej samej rewizji z tym samym wkładem dają różne wyniki
- **THEN** odciski danych w obu raportach MUST pokazywać, która seria się różni

### Requirement: Uruchomienia są trwałe i policzone

Każde uruchomienie, także nieudane i anulowane, MUST pozostać zapisane razem z wkładem. Dla każdej strategii
MUST być widoczna liczba zakończonych uruchomień, ze wszystkich jej rewizji, jako licznik prób.

#### Scenario: Kolejne uruchomienie

- **WHEN** strategia z trzema zakończonymi uruchomieniami kończy czwarte
- **THEN** jej licznik prób MUST wynosić cztery

