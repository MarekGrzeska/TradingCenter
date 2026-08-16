# market-data-database-connection Specification

## Purpose
Opisuje, na jakich warunkach `market-data` łączy się ze swoją bazą, gdy ta stoi poza maszyną modułu:
czym się przedstawia, jak radzi sobie z poświadczeniem, które wygasa, i kiedy odmawia pracy zamiast
działać w konfiguracji, która wygląda na działającą.
## Requirements
### Requirement: Połączenie z bazą jest szyfrowane

Gdy baza stoi poza maszyną modułu, ruch do niej przechodzi przez sieć, której moduł nie
kontroluje — takie połączenie MUST być wyłącznie szyfrowane. Konfiguracja wskazująca hosta
zdalnego, która szyfrowania nie wymusza, MUST być odrzucona przy starcie — moduł MUST NOT
połączyć się nieszyfrowanie ani ciszej obniżyć wymagania, gdy szyfrowane połączenie się nie
uda. Baza na pętli zwrotnej tej samej maszyny MAY być osiągana bez szyfrowania — ruch do niej
sieci nie opuszcza.

#### Scenario: Konfiguracja nie wymusza szyfrowania

- **WHEN** moduł startuje w trybie tożsamości z konfiguracją połączenia do hosta zdalnego,
  która nie wymaga szyfrowania
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje konfigurację połączenia jako przyczynę

#### Scenario: Serwer nie oferuje szyfrowania

- **WHEN** serwer zdalnej bazy odrzuca zestawienie połączenia szyfrowanego
- **THEN** moduł nie nawiązuje połączenia nieszyfrowanego
- **AND** zgłasza błąd połączenia

#### Scenario: Baza lokalna bez szyfrowania

- **WHEN** moduł startuje bez skonfigurowanej tożsamości, a `DATABASE_URL` wskazuje pętlę
  zwrotną bez `sslmode`
- **THEN** moduł startuje i łączy się z bazą

### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Wobec bazy zdalnej moduł MUST uwierzytelniać się poświadczeniem wystawianym dla jego
tożsamości i pobieranym przy nawiązywaniu połączenia; trwałe hasło do bazy zdalnej MUST NOT
być wymagane do pracy modułu ani przechowywane w jego konfiguracji. Tryb tożsamości wybiera
skonfigurowana nazwa roli (`DATABASE_USER`); konfiguracja trybu tożsamości, której
`DATABASE_URL` niesie własne poświadczenie, MUST być odrzucona przy starcie.

#### Scenario: Poświadczenia nie da się uzyskać

- **WHEN** moduł startuje w trybie tożsamości, a wystawca poświadczeń jest nieosiągalny lub
  odmawia
- **THEN** moduł odmawia startu z komunikatem wskazującym uzyskanie poświadczenia jako
  przyczynę
- **AND** MUST NOT sięgać po zapasowe hasło ani ponawiać w nieskończonej pętli bez zgłoszenia
  błędu

#### Scenario: Poświadczenie w URL obok tożsamości

- **WHEN** moduł startuje w trybie tożsamości, a `DATABASE_URL` niesie nazwę użytkownika lub
  hasło
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że poświadczenie z URL nie byłoby użyte

### Requirement: Wygasające poświadczenie jest odnawiane

Poświadczenie ma ograniczoną ważność, krótszą niż czas pracy modułu. Moduł MUST odnawiać je tak, by
połączenie nawiązywane po jego wygaśnięciu zestawiało się poprawnie. Wygaśnięcie poświadczenia
MUST NOT objawiać się jako trwałe zatrzymanie zapisu świec.

#### Scenario: Nowe połączenie po wygaśnięciu poświadczenia

- **WHEN** moduł pracuje dłużej niż okres ważności poświadczenia i potrzebuje nawiązać nowe
  połączenie z bazą
- **THEN** połączenie zestawia się na odnowionym poświadczeniu
- **AND** zapis świec trwa nieprzerwanie

#### Scenario: Odnowienie nie powiodło się

- **WHEN** odnowienie poświadczenia nie powiodło się
- **THEN** moduł zgłasza błąd wskazujący poświadczenie jako przyczynę
- **AND** MUST NOT raportować się jako zdrowy, dopóki nie odzyska połączenia z bazą

### Requirement: Poświadczenie nie wycieka do logów

