## Purpose

Brama do konta realnego capital.com: kiedy w ogóle wstaje, na jakim jednym koncie stoi, jakie zlecenia przepuszcza do
dostawcy, czego nie wystawia i co zostaje po każdym zapisie. Jedyne drzwi do pieniędzy, więc granice siedzą tutaj.

## ADDED Requirements

### Requirement: Tryb konta realnego jest jawnym wyborem i działa tylko na serwerze

Moduł MUST pracować na koncie realnym wyłącznie wtedy, gdy jego konfiguracja jawnie wybiera środowisko realne. Adres
bazowy MUST być wtedy dokładnie hostem realnym dostawcy; każdy inny adres, w tym host demo, MUST zatrzymać start. Tryb
realny MUST być dozwolony tylko w procesie wdrożonym na serwer (środowisko produkcyjne i tryb serwera naraz) — na
komputerze operatora i w testach MUST odmówić startu, zanim wyśle jakiekolwiek żądanie.

Publikowane możliwości procesu MUST nazywać środowisko `live`, wyprowadzone z hosta, z którym proces jest związany.

#### Scenario: Tryb realny poza serwerem

- **WHEN** konfiguracja wybiera środowisko realne, a proces nie jest wdrożeniem serwerowym
- **THEN** moduł odmawia startu, nazywając brak serwera jako przyczynę
- **AND** nie wysyła żadnego żądania do dostawcy

#### Scenario: Tryb realny z hostem demo

- **WHEN** konfiguracja wybiera środowisko realne, a adres bazowy jest hostem demo
- **THEN** moduł odmawia startu, nazywając oczekiwany host realny

#### Scenario: Możliwości procesu konta realnego

- **WHEN** konsument odczytuje możliwości procesu w trybie realnym
- **THEN** odpowiedź nazywa środowisko `live`

### Requirement: Proces konta realnego stoi na jednym wskazanym koncie

Konfiguracja trybu realnego MUST wskazywać dokładnie jedno konto. Każde żądanie czytające albo zmieniające rachunek MUST
działać na tym koncie. Żądanie wskazujące inne konto MUST zostać odmówione z nazwą konta, zanim cokolwiek trafi do
dostawcy. Gdy dostawca nie wylicza wskazanego konta, każde żądanie rachunku MUST być odmową nazywającą konto, a MUST
NOT zostać wykonane na koncie, na którym sesja się otworzyła.

#### Scenario: Wołający wskazuje inne konto

- **WHEN** wołający składa zlecenie, wskazując konto inne niż skonfigurowane
- **THEN** moduł odmawia, nazywając konto
- **AND** nic nie trafia do dostawcy

#### Scenario: Skonfigurowanego konta nie ma u dostawcy

- **WHEN** dostawca nie wylicza konta wskazanego w konfiguracji
- **THEN** każde żądanie rachunku jest odmową nazywającą to konto
- **AND** żadne zlecenie nie trafia na inne konto

### Requirement: Bez granic proces konta realnego nie wstaje

Konfiguracja trybu realnego MUST nieść listę dozwolonych instrumentów, a przy każdym z nich największą wielkość jednego
zlecenia w jednostkach instrumentu. Lista pusta, brak listy, instrument bez wielkości albo wielkość niedodatnia MUST
zatrzymać start z nazwą brakującej albo błędnej pozycji. Moduł MUST NOT podstawiać żadnej wartości domyślnej.

#### Scenario: Brak granic

- **WHEN** tryb realny jest wybrany, a lista dozwolonych instrumentów jest pusta albo nieobecna
- **THEN** moduł odmawia startu, nazywając brak granic jako przyczynę

#### Scenario: Instrument bez wielkości

- **WHEN** lista zawiera instrument, przy którym nie ma największej wielkości albo jest ona zerowa lub ujemna
- **THEN** moduł odmawia startu, nazywając ten instrument

### Requirement: Zlecenie poza granicami jest odmową przed dostawcą

Każde zlecenie — rynkowe, z limitem i stop — MUST zostać sprawdzone względem granic, zanim trafi do dostawcy. Zlecenie na
instrument spoza listy MUST być odmową nazywającą instrument. Zlecenie o wielkości większej niż granica instrumentu MUST
być odmową nazywającą wielkość i granicę. Odmowa MUST być odróżnialna od awarii dostępu i od odmowy dostawcy. Zlecenie w
granicach MUST trafić do dostawcy bez zmiany wielkości — moduł MUST NOT przycinać zlecenia do granicy.

#### Scenario: Instrument spoza listy

- **WHEN** wołający składa zlecenie na instrument, którego nie ma na liście dozwolonych
- **THEN** moduł odmawia, nazywając instrument
- **AND** nic nie trafia do dostawcy

#### Scenario: Wielkość ponad granicę

- **WHEN** wołający składa zlecenie o wielkości większej niż granica instrumentu
- **THEN** moduł odmawia, podając wielkość i granicę
- **AND** nie wysyła zlecenia o wielkości przyciętej

#### Scenario: Zlecenie w granicach

- **WHEN** wołający składa zlecenie na instrument z listy, w granicy wielkości
- **THEN** zlecenie trafia do dostawcy z wielkością podaną przez wołającego

### Requirement: Wyjście z rynku nie podlega granicom

