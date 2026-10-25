# strategies-backtest Specification

## Purpose
Jak silnik odtwarza strategię na historii: kiedy decyduje, po jakiej cenie i za ile wypełnia zlecenia, co
kosztuje transakcja, jak rozstrzyga niejasne minuty i jak uruchomienie żyje jako zadanie w tle.
## Requirements
### Requirement: Decyzja na zamkniętej świecy, wypełnienie od następnej minuty

Silnik MUST liczyć formuły strategii na zamknięciu każdej świecy interwału decyzji, wyłącznie na danych
dostępnych w tej chwili. Zlecenie powstałe w tej decyzji MUST być aktywne najwcześniej od pierwszej minuty po
zamknięciu świecy, a jego wypełnienie MUST być rozstrzygane na serii `MINUTE` instrumentu handlowanego.
Świeca jeszcze się formująca MUST NOT brać udziału w żadnej decyzji.

#### Scenario: Zlecenie rynkowe z sygnału

- **WHEN** warunek wejścia jest prawdziwy na świecy H1 zamkniętej o 10:00 UTC
- **THEN** zlecenie rynkowe MUST wypełnić się na otwarciu minuty 10:00–10:01 UTC, z kosztami

### Requirement: Wynik nie zależy od danych po chwili decyzji

Transakcje zamknięte przed końcem krótszego zakresu MUST być identyczne w uruchomieniu na tym zakresie i na
zakresie dłuższym o dowolny okres, przy tej samej rewizji, parametrach i kosztach. Decyzje liczone dla całego
zakresu naraz MUST być identyczne z decyzjami liczonymi świeca po świecy na danych uciętych do chwili decyzji.

#### Scenario: Dłuższy zakres

- **WHEN** ta sama strategia biegnie raz na styczniu, raz na styczniu i lutym
- **THEN** transakcje zamknięte w styczniu MUST być w obu uruchomieniach takie same co do czasu, ceny i wyniku

### Requirement: Strona ceny i spread

Archiwum trzyma stronę bid, więc silnik MUST wyprowadzać ask jako bid powiększony o spread obowiązujący w danej
godzinie UTC. Pozycja długa MUST wchodzić po ask i wychodzić po bid, krótka MUST wchodzić po bid i wychodzić po
ask. Stop i cel MUST być sprawdzane po tej stronie ceny, po której pozycja się zamyka.

#### Scenario: Stop pozycji krótkiej

- **WHEN** high bid minuty jest o 1 pkt pod stopem shorta, a spread tej godziny wynosi 1,5 pkt
- **THEN** stop MUST zostać uznany za dotknięty

### Requirement: Zlecenia wejścia

Zlecenie `market` MUST wypełniać się na otwarciu pierwszej aktywnej minuty, powiększonym o poślizg. Zlecenie
`stop` MUST wypełniać się, gdy cena przekroczy jego poziom, po gorszej z dwóch cen: poziomu zlecenia i otwarcia
minuty. Zlecenie `limit` MUST wypełniać się po swojej cenie albo lepszej. Niewypełnione zlecenie MUST wygasać po
zadeklarowanej liczbie świec decyzji. Silnik MUST trzymać co najwyżej jedną pozycję i co najwyżej jedno
oczekujące zlecenie wejścia naraz, a sygnał wejścia w tym czasie MUST być pominięty.

#### Scenario: Stop wejścia przeskoczony luką

- **WHEN** zlecenie kupna stop stoi na 18 000, a pierwsza minuta po luce otwiera się na 18 040
- **THEN** wejście MUST nastąpić po 18 040 powiększonym o spread i poślizg, nie po 18 000

#### Scenario: Sygnał przy otwartej pozycji

- **WHEN** warunek wejścia short jest prawdziwy, gdy pozycja long jest otwarta
- **THEN** silnik MUST NOT otworzyć drugiej pozycji ani odwrócić istniejącej

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

### Requirement: Niejasna minuta rozstrzygana na niekorzyść strategii

Gdy w jednej minucie zakres ceny obejmuje dwa zdarzenia, których kolejności dane nie rozstrzygają (stop i cel,
wejście i stop), silnik MUST przyjąć kolejność gorszą dla strategii i MUST oznaczyć tak rozstrzygniętą
transakcję.

#### Scenario: Stop i cel w jednej minucie

- **WHEN** low i high jednej minuty obejmują zarówno stop, jak i cel longa
- **THEN** transakcja MUST zostać zamknięta na stopie
- **AND** MUST nieść oznaczenie rozstrzygnięcia pesymistycznego

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

### Requirement: Model kosztów jest obowiązkowy