Poświadczenie do bazy jest sekretem o krótkiej ważności, ale sekretem. Moduł MUST NOT umieszczać go
w logach, komunikatach błędów ani w odpowiedziach swoich tras — w szczególności tam, gdzie loguje
adres połączenia.

#### Scenario: Błąd połączenia trafia do logu

- **WHEN** nawiązanie połączenia z bazą kończy się błędem, a moduł loguje jego okoliczności
- **THEN** log zawiera host, port i nazwę bazy
- **AND** nie zawiera poświadczenia ani jego fragmentu

### Requirement: Praca bez tożsamości nie wychodzi poza maszynę

Baza lokalna — w kontenerze na maszynie deweloperskiej — MAY być osiągana hasłem niesionym w
`DATABASE_URL`. Ta furtka MUST być ograniczona do pętli zwrotnej: bez skonfigurowanej
tożsamości moduł MUST NOT nawiązać połączenia z hostem innym niż pętla zwrotna i MUST odmówić
startu z taką konfiguracją, wskazując brak tożsamości jako przyczynę. Chroni to przed dwiema
pomyłkami naraz: lokalnym modułem piszącym do produkcji oraz poświadczeniem ambientowym
maszyny (sesją operatora), które uwierzytelniłoby moduł jako kogoś, kim nie jest.

#### Scenario: Baza lokalna na haśle

- **WHEN** moduł startuje bez `DATABASE_USER`, a `DATABASE_URL` wskazuje pętlę zwrotną i
  niesie hasło
- **THEN** moduł łączy się z bazą używając URL dosłownie

#### Scenario: Host zdalny bez tożsamości

- **WHEN** moduł startuje bez `DATABASE_USER`, a `DATABASE_URL` wskazuje hosta spoza pętli
  zwrotnej
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że praca bez tożsamości jest ograniczona do bazy lokalnej

#### Scenario: Narzędzie deweloperskie odmawia wcześniej

- **WHEN** skrypt uruchamiający środowisko lokalne czyta `.env` wskazujący hosta spoza pętli
  zwrotnej
- **THEN** skrypt odmawia startu przed uruchomieniem czegokolwiek
- **AND** komunikat wskazuje `.env` i wymaganie bazy lokalnej

### Requirement: Moduł sam doprowadza bazę do rewizji, dla której powstał

Moduł MUST doprowadzić własną bazę do rewizji schematu, dla której został zbudowany, zanim
zacznie odpowiadać na cokolwiek. Wdrożenie MUST NOT wymagać od operatora osobnego kroku
migracji — wdrożony kod i schemat, którego ten kod potrzebuje, MUST przyjeżdżać razem.

Moduł MUST NOT przyjmować żądań w trakcie migrowania ani MUST NOT zaczynać zbierania
świec. Trasa odpowiadająca, zanim schemat jest gotowy, odpowiada z bazy, której kształtu
nie zna; zbieranie rozpoczęte przed migracją pisze do archiwum, którego kształtu nie zna —
a to drugie zostawia ślad, którego nie da się cofnąć odpowiedzią z błędem.

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

#### Scenario: Zbieranie nie rusza przed migracją

- **WHEN** moduł startuje z migracją do wykonania
- **THEN** nie zapisuje żadnej świecy, zanim migracja się nie skończy

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

Kres MUST być dłuższy niż najdłuższa migracja, jaką ten moduł realnie wykonuje. Archiwum
świec jest największą bazą w tym systemie: migracja przebudowująca indeks na tabeli świec
trwa dłużej niż start procesu, a kres krótszy od niej zamienia wolną migrację w pętlę
restartów, w której nikt nigdy jej nie kończy.

Blokada MUST zostać zwolniona także wtedy, gdy migracja skończyła się błędem.

#### Scenario: Dwie instancje startują naraz

- **WHEN** dwie instancje modułu startują jednocześnie przeciwko jednej bazie wymagającej migracji
- **THEN** migracje wykonuje dokładnie jedna z nich
- **AND** druga zaczyna odpowiadać po tym, jak pierwsza skończyła

#### Scenario: Migracja dłuższa niż start procesu

- **WHEN** migracja na tabeli świec trwa dłużej, niż zajmuje uruchomienie modułu
- **THEN** proces czekający na blokadę czeka na nią do końca, zamiast odmówić w połowie

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
