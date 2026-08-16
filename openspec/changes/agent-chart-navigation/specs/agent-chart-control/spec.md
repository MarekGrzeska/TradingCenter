## MODIFIED Requirements

### Requirement: Narzędzie ustawia zawartość aktywnego slotu

Moduł MUST publikować modelowi narzędzie, które ustawia zawartość aktywnego slotu
terminala: zestaw wskaźników wraz z parametrami i kolorami, symbol, interwał oraz **kadr**
— fragment osi czasu, który ma być widoczny.

Polecenie MUST być **deklaratywne**: niesie stan, który ma być widoczny, a nie różnicę
wobec stanu poprzedniego. Pole pominięte MUST znaczyć „zostaw jak jest", nigdy „wyczyść" —
model proszony o dołożenie średniej nie ma jak wyzerować symbolu przez przeoczenie.
Pominięty kadr MUST znaczyć „zostaw operatora tam, gdzie patrzy".

Wskaźnik w poleceniu MUST być identyfikowany tak, jak nazywa go katalog archiwum, a jego
parametry MUST mieścić się w granicach, które katalog podaje. Kolor MUST pochodzić
z palety terminala albo być pominięty.

Kadr MUST dać się wskazać na trzy sposoby i MUST być podany dokładnie jednym z nich:
zakresem czasu „od–do", punktem w czasie wraz z liczbą świec wokół niego, albo liczbą
ostatnich świec. Czas MUST być podawany w skali absolutnej (UTC), nie względem chwili
odczytu — polecenie zapisane w logu MUST znaczyć po godzinie to samo, co znaczyło
w chwili, gdy padło. „Ostatnie N świec" jest wyjątkiem nazwanym wprost: znaczy „koniec
serii", cokolwiek nim jest w chwili zastosowania.

#### Scenario: Model pokazuje średnią

- **WHEN** model woła narzędzie z jednym wskaźnikiem i jego okresem
- **THEN** aktywny slot rysuje ten wskaźnik z tym okresem

#### Scenario: Model zmienia sam interwał

- **WHEN** model woła narzędzie podając wyłącznie interwał
- **THEN** interwał slotu się zmienia, a jego wskaźniki i symbol zostają

#### Scenario: Model podaje pełny zestaw wskaźników

- **WHEN** model woła narzędzie z trzema wskaźnikami, a slot rysował dwa inne
- **THEN** slot rysuje te trzy, bo polecenie niesie stan, a nie różnicę

#### Scenario: Model przenosi operatora na wskazaną datę

- **WHEN** model woła narzędzie z kadrem „od–do" obejmującym jeden dzień sprzed tygodnia
- **THEN** aktywny slot pokazuje ten dzień
- **AND** symbol, interwał i wskaźniki slotu zostają nietknięte

#### Scenario: Model przybliża ostatnie świece

- **WHEN** model woła narzędzie z kadrem „ostatnie 100 świec"
- **THEN** slot pokazuje 100 najnowszych świec, kończąc się na prawej krawędzi serii

#### Scenario: Polecenie bez kadru zostawia widok

- **WHEN** model woła narzędzie z samym wskaźnikiem, a operator jest przewinięty w historię
- **THEN** wskaźnik zostaje dorysowany, a operator patrzy nadal na ten sam fragment osi

### Requirement: Odmowa narzędzia nazywa, co poprawić

Narzędzie MUST odmówić polecenia, którego terminal nie mógłby wykonać: nieznanego
wskaźnika, parametru poza granicami katalogu, symbolu albo interwału, w którym archiwum
nie zbiera danych, oraz koloru spoza palety.

Narzędzie MUST odmówić także kadru, który nie opisuje żadnego fragmentu osi: podanego
więcej niż jednym sposobem albo żadnym, z początkiem nie wcześniejszym niż koniec,
z liczbą świec poza granicami, które narzędzie ogłasza, oraz kadru leżącego w całości
w przyszłości.

Odmowa MUST wracać do modelu jako wynik wywołania wraz ze zdaniem mówiącym, co zmienić —
tak samo jak odmowa serwera narzędzi (`agent-tools`, „Odmowa narzędzia jest wynikiem, nie
awarią tury"). Odmowa MUST NOT zapisać polecenia ani zmienić czegokolwiek na wykresie.

#### Scenario: Symbol, którego archiwum nie zbiera

- **WHEN** model woła narzędzie z symbolem spoza zbieranych par
- **THEN** dostaje odmowę mówiącą, które symbole są zbierane
- **AND** wykres zostaje bez zmian

#### Scenario: Parametr poza granicami katalogu

- **WHEN** model woła narzędzie z okresem spoza zakresu, który podaje katalog
- **THEN** dostaje odmowę nazywającą ten zakres i może zawołać ponownie

#### Scenario: Odmowa nie zostawia śladu na wykresie

- **WHEN** narzędzie odmawia polecenia niosącego trzy wskaźniki, z których jeden jest nieznany
- **THEN** nie zostaje zastosowany żaden z nich, a numer ostatniego polecenia się nie zmienia

#### Scenario: Kadr podany dwoma sposobami naraz

- **WHEN** model woła narzędzie z kadrem niosącym jednocześnie zakres „od–do" i liczbę ostatnich świec
- **THEN** dostaje odmowę mówiącą, że kadr wskazuje się dokładnie jednym sposobem
- **AND** nic nie zostaje zapisane

#### Scenario: Odwrócony zakres kadru

- **WHEN** model woła narzędzie z kadrem, którego początek jest późniejszy niż koniec
- **THEN** dostaje odmowę nazywającą oba końce i może zawołać ponownie

#### Scenario: Liczba świec poza granicami

- **WHEN** model woła narzędzie z kadrem żądającym liczby świec spoza granic, które narzędzie ogłasza
- **THEN** dostaje odmowę podającą te granice

#### Scenario: Kadr w całości w przyszłości

- **WHEN** model woła narzędzie z kadrem obejmującym wyłącznie czas późniejszy niż teraz
- **THEN** dostaje odmowę mówiącą, że archiwum nie ma tam świec
- **AND** wykres zostaje bez zmian
