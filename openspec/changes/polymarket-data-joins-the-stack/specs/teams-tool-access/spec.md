## MODIFIED Requirements

### Requirement: Ta sama nazwa narzędzia z dwóch serwerów jest odmową

Gdy więcej niż jeden skonfigurowany serwer ogłasza narzędzie o tej samej nazwie, moduł MUST
odmówić — przy zapisie rewizji przypisującej tę nazwę i przy uruchomieniu przebiegu, który ją
niesie — komunikatem nazywającym **wszystkie** serwery, które tę nazwę ogłaszają. Moduł MUST NOT
wybrać jednego z nich i MUST NOT wymienić tylko dwóch pierwszych: komunikat, który nie wymienia
wszystkich, każe operatorowi odkonfigurować serwer i zobaczyć tę samą odmowę jeszcze raz.

Definicja wskazuje narzędzie po nazwie i tylko po nazwie (patrz „Moduł nie trzyma kopii tego,
co ogłasza serwer narzędzi"), więc przy kolizji nie ma czym rozstrzygnąć, który z nich miał na
myśli operator. Cichy wybór jednego z nich dałby przebiegi, które różnią się użytym narzędziem,
a wyglądają identycznie w rewizji.

Liczba serwerów jest konfiguracją, nie stałą: moduł MAY być skonfigurowany z dowolną ich liczbą
(patrz „Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie"), a wymaganie to MUST NOT
zakładać żadnej konkretnej.

#### Scenario: Dwa serwery ogłaszają tę samą nazwę

- **WHEN** operator uruchamia przebieg, którego agent ma przypisane narzędzie o nazwie ogłaszanej
  przez dwa skonfigurowane serwery
- **THEN** moduł odmawia uruchomienia, nazywając nazwę i oba serwery
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Kolizja przy zapisie rewizji

- **WHEN** operator zapisuje rewizję przypisującą agentowi nazwę ogłaszaną przez więcej niż jeden
  serwer
- **THEN** zapis zostaje odrzucony komunikatem nazywającym nazwę i wszystkie te serwery

#### Scenario: Kolizja obejmuje więcej niż dwa serwery

- **WHEN** tę samą nazwę narzędzia ogłaszają trzy skonfigurowane serwery
- **THEN** komunikat odmowy wymienia wszystkie trzy
- **AND** MUST NOT wymieniać wyłącznie dwóch z nich
