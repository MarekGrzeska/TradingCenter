# strategies-tools Specification

## Purpose
Narzędzia, którymi agent w rozmowie pisze, sprawdza i uruchamia strategie: co każde robi, czego odmawia i gdzie kończy
się swoboda agenta. Koszty, kolejka i licznik prób są granicą, której agent nie przesuwa.
## Requirements
### Requirement: Powierzchnia narzędzi pakietu strategii

Pakiet MUST publikować narzędzia: `strategy_language` (opis języka), `list_strategies`, `read_strategy`,
`validate_strategy`, `save_strategy`, `run_backtest`, `read_backtest` i `compare_runs`. Każde narzędzie MUST używać tej samej
logiki co odpowiadająca mu trasa REST, czyli tej samej walidacji i tych samych odmów, a odmowa MUST wracać do modelu jako
wynik z problemami, ich ścieżkami, kolumnami i podpowiedziami. `strategy_language` MUST powstawać z tego samego rejestru
i katalogu co `GET /language`. `read_strategy` MUST podawać dokument wskazanej albo ostatniej rewizji, jego streszczenie,
licznik prób i to, czy instrument ma profil kosztów. `read_backtest` MUST podawać stan, metryki, punkty odniesienia i
pochodzenie wyniku, ale MUST NOT oddawać modelowi krzywej kapitału ani pełnej listy transakcji.

Serializowana powierzchnia narzędzi pakietu MUST mieścić się w nazwanym suficie znaków.

#### Scenario: Pakiet nieobecny

- **WHEN** proces działa bez `STRATEGIES_DATABASE_URL`
- **THEN** rozmowa MUST NOT dostać żadnego narzędzia strategii, a pozostałe narzędzia MUST działać jak dotąd

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wskaźnik z wyjściem liniowym
- **THEN** `strategy_language` MUST go wymieniać bez zmiany kodu pakietu

### Requirement: Narzędzia strategii dostaje tylko rozmowa

Narzędzia pakietu MUST trafiać do rejestru rozmowy jako funkcje w procesie. MUST NOT trafiać do rejestru zespołów ani do
katalogu narzędzi, z którego czytają reguły alertów, i MUST NOT być serwowane przez sieć pod `/strategies/mcp`.

#### Scenario: Narzędzia dla agenta zespołu

- **WHEN** operator przydziela narzędzia agentowi w zespole
- **THEN** wśród dostępnych narzędzi MUST NOT być żadnego narzędzia strategii

### Requirement: Agent zapisuje rewizje jako autor `agent`

`save_strategy` MUST tworzyć nową strategię albo kolejną rewizję wskazanej strategii, z tym samym sprawdzeniem co zapis
przez REST, i MUST zapisywać autora `agent`. Odrzucony dokument MUST NOT zostawić śladu, a odpowiedź MUST zawierać
wszystkie problemy naraz. Odpowiedź udanego zapisu MUST nieść numer rewizji, streszczenie dokumentu i zmiany względem
poprzedniej rewizji. Narzędzie MUST przyjmować rewizję, na której agent oparł zmianę. Gdy ostatnia rewizja jest inna,
MUST odmówić, nazwać ostatnią rewizję i niczego nie zapisać.

#### Scenario: Zmiana stopu na prośbę operatora

- **WHEN** agent zapisuje zmieniony stop strategii, której ostatnią rewizją jest 4, podając podstawę 4
- **THEN** MUST powstać rewizja 5 z autorem `agent`
- **AND** odpowiedź MUST wymieniać zmianę pod ścieżką `exits.stop` z wartością przed i po

#### Scenario: Operator zapisał w międzyczasie

- **WHEN** agent zapisuje z podstawą 4, a operator zapisał już rewizję 5
- **THEN** zapis MUST zostać odrzucony z informacją, że ostatnia rewizja to 5
- **AND** MUST NOT powstać rewizja 6

### Requirement: Agent nie podaje kosztów

`run_backtest` MUST brać model kosztów z profilu kosztów instrumentu i MUST NOT przyjmować kosztów jako argumentu.
Instrument bez profilu MUST dawać odmowę mówiącą, że profil ustawia operator w zakładce Strategies. Agent MUST NOT mieć
narzędzia, które ustawia albo zmienia profil kosztów.

