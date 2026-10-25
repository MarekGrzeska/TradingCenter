## MODIFIED Requirements

### Requirement: Wyjścia i limity

Stop, jeśli dokument go ma, MUST być wyliczany raz, na świecy wejścia. Cel, jeśli jest, również. Trailing MUST zaczynać
działać, gdy wynik otwartej pozycji osiągnie zadeklarowany próg w R, i MUST wyłącznie zacieśniać stop. Wyjście z formuły
`when` i wyjście po `max_bars` MUST wypełniać się na otwarciu pierwszej minuty po decyzji. Stop przeskoczony
luką MUST wypełniać się po pierwszej cenie za luką. Po osiągnięciu `daily_stop_r` silnik MUST NOT otwierać
nowych pozycji do końca dnia UTC, a prawdziwy `no_entry` MUST blokować wejście na tej świecy. Pozycja otwarta
na końcu zakresu MUST zostać zamknięta po ostatniej cenie z przyczyną „koniec zakresu”. Pozycja bez stopu MUST zamykać
się wyłącznie przez `when`, `max_bars`, cel, brak kapitału albo koniec zakresu.

#### Scenario: Trailing tylko zacieśnia

- **WHEN** trailing przesunął stop longa na 18 100, a potem cena spada
- **THEN** stop MUST pozostać na 18 100

#### Scenario: Stop dnia

- **WHEN** zrealizowany wynik dnia spada do −2 R przy `daily_stop_r` równym −2
- **THEN** żadne wejście MUST NOT nastąpić do północy UTC, nawet przy prawdziwym warunku

#### Scenario: Wyjście pięć minut przed końcem sesji

- **WHEN** strategia na `MINUTE_5` bez stopu ma `exits.when` równe `minutes_to_session_close(NEW_YORK) <= 5`, a 2 lipca
  2026 jest otwarty long
- **THEN** pozycja MUST zamknąć się na otwarciu minuty 19:55 UTC (15:55 w Nowym Jorku, 21:55 w Polsce)

### Requirement: Rozmiar pozycji i wynik w R

Przy `risk_fraction` wielkość pozycji MUST wynikać z ułamka bieżącego kapitału podzielonego przez odległość
wejścia od stopu. Przy `fixed_units` MUST być stała. Przy `margin_fraction` wielkość MUST być taka, żeby wymagany
depozyt pozycji, czyli jej wartość przy wejściu razy wymagany depozyt instrumentu, był równy ułamkowi bieżącego
kapitału. Przy `notional_fraction` wartość pozycji przy wejściu MUST być równa ułamkowi bieżącego kapitału. Wynik
transakcji w R MUST być jej wynikiem po kosztach, podzielonym przez początkową odległość od stopu razy wielkość, a w
transakcji bez stopu MUST być pusty. Wynik transakcji w procentach MUST być jej wynikiem po kosztach podzielonym przez
kapitał w chwili wejścia. Kapitał MUST startować od kapitału nominalnego podanego w uruchomieniu.

#### Scenario: Ułamek ryzyka

- **WHEN** kapitał wynosi 10 000, `risk_fraction` to 0,005, a stop jest 40 pkt od wejścia
- **THEN** wielkość pozycji MUST wynosić 1,25 jednostki

#### Scenario: Ułamek depozytu

- **WHEN** kapitał wynosi 10 000, `margin_fraction` to 0,05, wymagany depozyt instrumentu 5%, a wejście 20 000
- **THEN** wielkość pozycji MUST wynosić 0,5 jednostki

#### Scenario: Ułamek wartości pozycji

- **WHEN** kapitał wynosi 10 000, `notional_fraction` to 1, a wejście 20 000
- **THEN** wielkość pozycji MUST wynosić 0,5 jednostki

#### Scenario: Wynik transakcji bez stopu

- **WHEN** transakcja bez stopu kończy się zyskiem 150 po kosztach przy kapitale 10 000 w chwili wejścia
- **THEN** jej wynik w R MUST być pusty, a wynik w procentach MUST wynosić 1,5%

## ADDED Requirements

### Requirement: Brak kapitału zamyka pozycję

Gdy kapitał, czyli kapitał nominalny powiększony o wynik zrealizowany i o otwartą pozycję wycenioną po stronie wyjścia,
spada do zera, silnik MUST zamknąć pozycję tak, jak zamyka stop: na poziomie, przy którym kapitał osiąga zero, albo po
pierwszej cenie za luką. Przyczyną wyjścia MUST być `out_of_capital`. Po takim zamknięciu silnik MUST NOT otwierać
żadnej pozycji do końca zakresu. Reguła MUST obowiązywać każdą strategię, ze stopem i bez.

#### Scenario: Long bez stopu traci cały kapitał

- **WHEN** przy zerowych kosztach i kapitale 10 000 long 1 jednostki otwarty po 20 000 bez stopu, a minuta bid spada
  od 10 050 do 9 990
- **THEN** pozycja MUST zamknąć się po 10 000 z przyczyną `out_of_capital`
- **AND** żadne kolejne wejście MUST NOT nastąpić, nawet przy prawdziwym warunku

### Requirement: Wymagany depozyt instrumentu pochodzi od brokera

Gdy uruchomienie strategii z `margin_fraction` potrzebuje wymaganego depozytu, a profil instrumentu go nie ma, pakiet
MUST pobrać go sam z warunków instrumentu u brokera, przez archiwum w tym procesie, bez kroku operatora. Pakiet MUST
zapisać go w profilu razem z surową wartością i jednostką brokera, bez zmiany pozostałych wartości profilu. Depozyt
podany w procentach MUST być przeliczony na ułamek. Brak wartości albo inna jednostka MUST być odmową uruchomienia,
która je nazywa, bez zapisu i bez wartości domyślnej. Operator MAY zmienić depozyt w profilu. Uruchomienie MUST
zapisywać użytą wartość depozytu, a nie odwołanie do profilu, a zmiana profilu MUST NOT zmieniać zapisanych
uruchomień. Uruchomienie strategii z innym trybem wielkości MUST NOT potrzebować depozytu.

#### Scenario: Pierwsze uruchomienie z ułamkiem depozytu

- **WHEN** uruchomienie strategii z `margin_fraction` dotyczy instrumentu, którego profil ma koszty, ale nie ma depozytu,
  a broker podaje `margin_factor` 5 w jednostce `PERCENTAGE`
- **THEN** profil MUST dostać depozyt 0,05, a jego koszty MUST pozostać takie, jakie były
- **AND** uruchomienie MUST zapisać depozyt 0,05

#### Scenario: Depozyt w nieznanej jednostce

- **WHEN** broker podaje wymagany depozyt instrumentu w jednostce innej niż procenty
- **THEN** uruchomienie MUST zostać odrzucone z komunikatem nazywającym jednostkę, a profil MUST NOT się zmienić

#### Scenario: Strategia bez ułamka depozytu

- **WHEN** uruchomienie strategii z `fixed_units` dotyczy instrumentu, dla którego broker nie podaje depozytu
- **THEN** uruchomienie MUST przebiec bez odczytu depozytu
