# agent-database-connection Specification

## Purpose

Opisuje, na jakich warunkach moduł agenta łączy się ze swoją bazą: czym się przedstawia
wobec bazy zdalnej, kiedy wolno mu użyć hasła, i kiedy MUST odmówić pracy zamiast działać
w konfiguracji, która wygląda na działającą.

## Requirements

### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Wobec bazy zdalnej moduł MUST uwierzytelniać się poświadczeniem wystawianym dla jego
tożsamości i pobieranym przy nawiązywaniu połączenia; trwałe hasło do bazy zdalnej MUST NOT
być wymagane do pracy modułu ani przechowywane w jego konfiguracji. Tryb tożsamości wybiera
skonfigurowana nazwa roli; konfiguracja trybu tożsamości, której adres bazy niesie własne
poświadczenie, MUST być odrzucona przy starcie.

Poświadczenie ma ważność krótszą niż czas pracy modułu i MUST być odnawiane tak, by
połączenie nawiązywane po jego wygaśnięciu zestawiało się poprawnie.

#### Scenario: Poświadczenia nie da się uzyskać

- **WHEN** moduł startuje w trybie tożsamości, a wystawca poświadczeń jest nieosiągalny lub
  odmawia
- **THEN** moduł odmawia startu, wskazując uzyskanie poświadczenia jako przyczynę
- **AND** MUST NOT sięgać po zapasowe hasło

#### Scenario: Poświadczenie w adresie obok tożsamości

- **WHEN** moduł startuje w trybie tożsamości, a adres bazy niesie nazwę użytkownika lub
  hasło
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że poświadczenie z adresu nie byłoby użyte

#### Scenario: Nowe połączenie po wygaśnięciu poświadczenia

- **WHEN** moduł pracuje dłużej niż okres ważności poświadczenia i potrzebuje nowego
  połączenia
- **THEN** połączenie zestawia się na odnowionym poświadczeniu

### Requirement: Połączenie z bazą zdalną jest szyfrowane

Gdy baza stoi poza maszyną modułu, ruch do niej przechodzi przez sieć, której moduł nie
kontroluje — takie połączenie MUST być wyłącznie szyfrowane. Konfiguracja wskazująca hosta
zdalnego, która szyfrowania nie wymusza, MUST być odrzucona przy starcie, a moduł MUST NOT
obniżyć wymagania, gdy połączenie szyfrowane się nie uda. Baza na pętli zwrotnej tej samej
maszyny MAY być osiągana bez szyfrowania.

#### Scenario: Konfiguracja nie wymusza szyfrowania

- **WHEN** moduł startuje w trybie tożsamości z adresem hosta zdalnego, który nie wymaga
  szyfrowania
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje konfigurację połączenia jako przyczynę

#### Scenario: Baza lokalna bez szyfrowania

- **WHEN** moduł startuje bez skonfigurowanej tożsamości, a adres wskazuje pętlę zwrotną bez
  wymogu szyfrowania
- **THEN** moduł startuje i łączy się z bazą

### Requirement: Praca bez tożsamości nie wychodzi poza maszynę

Baza lokalna — w kontenerze na maszynie deweloperskiej — MAY być osiągana hasłem niesionym
w adresie. Ta furtka MUST być ograniczona do pętli zwrotnej: bez skonfigurowanej tożsamości
moduł MUST NOT nawiązać połączenia z hostem innym niż pętla zwrotna i MUST odmówić startu z
taką konfiguracją. Chroni to przed lokalnym modułem piszącym do produkcji i przed
poświadczeniem ambientowym maszyny, które uwierzytelniłoby moduł jako kogoś, kim nie jest.

#### Scenario: Host zdalny bez tożsamości

- **WHEN** moduł startuje bez skonfigurowanej roli, a adres wskazuje hosta spoza pętli
  zwrotnej
- **THEN** moduł odmawia startu
- **AND** komunikat wskazuje, że praca bez tożsamości jest ograniczona do bazy lokalnej

#### Scenario: Narzędzie deweloperskie odmawia wcześniej

- **WHEN** skrypt uruchamiający środowisko lokalne czyta konfigurację wskazującą hosta spoza
  pętli zwrotnej
- **THEN** skrypt odmawia startu przed uruchomieniem czegokolwiek

### Requirement: Moduł nie dzieli bazy z innym modułem

Baza modułu agenta MUST być odrębna od bazy archiwum świec: moduł MUST NOT czytać ani pisać
w tabelach należących do innego modułu, a jego migracje MUST NOT dotykać niczego poza jego
własną bazą. Dwa moduły w jednej bazie logicznej nie dają się osobno wdrożyć, przywrócić z
kopii ani usunąć, a to właśnie te trzy rzeczy czynią moduł niezależnym.

#### Scenario: Migracje modułu

- **WHEN** migracje modułu agenta zostają wykonane
- **THEN** dotyczą wyłącznie jego własnej bazy
- **AND** żadna tabela archiwum świec nie zostaje zmieniona

#### Scenario: Poświadczenie nie sięga dalej

- **WHEN** moduł agenta łączy się w trybie tożsamości
- **THEN** jego rola MUST NOT mieć dostępu do bazy archiwum świec

### Requirement: Poświadczenie nie wycieka do logów

Poświadczenie do bazy jest sekretem o krótkiej ważności, ale sekretem. Moduł MUST NOT
umieszczać go w logach, komunikatach błędów ani w odpowiedziach swoich tras — w
szczególności tam, gdzie loguje adres połączenia.

#### Scenario: Błąd połączenia trafia do logu

- **WHEN** nawiązanie połączenia z bazą kończy się błędem, a moduł loguje jego okoliczności
- **THEN** log zawiera host, port i nazwę bazy
- **AND** nie zawiera poświadczenia ani jego fragmentu

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
