## Purpose

Publikowany kontrakt archiwum: jak konsument czyta świece, jak subskrybuje bieżące, skąd wie, czego
w archiwum brakuje, i jak zarządza tym, co jest zbierane.
## Requirements
### Requirement: Odczyt świec po zakresie czasu

Moduł MUST udostępniać świece śledzonej pary dla wskazanego przedziału czasu, uporządkowane od
najstarszej, bez powtórzonych znaczników. Odpowiedź MUST nieść rozdzielczość i stronę ceny, żeby
seria była samoopisująca się.

#### Scenario: Odczyt zakresu

- **WHEN** konsument prosi o świece pary w przedziale czasu
- **THEN** dostaje serię uporządkowaną od najstarszej, bez powtórzonych znaczników czasu
- **AND** odpowiedź niesie rozdzielczość i stronę ceny

#### Scenario: Przedział wychodzi poza pokrycie

- **WHEN** żądany przedział wykracza poza to, co archiwum zebrało
- **THEN** odpowiedź zawiera świece z części pokrytej
- **AND** stwierdza, która część przedziału nie jest pokryta

### Requirement: Subskrypcja zaczyna się od snapshotu

Konsument, który najpierw odczytuje historię, a potem subskrybuje, ma między tymi krokami okno, w
którym świeca może mu uciec. Moduł MUST rozpoczynać subskrypcję wiadomością niosącą ostatnie świece
zamknięte oraz świecę w budowie, jeśli taka jest, i dopiero po niej wysyłać zmiany.

#### Scenario: Konsument subskrybuje

- **WHEN** konsument otwiera subskrypcję pary
- **THEN** pierwsza wiadomość niesie ostatnie świece zamknięte oraz świecę w budowie, jeśli istnieje
- **AND** kolejne wiadomości niosą wyłącznie zmiany

#### Scenario: Świeca zamyka się w trakcie subskrypcji

- **WHEN** okres, który był w budowie, zostaje zamknięty
- **THEN** konsument dostaje tę świecę oznaczoną jako zamkniętą
- **AND** znacznik czasu jest ten sam co w świecy w budowie, żeby podmiana nie utworzyła drugiej
  świecy

#### Scenario: Subskrypcja nieśledzonej pary

- **WHEN** konsument subskrybuje parę, która nie jest śledzona
- **THEN** moduł odmawia i stwierdza, że para nie jest śledzona

### Requirement: Świeca w budowie jest oznaczona

Świeca w budowie zmienia się przy każdym kwotowaniu i nie jest utrwalana. Każda wiadomość niosąca
świecę MUST stwierdzać, czy jest ona zamknięta, czy w budowie, żeby konsument mógł je odróżnić.

#### Scenario: Odbiorca rozróżnia świece

- **WHEN** konsument odbiera świecę z subskrypcji
- **THEN** wiadomość stwierdza, czy świeca jest zamknięta, czy w budowie

### Requirement: Pokrycie jest odczytywalne

Konsument MUST móc dowiedzieć się, jaki przedział czasu archiwum pokrywa dla danej pary, zanim
zbuduje na tych danych wykres albo backtest.

#### Scenario: Odczyt pokrycia

- **WHEN** konsument pyta o pokrycie pary
- **THEN** dostaje najstarszy i najnowszy zweryfikowany znacznik czasu
- **AND** informację, czy najstarsza granica wynika z końca historii u providera

### Requirement: Śledzone pary są zarządzalne przez kontrakt

Moduł MUST udostępniać przez swój kontrakt dodanie pary do śledzonych, skasowanie jej oraz odczyt
listy wraz ze stanem każdej pary. Konfiguracja MUST NOT wymagać dostępu do plików ani restartu.
Dodanie MUST przyjmować wiele par naraz wraz z jednym momentem, od którego historia ma zostać
pokryta, i MUST odpowiadać wynikiem osobno dla każdej pary — odmowa dla jednej MUST NOT przekreślać
pozostałych. Żądanie bez podanego momentu początku MUST pozostać ważne i MUST znaczyć domyślną
głębokość z konfiguracji, żeby konsument sprzed tej zmiany działał dalej.

Odczyt listy MUST nieść dla każdej pary liczbę zebranych świec oraz szacowaną objętość, jaką
zajmują. Konsument MUST NOT musieć wyliczać żadnej z tych liczb sam: liczby świec nie da się
wyprowadzić z zakresu dat, a mnożnik objętości należy do modułu, który dane przechowuje, a nie do
tego, który je pokazuje.

Skasowanie pary przez kontrakt MUST zatrzymać zbieranie i usunąć zebrane dane tej pary. Odpowiedź
MUST nieść liczbę usuniętych świec, bo to jedyny moment, w którym konsument może się dowiedzieć, ile
danych właśnie zniknęło.

