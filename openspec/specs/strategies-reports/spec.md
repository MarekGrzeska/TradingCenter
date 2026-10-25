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

Raport MUST podawać: liczbę transakcji, odsetek zyskownych, wartość oczekiwaną w R i w procentach kapitału, sumę
w R, profit factor, maksymalne obsunięcie w R i w procentach kapitału nominalnego, Sharpe'a i Sortino z dziennych
zwrotów kapitału (z nazwaną metodą rocznej skali), Calmar, najdłuższą serię strat, średni czas w pozycji w świecach
decyzji, ekspozycję, wynik bez pięciu najlepszych transakcji, podział wyników na lata kalendarzowe (w R i w
procentach), koszty rozbite na składniki, liczbę rozstrzygnięć pesymistycznych oraz największą stratę otwartą
spośród transakcji w procentach kapitału. Zyskowność, profit factor i serie strat MUST być liczone z wyniku w
pieniądzu, żeby istniały także bez stopu. Metryka, której nie da się policzyć, MUST mieć wartość pustą, a nie zero.
W uruchomieniu strategii bez stopu każda metryka w R MUST być pusta.

#### Scenario: Brak transakcji

- **WHEN** strategia nie otworzyła w zakresie żadnej pozycji
- **THEN** raport MUST mówić, że transakcji nie było, a metryki zależne od transakcji MUST być puste

#### Scenario: Brak strat

- **WHEN** każda transakcja była zyskowna
- **THEN** profit factor MUST być pusty

#### Scenario: Strategia bez stopu

- **WHEN** uruchomienie strategii bez stopu zamknęło 40 transakcji
- **THEN** wartość oczekiwana w R, suma w R i obsunięcie w R MUST być puste
- **AND** odsetek zyskownych, wartość oczekiwana w procentach, obsunięcie w procentach i największa strata otwarta
  MUST mieć wartości

### Requirement: Każda transakcja jest widoczna

Raport MUST udostępniać listę transakcji, a każda MUST nieść: stronę, czas i cenę wejścia i wyjścia, wielkość,
początkowy stop, wynik w R, w procentach kapitału przy wejściu i w pieniądzu, najgłębszą stratę otwartą w procentach
kapitału przy wejściu, koszty rozbite na składniki, przyczynę wyjścia (`stop`, `target`, `trail`, `when`, `max_bars`,
`out_of_capital`, „koniec zakresu”) i oznaczenie rozstrzygnięcia pesymistycznego. W transakcji bez stopu początkowy
stop i wynik w R MUST być puste. Najgłębsza strata otwarta MUST być liczona na minutach po stronie wyjścia, przez
cały czas trwania pozycji, a transakcja, która nigdy nie była na minusie, MUST mieć zero.

#### Scenario: Transakcja zamknięta trailingiem

- **WHEN** pozycja zamyka się na przesuniętym stopie
- **THEN** jej przyczyną wyjścia MUST być `trail`, nie `stop`

#### Scenario: Najgłębsza strata otwarta

- **WHEN** przy zerowych kosztach i kapitale 10 000 long 0,5 jednostki otwarty po 20 000 schodzi do bid 19 800, a
  zamyka się po 20 100
- **THEN** transakcja MUST mieć najgłębszą stratę otwartą −1% i wynik +0,5%

### Requirement: Dwa punkty odniesienia

Raport MUST zawierać wynik „kup i trzymaj” instrumentu na tym samym zakresie i z tymi samymi kosztami oraz
wynik losowego wejścia: tyle samo wejść w losowych świecach decyzji, z tymi samymi wyjściami, rozmiarem i
kosztami, powtórzony ustaloną liczbę razy, podany jako mediana oraz 5. i 95. percentyl sumy R i zwrotu kapitału w
procentach. W uruchomieniu strategii bez stopu wartości w R MUST być puste. Losowanie MUST być powtarzalne z ziarna
zapisanego w raporcie.

#### Scenario: Powtórzenie z tym samym ziarnem

- **WHEN** to samo uruchomienie powtarza się z tym samym ziarnem
- **THEN** wynik losowego wejścia MUST być identyczny

#### Scenario: Losowe wejście strategii bez stopu

- **WHEN** strategia bez stopu ma raport z losowym wejściem
- **THEN** mediana i percentyle zwrotu w procentach MUST mieć wartości, a mediana i percentyle sumy R MUST być puste

### Requirement: Raport mówi, z czego powstał

Raport MUST zapisywać: identyfikator strategii, rewizję i hash jej treści, użyte parametry, model kosztów,
wymagany depozyt instrumentu, gdy wielkość pozycji od niego zależała, zakres, przeczytaną rozgrzewkę, wersję silnika,
ziarno oraz dla każdej przeczytanej serii odcisk danych (liczbę punktów, pierwszą i ostatnią chwilę, hash wartości) i
fragmenty zakresu, których archiwum nie potwierdziło.

#### Scenario: Dane zmieniły się między uruchomieniami

- **WHEN** dwa uruchomienia tej samej rewizji z tym samym wkładem dają różne wyniki
- **THEN** odciski danych w obu raportach MUST pokazywać, która seria się różni

#### Scenario: Raport strategii z ułamkiem depozytu

- **WHEN** uruchomienie strategii z `margin_fraction` liczyło wielkość z depozytu 0,05
- **THEN** raport MUST zapisywać depozyt 0,05 wśród tego, z czego powstał

### Requirement: Uruchomienia są trwałe i policzone

Każde uruchomienie, także nieudane i anulowane, MUST pozostać zapisane razem z wkładem. Dla każdej strategii
MUST być widoczna liczba zakończonych uruchomień, ze wszystkich jej rewizji, jako licznik prób.

#### Scenario: Kolejne uruchomienie

- **WHEN** strategia z trzema zakończonymi uruchomieniami kończy czwarte
- **THEN** jej licznik prób MUST wynosić cztery

### Requirement: Raport niesie krzywą kapitału

Raport MUST zawierać dzienną krzywą kapitału nominalnego, czyli wartość o każdej północy UTC w zakresie, i MUST to być ta
sama seria, z której liczone są Sharpe, Sortino i obsunięcie w procentach. Każdy punkt to wynik zrealizowany i otwarta
pozycja wyceniona na ostatniej minucie przed północą, pomniejszone o narosłe finansowanie. Raport wersji silnika, która
krzywej nie zapisywała, MUST mieć to pole puste.

#### Scenario: Krzywa zgodna z obsunięciem

- **WHEN** z krzywej raportu liczy się największe obsunięcie w procentach
- **THEN** wynik MUST być równy obsunięciu w procentach podanemu w raporcie

