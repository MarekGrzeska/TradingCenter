## MODIFIED Requirements

### Requirement: Śledzone pary są zarządzalne przez kontrakt

Moduł MUST udostępniać przez swój kontrakt dodanie pary do śledzonych, usunięcie jej oraz odczyt
listy wraz ze stanem każdej pary. Konfiguracja MUST NOT wymagać dostępu do plików ani restartu.
Dodanie MUST przyjmować wiele par naraz wraz z jednym momentem, od którego historia ma zostać
pokryta, i MUST odpowiadać wynikiem osobno dla każdej pary — odmowa dla jednej MUST NOT przekreślać
pozostałych. Żądanie bez podanego momentu początku MUST pozostać ważne i MUST znaczyć domyślną
głębokość z konfiguracji, żeby konsument sprzed tej zmiany działał dalej.

#### Scenario: Dodanie pary

- **WHEN** konsument dodaje parę przez kontrakt
- **THEN** para zostaje zapisana jako śledzona, a odpowiedź to potwierdza

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

- **WHEN** konsument usuwa parę ze śledzonych
- **THEN** zbieranie ustaje, a zebrane świece pozostają odczytywalne

## ADDED Requirements

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