#### Scenario: Dodanie pary

- **WHEN** konsument dodaje parę przez kontrakt
- **THEN** para zostaje zapisana jako śledzona, a odpowiedź to potwierdza

#### Scenario: Odczyt listy z objętością danych

- **WHEN** konsument odczytuje listę śledzonych par
- **THEN** każda para niesie liczbę zebranych świec i szacowaną objętość w bajtach
- **AND** obie liczby dotyczą wyłącznie tej pary, a nie całego archiwum

#### Scenario: Dodanie wielu par jednym żądaniem

- **WHEN** konsument dodaje kilka par wraz z momentem początku
- **THEN** wszystkie zostają zapisane jako śledzone
- **AND** odpowiedź niesie identyfikator zlecenia dociągnięcia historii dla tych par

#### Scenario: Jedna z par zostaje odrzucona

- **WHEN** wśród dodawanych par jedna zostaje odrzucona, a pozostałe nie
- **THEN** odpowiedź stwierdza to osobno dla każdej pary, nazywając powód odmowy
- **AND** pary przyjęte są śledzone

#### Scenario: Żądanie bez momentu początku

- **WHEN** konsument dodaje parę bez podania momentu początku
- **THEN** moduł przyjmuje żądanie
- **AND** historia jest dociągana do domyślnej głębokości z konfiguracji

#### Scenario: Dodanie pary nieznanej providerowi

- **WHEN** konsument dodaje parę, której symbolu provider nie zna
- **THEN** moduł odmawia i nazywa symbol jako nieznaleziony

#### Scenario: Usunięcie pary

- **WHEN** konsument kasuje parę przez kontrakt
- **THEN** zbieranie ustaje, a świece i pokrycie tej pary przestają istnieć
- **AND** odpowiedź niesie liczbę usuniętych świec

#### Scenario: Skasowanie pary, która nie jest śledzona

- **WHEN** konsument kasuje parę, której moduł nie zna
- **THEN** moduł odmawia i nazywa parę jako nieśledzoną
- **AND** MUST NOT kasować niczego innego

### Requirement: Odpowiedzi nazywają swoje porażki

Każda porażka MUST być opisana w sposób, który da się pokazać operatorowi: nieznany symbol,
nieobsługiwana rozdzielczość, para nieśledzona, źródło nieosiągalne. Odpowiedź MUST NOT być surowym
błędem bazy ani sieci i MUST NOT nieść poświadczeń żadnego systemu.

#### Scenario: Baza nieosiągalna

- **WHEN** archiwum nie może sięgnąć do własnej bazy
- **THEN** konsument dostaje błąd mówiący, że archiwum jest niedostępne, a nie pustą serię świec

#### Scenario: Nieobsługiwana rozdzielczość

- **WHEN** konsument prosi o rozdzielczość spoza obsługiwanych
- **THEN** moduł odmawia i wylicza rozdzielczości, które obsługuje

### Requirement: Kontrakt wycenia zlecenie przed jego złożeniem

Moduł MUST udostępniać wycenę zlecenia: dla wskazanych par i momentu początku odpowiada przyciętym
zakresem, szacowaną liczbą świec i szacowanym rozmiarem, osobno dla każdej pary i w sumie. Wycena
MUST NOT mieć skutków ubocznych — żadna para nie zaczyna być śledzona, żadne zlecenie nie powstaje.

#### Scenario: Odczyt wyceny

- **WHEN** konsument prosi o wycenę dla trzech par i momentu początku
- **THEN** dostaje dla każdej pary przycięty zakres, szacowaną liczbę świec i szacowany rozmiar
- **AND** sumę tych wartości

#### Scenario: Wycena nie ma skutków ubocznych

- **WHEN** konsument prosi o wycenę
- **THEN** lista śledzonych par pozostaje niezmieniona
- **AND** żadne zlecenie nie zostaje utworzone

#### Scenario: Wycena pary nieznanej providerowi

- **WHEN** wycena dotyczy pary, której symbolu provider nie zna
- **THEN** odpowiedź nazywa tę parę jako nieznaną
- **AND** wycenia pozostałe

### Requirement: Zlecenia dociągania są odczytywalne przez kontrakt

Moduł MUST udostępniać odczyt zleceń dociągania — listę oraz pojedyncze zlecenie — wraz ze stanem,
postępem liczonym z kawałków, liczbą zapisanych świec, pokrytym zakresem oraz przyczynami porażek.
Odczyt MUST dać się zawęzić do jednej pary, bo tak patrzy na to operator. Odpowiedź MUST rozróżniać
zlecenie trwające, zakończone powodzeniem, zakończone częściowo, zakończone porażką oraz przerwane.