#### Scenario: Instrument bez profilu kosztów

- **WHEN** agent prosi o backtest strategii na instrumencie, który nie ma profilu kosztów
- **THEN** narzędzie MUST odmówić, a odmowa MUST mówić, gdzie operator ustawia koszty
- **AND** MUST NOT powstać uruchomienie

### Requirement: Uruchomienie z rozmowy jest policzone i ograniczone

`run_backtest` MUST kolejkować uruchomienie zapisane jako zlecone przez agenta i liczone do licznika prób jak każde inne.
Narzędzie MUST odmówić, gdy w kolejce czeka albo liczy się już jakieś uruchomienie zlecone przez agenta, i MUST nazwać
jego identyfikator. Narzędzie MUST czekać na wynik nie dłużej niż czas podany w swoim opisie. Gdy uruchomienie się
skończy, narzędzie MUST oddać jego główne metryki. W przeciwnym razie MUST oddać identyfikator i stan, żeby wynik dało
się odczytać przez `read_backtest`. Opis narzędzia MUST mówić, że każde uruchomienie jest próbą liczoną przeciw strategii i że
narzędzie służy do uruchomień, o które poprosił operator.

#### Scenario: Krótkie uruchomienie

- **WHEN** agent zleca backtest, który kończy się w czasie oczekiwania narzędzia
- **THEN** odpowiedź MUST nieść identyfikator uruchomienia i jego główne metryki
- **AND** licznik prób strategii MUST wzrosnąć o jeden

#### Scenario: Druga prośba, gdy pierwsza czeka

- **WHEN** agent zleca backtest, gdy jego poprzednie uruchomienie jest jeszcze w kolejce
- **THEN** narzędzie MUST odmówić, nazywając czekające uruchomienie

#### Scenario: Długie uruchomienie

- **WHEN** uruchomienie nie kończy się w czasie oczekiwania narzędzia
- **THEN** odpowiedź MUST nieść identyfikator i stan uruchomienia, a uruchomienie MUST liczyć się dalej

### Requirement: Porównanie tylko porównywalnych uruchomień

`compare_runs` MUST przyjmować od dwóch do pięciu zakończonych uruchomień i MUST zestawiać ich metryki tylko wtedy, gdy
mają ten sam zakres, ten sam model kosztów, ten sam wymagany depozyt instrumentu (także jego brak) i tę samą wersję
silnika. Gdy którakolwiek z tych rzeczy się różni, narzędzie MUST odmówić i MUST nazwać, co się różni i w którym
uruchomieniu. Uruchomienie niezakończone MUST dawać odmowę z jego stanem. Zestawienie MUST NOT wskazywać lepszego
uruchomienia ani porównywać metryk z progami.

#### Scenario: Różne koszty

- **WHEN** agent porównuje dwa uruchomienia, które różnią się spreadem
- **THEN** narzędzie MUST odmówić, a odmowa MUST nazywać różnicę w kosztach

#### Scenario: Porównywalne uruchomienia

- **WHEN** agent porównuje dwa zakończone uruchomienia o tym samym zakresie, kosztach i wersji silnika
- **THEN** odpowiedź MUST zestawiać ich metryki obok siebie, bez oceny, które jest lepsze

#### Scenario: Różny depozyt

- **WHEN** agent porównuje dwa uruchomienia strategii z `margin_fraction`, liczone z depozytem 0,05 i 0,10
- **THEN** narzędzie MUST odmówić, a odmowa MUST nazywać oba depozyty

### Requirement: Opisy narzędzi prowadzą autora strategii

Opisy narzędzi MUST mówić modelowi, że:
- gdy opis operatora zostawia wartość otwartą, model pyta o nią albo zapisuje przyjęte założenie w `notes`;
- streszczenie zwracane przez zapis i walidację należy porównać z opisem operatora przed odpowiedzią;
- parametrów nie zmienia się po to, żeby szukać lepszego wyniku.

#### Scenario: Opis bez godzin sesji

- **WHEN** model czyta opisy narzędzi strategii
- **THEN** opis `save_strategy` MUST mówić, że każde założenie, którego operator nie podał, trafia do `notes`

