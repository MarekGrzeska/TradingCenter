# market-data-browser-access Specification

## Purpose
Opisuje, na jakich warunkach archiwum przyjmuje wywołanie pochodzące z przeglądarki — czym
przedstawia się konsument na trasach HTTP, czym zestawia połączenie strumieniowe, którego nagłówka
nie da się ustawić, i skąd wolno takie wywołanie przyjść.
## Requirements
### Requirement: Strumień zestawia się poświadczeniem jednorazowym

Konsument z przeglądarki nie może dołożyć nagłówka do połączenia strumieniowego, a poświadczenie
umieszczone w adresie trafia do logów serwera i zostaje tam po zakończeniu połączenia. Moduł MUST
wystawiać trasę wydającą poświadczenie jednorazowe przeznaczone wyłącznie do zestawienia jednego
połączenia strumieniowego.

Poświadczenie jednorazowe MUST być nieodgadywalne, MUST tracić ważność po krótkim czasie liczonym
w sekundach i MUST przestać być ważne w chwili pierwszego użycia. Moduł MUST NOT przyjmować go
powtórnie, nawet gdy nie minął jeszcze czas jego ważności.

#### Scenario: Konsument prosi o poświadczenie jednorazowe

- **WHEN** uprawniony konsument prosi o poświadczenie do zestawienia strumienia
- **THEN** dostaje poświadczenie wraz z informacją, jak długo jest ważne

#### Scenario: To samo poświadczenie użyte dwa razy

- **WHEN** konsument zestawia połączenie poświadczeniem, którym zestawiono już wcześniej inne
- **THEN** moduł odmawia zestawienia
- **AND** pierwsze połączenie nie zostaje przerwane

#### Scenario: Poświadczenie przeleżało

- **WHEN** konsument zestawia połączenie poświadczeniem, którego czas ważności minął
- **THEN** moduł odmawia zestawienia

### Requirement: Bez ważnego poświadczenia strumień się nie zestawia

Trasa strumienia MUST odmówić zestawienia połączenia, gdy poświadczenia jednorazowego nie ma, jest
nieznane, wygasło lub zostało już zużyte. Odmowa MUST nastąpić przed przyjęciem połączenia
i konsument MUST NOT zostać zapisany do rozgłaszania.

Odmowa z powodu poświadczenia MUST być odróżnialna od odmowy z powodu pary, która nie jest
śledzona — są to dwie różne przyczyny i konsument reaguje na nie inaczej: jedną naprawia ponowne
uwierzytelnienie, drugiej nie naprawi nic poza włączeniem zbierania pary.

#### Scenario: Zestawienie bez poświadczenia

- **WHEN** konsument zestawia połączenie strumieniowe bez poświadczenia jednorazowego
- **THEN** moduł odmawia przed przyjęciem połączenia
- **AND** nie zapisuje konsumenta do rozgłaszania

#### Scenario: Poświadczenie nieznane modułowi

- **WHEN** konsument zestawia połączenie poświadczeniem, którego moduł nigdy nie wydał
- **THEN** moduł odmawia
- **AND** odpowiedź nie rozróżnia poświadczenia nieistniejącego od wygasłego

#### Scenario: Dwie różne przyczyny odmowy

- **WHEN** konsument zestawia połączenie z ważnym poświadczeniem, ale dla pary, która nie jest
  śledzona
- **THEN** moduł odmawia, podając nieśledzoną parę jako przyczynę
- **AND** przyczyna ta jest odróżnialna od odmowy z powodu poświadczenia

### Requirement: Poświadczenie wydaje się wyłącznie temu, kogo platforma uwierzytelniła

Trasa wydająca poświadczenia jednorazowe jest wytwórnią kluczy do strumienia — wystawiona bez
ochrony otwiera strumień każdemu. Moduł MUST dać się skonfigurować tak, że wymaga tożsamości
ustalonej przez warstwę uwierzytelniającą stojącą przed nim, i w tej konfiguracji MUST odmówić
wydania poświadczenia, gdy tożsamości nie ma.

Moduł MUST NOT zakładać, że warstwa przed nim działa. Wyłączenie jej — pomyłką w konfiguracji
platformy albo zmianą, której nikt nie zauważył — MUST skutkować odmową wydawania poświadczeń,
a nie cichym wydawaniem ich każdemu.

#### Scenario: Żądanie bez ustalonej tożsamości

- **WHEN** moduł skonfigurowany jako stojący za warstwą uwierzytelniającą dostaje żądanie
  o poświadczenie bez ustalonej tożsamości
- **THEN** odmawia wydania
- **AND** nie tworzy żadnego poświadczenia

#### Scenario: Konfiguracja lokalna

- **WHEN** moduł nie jest skonfigurowany jako stojący za warstwą uwierzytelniającą
- **THEN** wydaje poświadczenie jednorazowe na żądanie
- **AND** trasa strumienia nadal wymaga tego poświadczenia

### Requirement: Wywołanie z przeglądarki przychodzi z uznanego adresu

Interfejs operatora i archiwum stoją pod różnymi adresami, więc przeglądarka pyta o zgodę, zanim
wyśle wywołanie niosące poświadczenie. Moduł MUST uznawać wywołania pochodzące z adresów
skonfigurowanych jako dozwolone i MUST NOT uznawać wywołań z pozostałych. Lista dozwolonych adresów
MUST być konfiguracją, nie wartością wpisaną w kod, i MUST NOT być otwarta na dowolny adres.

Zapytanie wstępne przeglądarki poprzedza wysłanie poświadczenia i samo go nie niesie. MUST zostać
obsłużone, bo inaczej żadne wywołanie z przeglądarki nie dojdzie do skutku — niezależnie od tego,
czy konsument ma poprawną tożsamość.

#### Scenario: Wywołanie z adresu interfejsu operatora

- **WHEN** przeglądarka pyta, czy wolno wysłać wywołanie z adresu interfejsu operatora
- **THEN** moduł odpowiada, że wolno, wraz z nagłówkiem niosącym poświadczenie

#### Scenario: Wywołanie z adresu spoza listy

- **WHEN** przeglądarka pyta o zgodę dla adresu, którego nie ma w konfiguracji
- **THEN** moduł nie potwierdza zgody

#### Scenario: Zapytanie wstępne bez poświadczenia

- **WHEN** przychodzi zapytanie wstępne przeglądarki, które z natury nie niesie poświadczenia
- **THEN** zostaje obsłużone i nie kończy się odmową z powodu braku poświadczenia

### Requirement: Poświadczenia nie trafiają do logów ani do odpowiedzi

Moduł MUST NOT umieszczać w logach, komunikatach błędów ani odpowiedziach poświadczenia
konsumenta ani poświadczenia jednorazowego. Odmowa MUST być zalogowana z przyczyną, bez cytowania
poświadczenia, którego dotyczy.

#### Scenario: Odmowa zestawienia trafia do logu

- **WHEN** moduł odmawia zestawienia strumienia z powodu poświadczenia i loguje to zdarzenie
- **THEN** log niesie przyczynę odmowy
- **AND** nie niesie poświadczenia ani jego fragmentu

#### Scenario: Wydane poświadczenie w logu

- **WHEN** moduł wydaje poświadczenie jednorazowe i loguje to zdarzenie
- **THEN** log stwierdza fakt wydania
- **AND** nie niesie wydanej wartości