Uruchomienie MUST podawać model kosztów: spread (jedna wartość albo profil 24 godzin UTC), poślizg na stronę,
stawki finansowania overnight dla longa i shorta (ułamek wartości pozycji za noc) i godzinę rozliczenia doby.
Uruchomienie bez modelu kosztów MUST zostać odrzucone. Zera MUST być przyjęte tylko wtedy, gdy podano je jawnie.
Finansowanie MUST być naliczane za każde przekroczenie godziny rozliczenia przy otwartej pozycji, także w dni
bez handlu.

#### Scenario: Brak modelu kosztów

- **WHEN** żądanie uruchomienia nie zawiera modelu kosztów
- **THEN** uruchomienie MUST zostać odrzucone przed zakolejkowaniem

#### Scenario: Pozycja przez weekend

- **WHEN** long jest otwarty od piątku 20:00 do poniedziałku 10:00 UTC przy rozliczeniu o 22:00 UTC
- **THEN** finansowanie MUST zostać naliczone za trzy noce

### Requirement: Uruchomienie jest zadaniem w tle z limitami

Żądanie uruchomienia MUST być przyjmowane od razu jako zakolejkowane, z parametrami w zakresach dokumentu.
Wartość poza zakresem MUST być odmową. Uruchomienia MUST wykonywać się w tle, w liczbie nie większej niż
ustawiony limit, i MUST NOT wstrzymywać obsługi innych tras procesu. Zakres przekraczający limit liczby świec
`MINUTE` MUST być odrzucony przed startem, a uruchomienie przekraczające limit czasu MUST skończyć się
niepowodzeniem z nazwaną przyczyną. Uruchomienie MUST dać się anulować. Uruchomienie przerwane restartem
procesu MUST zostać oznaczone jako przerwane, a nie pozostać „w toku”.

#### Scenario: Restart w trakcie

- **WHEN** proces restartuje się, gdy uruchomienie jest w toku
- **THEN** po starcie uruchomienie MUST mieć stan niepowodzenia z przyczyną „przerwane restartem”

#### Scenario: Za długi zakres

- **WHEN** zakres wymaga więcej świec `MINUTE`, niż pozwala limit
- **THEN** uruchomienie MUST zostać odrzucone przed zakolejkowaniem, z limitem i wymaganą liczbą w komunikacie

### Requirement: Ten sam wkład daje ten sam wynik

Uruchomienie tej samej rewizji z tymi samymi parametrami, kosztami, zakresem i ziarnem, na tej samej wersji
silnika i tych samych danych, MUST dać identyczny raport. Każda zmiana silnika, która zmienia wynik
któregokolwiek uruchomienia, MUST podnosić wersję silnika zapisywaną w raporcie.

#### Scenario: Złota strategia

- **WHEN** zmiana w silniku zmienia wynik dokumentu referencyjnego na zamrożonych danych, a wersja silnika
  pozostaje ta sama
- **THEN** sprawdzenie w CI MUST zakończyć się niepowodzeniem

### Requirement: Profil kosztów instrumentu ustawia operator

Pakiet MUST przechowywać co najwyżej jeden profil kosztów na instrument, o tym samym kształcie i z tym samym sprawdzeniem
co model kosztów uruchomienia. Profil ustawia i zmienia operator przez REST. Uruchomienie korzystające z profilu MUST
zapisywać wartości kosztów, a nie odwołanie do profilu. Zmiana profilu MUST NOT zmieniać żadnego wcześniej zapisanego
uruchomienia.

#### Scenario: Zmiana profilu po uruchomieniu

- **WHEN** operator zmienia spread w profilu instrumentu, który ma już zakończone uruchomienie
- **THEN** koszty zapisane w tamtym uruchomieniu MUST pozostać takie, jakie były

#### Scenario: Profil z niepełnym profilem spreadu

- **WHEN** operator zapisuje profil, którego godzinowy profil spreadu ma 23 wartości
- **THEN** zapis MUST zostać odrzucony z tym samym problemem, jaki dostałby model kosztów uruchomienia

### Requirement: Uruchomienie pamięta, kto o nie poprosił

Każde uruchomienie MUST zapisywać, czy zlecił je operator (REST), czy agent (narzędzie rozmowy). Uruchomienia zapisane
przed tą zmianą MUST być przypisane operatorowi. Licznik prób MUST liczyć uruchomienia obu zlecających tak samo.

#### Scenario: Uruchomienie z rozmowy

- **WHEN** agent zleca uruchomienie, które się kończy
- **THEN** uruchomienie MUST mieć zlecającego `agent`, a licznik prób strategii MUST wzrosnąć o jeden

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

