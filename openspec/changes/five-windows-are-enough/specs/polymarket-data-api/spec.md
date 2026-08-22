## MODIFIED Requirements

### Requirement: Zmiany w oknach są liczone przy odczycie

Kontrakt MUST udostępniać zmianę ceny wyniku w oknach 5 minut, godziny, 4 godzin, doby
i 7 dni. Zestaw jest gęsty przy teraz i rzadki dalej, i to jest wybór, nie przeoczenie: rynek
predykcyjny rusza się wolno, więc drugie okno rzędu kwadransa powtarza to, co mówi pierwsze.

Wartości MUST być liczone z zebranej historii w chwili odczytu, a nie odczytywane z tabeli
utrzymywanej osobnym zadaniem — nie ma zadania, które by ją utrzymywało, i utrzymanie takiej
tabeli MUST NOT być wymagane, dopóki pomiar nie pokaże, że liczenie przy odczycie kosztuje za
dużo. Każde okno to osobne zapytanie na wynik, więc liczba okien jest mnożnikiem kosztu odczytu
i MUST NOT rosnąć bez odbiorcy, który je czyta.

Okno, dla którego historia nie sięga wystarczająco wstecz, MUST być zwrócone jako brak wartości
nazywający swój powód, a MUST NOT jako zero ani jako zmiana liczona od najstarszego punktu, jaki
jest — pierwsze kłamie o rynku, drugie o oknie.

Punkt bazowy MUST być wybierany z tolerancją na nierówny takt próbkowania i odpowiedź MUST nieść
moment, z którego faktycznie pochodzi.

#### Scenario: Odczyt zmian dla wydarzenia

- **WHEN** terminal odczytuje zmiany dla obserwowanego wydarzenia
- **THEN** dostaje dla każdego wyniku zmianę w pięciu oknach
- **AND** przy każdym oknie moment punktu bazowego, z którego została policzona

#### Scenario: Historia krótsza niż okno

- **WHEN** zebrana historia wyniku jest krótsza niż okno 7 dni
- **THEN** wartość dla tego okna jest brakiem nazywającym przyczynę
- **AND** MUST NOT być zerem ani zmianą liczoną od najstarszego posiadanego punktu

#### Scenario: Okno spoza zestawu

- **WHEN** konsument spodziewa się okna, którego kontrakt nie wylicza
- **THEN** kontrakt MUST NOT go zwrócić
- **AND** zestaw okien MUST być odczytywalny z kontraktu, a nie zapisany drugi raz po stronie konsumenta
