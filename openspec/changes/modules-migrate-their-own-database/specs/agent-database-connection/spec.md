## ADDED Requirements

### Requirement: Moduł sam doprowadza bazę do rewizji, dla której powstał

Moduł MUST doprowadzić własną bazę do rewizji schematu, dla której został zbudowany, zanim
zacznie odpowiadać na cokolwiek. Wdrożenie MUST NOT wymagać od operatora osobnego kroku
migracji — wdrożony kod i schemat, którego ten kod potrzebuje, MUST przyjeżdżać razem.

Moduł MUST NOT przyjmować żądań w trakcie migrowania. Trasa odpowiadająca, zanim schemat
jest gotowy, odpowiada z bazy, której kształtu nie zna.

Baza już będąca na właściwej rewizji MUST NOT powodować żadnego zapisu: uruchomienie
modułu, dla którego nie ma nic do zrobienia, MUST być nieodróżnialne od uruchomienia bez
tej zdolności — poza tym, co moduł o tym powie w swoim logu.

#### Scenario: Wdrożenie niosące nową rewizję

- **WHEN** moduł startuje z obrazem nowszym niż rewizja, na której stoi jego baza
- **THEN** brakujące migracje zostają wykonane
- **AND** moduł zaczyna odpowiadać dopiero po nich

#### Scenario: Baza już na właściwej rewizji

- **WHEN** moduł startuje przeciwko bazie, która jest na rewizji jego obrazu
- **THEN** nic nie zostaje zmigrowane
- **AND** moduł zaczyna odpowiadać

#### Scenario: Żądanie w trakcie migracji

- **WHEN** żądanie dociera do modułu, który jeszcze migruje
- **THEN** moduł nie odpowiada na nie danymi z bazy

### Requirement: Migruje dokładnie jeden proces naraz

Migracja MUST odbywać się pod blokadą wyłączną trzymaną w samej bazie, a nie w module —
dwa procesy tego samego modułu MUST NOT wykonywać migracji jednocześnie. Blokada w
procesie nie jest blokadą: instancje App Service nie widzą się nawzajem.

Proces, który blokady nie dostał, MUST poczekać na jej zwolnienie i dopiero potem
sprawdzić, na jakiej rewizji stoi baza — po czym MUST zastać robotę wykonaną i nie
powtarzać jej.

Czekanie MUST mieć kres. Proces, który nie doczekał się blokady, MUST odmówić pracy
i powiedzieć, że jej nie dostał — zamiast czekać bez końca na blokadę porzuconą przez
proces, który przestał istnieć.

Blokada MUST zostać zwolniona także wtedy, gdy migracja skończyła się błędem.

#### Scenario: Dwie instancje startują naraz

- **WHEN** dwie instancje modułu startują jednocześnie przeciwko jednej bazie wymagającej migracji
- **THEN** migracje wykonuje dokładnie jedna z nich
- **AND** druga zaczyna odpowiadać po tym, jak pierwsza skończyła

#### Scenario: Blokada nie zwalnia się w wyznaczonym czasie

- **WHEN** proces czeka na blokadę dłużej niż wynosi kres czekania
- **THEN** odmawia pracy, mówiąc, że nie dostał blokady

#### Scenario: Migracja kończy się błędem

- **WHEN** migracja przerywa się na błędzie
- **THEN** blokada zostaje zwolniona
- **AND** kolejny proces może spróbować

### Requirement: Moduł jest właścicielem tego, co jego migracje tworzą

Migracje MUST być wykonywane tą samą tożsamością, którą moduł łączy się z bazą na co
dzień. Obiekt utworzony przez migrację MUST być użyteczny dla modułu bez osobnego nadania
uprawnień.

Uprawnienie nadawane po fakcie jest krokiem, o którym nikt nie pamięta dopóki nie zawiedzie,
a zawodzi jako `permission denied` na tabeli, która istnieje — objaw czytający się jak brak
tabeli i prowadzący śledztwo w złą stronę.

Moduł MUST NOT wymagać do migrowania tożsamości szerszej niż ta, którą pracuje. Migracja
biegnąca jako administrator serwera jest podniesieniem uprawnień, którego reszta pracy
modułu nie potrzebuje.

#### Scenario: Nowa tabela jest od razu użyteczna

- **WHEN** migracja tworzy nową tabelę
- **THEN** moduł czyta z niej i pisze do niej bez osobnego nadania uprawnień

#### Scenario: Migracja nie sięga po szersze uprawnienia

- **WHEN** moduł migruje bazę
- **THEN** robi to tą samą tożsamością, którą ją potem czyta

### Requirement: Moduł, który nie zdołał zmigrować, nie udaje że działa

Moduł MUST odmówić pracy, gdy migracja się nie powiodła, i MUST powiedzieć w swoim logu,
która rewizja zawiodła. Proces MUST zakończyć się niepowodzeniem — moduł odpowiadający
częściowo, z połową schematu, jest gorszy niż moduł, którego nie ma, bo wygląda na
działający.

Moduł MUST odmówić pracy także wtedy, gdy baza jest **przed** rewizją jego obrazu mimo
wykonanej migracji, oraz gdy jest **za** nią — pierwsze znaczy, że migracja nie zrobiła
tego, co miała, a drugie, że wdrożono obraz starszy niż baza, i kod pracujący na schemacie
z przyszłości jest tak samo nieprzetestowany jak na schemacie z przeszłości.

Odmowa MUST nazwać obie rewizje: tę, której oczekuje obraz, i tę, na której stoi baza.

#### Scenario: Migracja nie przechodzi

- **WHEN** migracja kończy się błędem
- **THEN** moduł nie zaczyna odpowiadać
- **AND** log niesie rewizję, na której się przerwała

#### Scenario: Baza wyprzedza obraz

- **WHEN** moduł startuje przeciwko bazie na rewizji nowszej niż jego obraz
- **THEN** odmawia pracy, nazywając obie rewizje

#### Scenario: Wdrożenie z nieudaną migracją nie wypuszcza wersji

- **WHEN** wdrożenie niesie migrację, która nie przechodzi
- **THEN** nowa wersja nie zaczyna obsługiwać ruchu
- **AND** wdrożenie kończy się niepowodzeniem, zamiast zgłosić powodzenie