#### Scenario: Odczyt zleceń pary

- **WHEN** konsument prosi o zlecenia dla wskazanego symbolu i rozdzielczości
- **THEN** dostaje je od najnowszego, każde ze stanem, postępem i liczbą zapisanych świec

#### Scenario: Odczyt zlecenia w toku

- **WHEN** konsument odczytuje trwające zlecenie
- **THEN** dostaje liczbę kawałków ukończonych i wszystkich oraz parę właśnie obsługiwaną

#### Scenario: Odczyt zlecenia zakończonego częściowo

- **WHEN** konsument odczytuje zlecenie, w którym część kawałków zawiodła
- **THEN** stan mówi o pokryciu częściowym
- **AND** odpowiedź wylicza nieudane kawałki wraz z nazwaną przyczyną każdego

### Requirement: Nieudane zlecenie da się ponowić przez kontrakt

Moduł MUST udostępniać ponowienie zlecenia zakończonego częściowo, porażką albo przerwanego.
Ponowienie MUST obejmować wyłącznie kawałki, które nie zostały pokryte, i MUST odpowiedzieć tym, co
zostanie ponowione. Ponowienie zlecenia, w którym nic nie zawiodło, MUST być odmówione z nazwanym
powodem, zamiast wykonywać pracę raz jeszcze.

#### Scenario: Ponowienie nieudanego zlecenia

- **WHEN** konsument ponawia zlecenie z nieudanymi kawałkami
- **THEN** moduł wznawia wyłącznie te kawałki
- **AND** odpowiedź wymienia pary i zakresy objęte ponowieniem

#### Scenario: Ponowienie zlecenia bez porażek

- **WHEN** konsument ponawia zlecenie zakończone w pełni powodzeniem
- **THEN** moduł odmawia i stwierdza, że nie ma czego ponawiać

#### Scenario: Ponowienie zlecenia nieistniejącego

- **WHEN** konsument ponawia zlecenie, którego moduł nie zna
- **THEN** odpowiedź stwierdza, że takiego zlecenia nie ma

### Requirement: Odnotowane skasowania są odczytywalne przez kontrakt

Konsument MUST móc odczytać, które pary zostały skasowane, kiedy, ile świec przy tym zniknęło i jaki
zakres czasu obejmowały. Odczyt MUST być zawężalny do pary, tak samo jak odczyt historii zleceń —
operator patrzący na jeden instrument pyta o jego historię, nie o cudzą.

#### Scenario: Odczyt skasowań

- **WHEN** konsument odczytuje odnotowane skasowania
- **THEN** dla każdego dostaje parę, moment skasowania, liczbę usuniętych świec i zakres czasu,
  który obejmowały

#### Scenario: Odczyt zawężony do pary

- **WHEN** konsument pyta o skasowania jednej pary
- **THEN** dostaje wyłącznie skasowania tej pary

#### Scenario: Nic nie było kasowane

- **WHEN** konsument odczytuje skasowania, a żadne nie miało miejsca
- **THEN** dostaje pustą odpowiedź, a nie porażkę

### Requirement: Katalog instrumentów jest osiągalny przez ten moduł

`capital-gateway` jest niepubliczny — jedynym wywołującym, jaki może mieć skonfigurowane do niego
poświadczenie, jest proces po stronie serwera. Moduł MUST udostępniać wyszukiwanie instrumentów,
listę klas aktywów i katalog instrumentów jako trasy proxujące do gatewaya, tak by `terminal` mógł
osiągnąć te dane bez własnego, bezpośredniego połączenia z gatewayem.

Odpowiedź MUST być tym samym kształtem danych, jaki zwraca gateway — moduł nie interpretuje ani nie
wzbogaca katalogu, wyłącznie go przekazuje.

#### Scenario: Terminal wyszukuje instrument

- **WHEN** konsument prosi ten moduł o wyszukanie instrumentów po frazie
- **THEN** moduł zwraca wynik otrzymany od gatewaya, bez zmiany kształtu

#### Scenario: Terminal pyta o klasy aktywów

- **WHEN** konsument prosi ten moduł o listę klas aktywów
- **THEN** moduł zwraca listę otrzymaną od gatewaya

### Requirement: Odmowa gatewaya jest przezroczysta dla konsumenta

Gdy gateway odmawia lub jest nieosiągalny, moduł MUST NOT udawać pustego wyniku wyszukiwania —
odmowa i brak wyników muszą być rozróżnialne przez wywołującego proxy.

#### Scenario: Gateway odrzuca żądanie proxy

- **WHEN** gateway odrzuca żądanie o katalog instrumentów
- **THEN** moduł zwraca odpowiedź, którą konsument odróżni od pustego wyniku wyszukiwania