Zamknięcie pozycji, zmiana albo usunięcie jej stopów i anulowanie zlecenia oczekującego MUST być dozwolone bez względu na
granice, także dla instrumentu, którego nie ma już na liście. Granica ma ograniczać wejście w ryzyko, a nie wyjście z
niego.

#### Scenario: Zamknięcie pozycji na instrumencie usuniętym z listy

- **WHEN** operator usuwa instrument z listy, a na koncie zostaje otwarta pozycja na nim
- **THEN** zamknięcie tej pozycji trafia do dostawcy jak każde inne

### Requirement: Proces konta realnego nie wystawia rynku, strumienia ani zasilenia

W trybie realnym moduł MUST wystawiać wyłącznie rachunek i wykonanie: listę kont, pozycje, zlecenia oczekujące, ich
składanie, zamykanie, zmianę i anulowanie, warunki instrumentu oraz awaryjne zamknięcie wszystkiego. Katalog
instrumentów, świece, historia, strumień, korekta salda i przełączanie konta aktywnego MUST być nieosiągalne. Archiwum
świec MUST dalej czytać rynek z bramy demo.

#### Scenario: Prośba o świece w procesie konta realnego

- **WHEN** wołający prosi proces konta realnego o świece instrumentu
- **THEN** trasa nie istnieje
- **AND** do dostawcy nie trafia żadne żądanie

#### Scenario: Próba korekty salda konta realnego

- **WHEN** wołający prosi proces konta realnego o korektę salda albo przełączenie konta
- **THEN** trasa nie istnieje

### Requirement: Każdy zapis na koncie realnym zostawia ślad przed i po

Przed wysłaniem do dostawcy każdego żądania zmieniającego konto realne moduł MUST zapisać w logu wiersz z aplikacją
wołającego, kontem, rodzajem zapisu, instrumentem, kierunkiem, wielkością i typem zlecenia; po odpowiedzi MUST zapisać
wiersz ze skutkiem — rozliczonym, odmówionym albo nieznanym. Odmowa z powodu granic MUST zostawić wiersz z nazwą granicy.
Żaden wiersz MUST NOT zawierać poświadczeń wołającego ani dostawcy.

#### Scenario: Zlecenie złożone

- **WHEN** zlecenie w granicach trafia do dostawcy i zostaje rozliczone
- **THEN** log niesie wiersz sprzed wysłania i wiersz ze skutkiem, oba z aplikacją wołającego

#### Scenario: Dostawca nie odpowiada

- **WHEN** żądanie zapisu zostaje wysłane, a odpowiedź nie przychodzi
- **THEN** wiersz po nazywa skutek nieznanym, a MUST NOT nazwać go nieudanym

### Requirement: Operator zamyka wszystko jednym wywołaniem

W trybie realnym moduł MUST wystawiać jedno wywołanie, które zamyka każdą otwartą pozycję i anuluje każde zlecenie
oczekujące skonfigurowanego konta. Odpowiedź MUST nazywać skutek każdej pozycji i każdego zlecenia osobno; niepowodzenie
jednej MUST NOT zatrzymać pozostałych i MUST być nazwane. Konto bez pozycji i zleceń MUST dać odpowiedź udaną, z pustą
listą. Wołający z przeglądarki MUST sięgać w trybie realnym wyłącznie po odczyt rachunku i to wywołanie — żaden inny
zapis. W trybie demo tego wywołania MUST NOT być.

#### Scenario: Zamknięcie wszystkiego

- **WHEN** operator wywołuje zamknięcie wszystkiego, a konto ma dwie pozycje i jedno zlecenie oczekujące
- **THEN** obie pozycje są zamknięte, a zlecenie anulowane
- **AND** odpowiedź nazywa skutek każdego z trzech

#### Scenario: Jedna pozycja nie daje się zamknąć

- **WHEN** dostawca odmawia zamknięcia jednej z pozycji
- **THEN** pozostałe zostają zamknięte
- **AND** odpowiedź nazywa pozycję, której nie zamknięto, i powód

#### Scenario: Przeglądarka próbuje złożyć zlecenie na koncie realnym

- **WHEN** wołający z przeglądarki wysyła zlecenie do procesu konta realnego
- **THEN** moduł odmawia, a nic nie trafia do dostawcy

### Requirement: Klucz procesu konta realnego jest jego własny

Klucz, którym usługi wewnętrzne wołają proces konta realnego, MUST być różny od klucza bramy demo. Wdrożenie, w którym
oba klucze są równe, MUST zostać zatrzymane przed wysłaniem czegokolwiek na serwer. Proces konta realnego MUST być
osiągalny w sieci wewnętrznej wyłącznie dla serwera narzędzi konta realnego i dla krawędzi.

#### Scenario: Ten sam klucz dla demo i konta realnego

- **WHEN** środowisko wdrożenia niesie ten sam klucz dla bramy demo i dla bramy konta realnego
- **THEN** wdrożenie zatrzymuje się, nazywając oba ustawienia
- **AND** nic nie trafia na serwer

#### Scenario: Workbench próbuje sięgnąć bramy konta realnego

- **WHEN** workbench wysyła żądanie pod nazwę procesu konta realnego w sieci wewnętrznej
- **THEN** żądanie nie dochodzi, bo workbench nie jest w jego sieci
