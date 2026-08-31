## Purpose

Zestaw narzędzi, który moduł publikuje klientowi MCP: na jakie pytania o posty odpowiada modelowi,
w jak dużych porcjach — i dlaczego nie ma tu ani jednego narzędzia zmieniającego stan.

## ADDED Requirements

### Requirement: Zestaw wyłącznie czyta

Zestaw MUST zawierać wyłącznie narzędzia czytające. Żadne narzędzie MUST NOT zbierać na żądanie,
wzbogacać na żądanie, kasować posta, zmieniać konfiguracji modułu ani sięgać po cokolwiek
związanego z rachunkiem, zleceniem czy pozycją.

To nie jest powtórzenie reguły z `polymarket-data-tools`, tylko inny wniosek z tej samej zasady:
tam narzędzia piszą, bo istnieje **lista obserwacji**, którą operator układa i którą model może
uzupełnić. Tutaj takiej listy nie ma — źródło jest zbierane w całości — więc narzędzie zapisujące
nie miałoby czego zapisać poza tym, co pętla robi sama. Ograniczenie MUST być sprawdzane testem,
bo narzędzia stoją w tym samym procesie co zapis.

#### Scenario: Lista narzędzi nie zawiera zapisu

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** żadne z nich MUST NOT zmieniać stanu modułu

#### Scenario: Narzędzie sięga po zapis

- **WHEN** kod narzędzia wywołuje operację zmieniającą archiwum albo konfigurację
- **THEN** MUST to wywrócić testy modułu, zanim zmiana zostanie wdrożona

### Requirement: Zestaw domyka drogę od pytania do treści

Zestaw MUST pozwalać modelowi dojść od pytania operatora do konkretnego posta bez wiedzy zdobytej
gdzie indziej: odczytać ostatnie posty z zawężeniem po ocenie wpływu, odczytać dowolne okno
z zawężeniem po źródle, ocenie i temacie, otworzyć jeden post w całości oraz sprawdzić stan
archiwum. Model MUST NOT musieć znać identyfikatora posta z góry.

#### Scenario: Pytanie o dzień wstecz

- **WHEN** operator pyta o posty z wczoraj o wysokim wpływie
- **THEN** model MUST móc odpowiedzieć, wołając narzędzia zestawu i nie znając wcześniej żadnego
  identyfikatora

### Requirement: Lista wydaje skrót, pełną treść wydaje osobne narzędzie

Narzędzie zwracające listę MUST wydawać treść w skróconej formie wraz z oceną, tematami i czasem
publikacji. Pełna treść MUST być dostępna wyłącznie przez narzędzie odczytujące jeden post.

Powód jest arytmetyczny: doba postów w pełnej treści to okno kontekstu wydane na jedno wywołanie,
zanim model zdąży cokolwiek z nimi zrobić.

#### Scenario: Doba postów w jednym wywołaniu

- **WHEN** model prosi o listę postów z ostatnich 24 godzin
- **THEN** każdy post MUST być skrócony
- **AND** odpowiedź MUST nieść identyfikator pozwalający dociągnąć pełną treść

### Requirement: Model dostaje oryginał, tłumaczenie na żądanie

Narzędzia MUST domyślnie wydawać treść w języku źródła. Tłumaczenie MUST być wydawane wyłącznie
wtedy, gdy wywołanie o nie prosi — jest robione dla operatora patrzącego na ekran, nie dla modelu,
który czyta oryginał bez straty.

#### Scenario: Domyślne wywołanie

- **WHEN** model woła narzędzie bez prośby o tłumaczenie
- **THEN** odpowiedź MUST nieść treść oryginalną i MUST NOT nieść tłumaczenia

### Requirement: Narzędzie statusu odróżnia ciszę archiwum od cichego dnia

Zestaw MUST zawierać narzędzie odpowiadające, kiedy ostatnio udało się zebrać, od kiedy moduł
zbiera, które źródła są czynne i czy dostęp do modelu jest skonfigurowany.

Bez niego model odpowiada „brak postów" na obie sytuacje: gdy Trump milczał i gdy archiwum stoi
od trzech godzin.

#### Scenario: Archiwum stoi, a model jest pytany o posty

- **WHEN** ostatni udany zbiór jest znacznie starszy niż odstęp zbioru
- **THEN** model MUST móc nazwać archiwum nieświeżym, zamiast twierdzić, że postów nie było
