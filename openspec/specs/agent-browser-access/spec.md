# agent-browser-access Specification

## Purpose

Opisuje, na jakich warunkach moduł agenta przyjmuje wywołanie z przeglądarki: czym
przedstawia się operator, skąd wolno takiemu wywołaniu przyjść, i dlaczego cudzej rozmowy
nie da się odczytać, znając jej identyfikator.

## Requirements

### Requirement: Rozmowa należy do operatora, który ją prowadził

Sesja MUST być przypisana do tożsamości, która ją utworzyła. Odczyt sesji, jej transkryptu
i jej zużycia MUST być ograniczony do tej tożsamości; wywołanie od kogo innego MUST być
odrzucone, także wtedy, gdy niesie poprawny identyfikator sesji. Identyfikator sesji MUST
NOT być jedyną rzeczą, jaka dzieli obcego od cudzej rozmowy.

Odmowa dostępu do cudzej sesji MUST być nieodróżnialna od odpowiedzi o sesji nieistniejącej
— różnica między nimi mówi obcemu, że rozmowa istnieje, i pozwala wyliczyć, ile ich jest.

#### Scenario: Cudza sesja

- **WHEN** wywołanie od jednej tożsamości wskazuje sesję należącą do innej
- **THEN** moduł odmawia
- **AND** odpowiedź jest taka sama jak dla sesji, która nie istnieje

#### Scenario: Lista rozmów

- **WHEN** operator prosi o listę swoich rozmów
- **THEN** dostaje wyłącznie sesje własnej tożsamości

### Requirement: Moduł nie bierze na wiarę warstwy przed sobą

Moduł MUST dać się skonfigurować tak, że wymaga tożsamości ustalonej przez warstwę
uwierzytelniającą stojącą przed nim, i w tej konfiguracji MUST odmówić każdego wywołania,
któremu tożsamości brakuje. Moduł MUST NOT zakładać, że warstwa przed nim działa — jedna
pomyłka w konfiguracji platformy otworzyłaby inaczej płatne wywołania modelu każdemu, kto
zna adres.

Konfiguracja bez tego wymagania MUST być możliwa i MUST być trybem pracy lokalnej, gdzie
przed modułem nie stoi nic i nie ma tożsamości do ustalenia.

#### Scenario: Wywołanie bez ustalonej tożsamości

- **WHEN** moduł skonfigurowany jako stojący za warstwą uwierzytelniającą dostaje wywołanie
  bez tożsamości
- **THEN** odmawia przed dotknięciem modelu
- **AND** komunikat wskazuje brak tożsamości jako przyczynę

#### Scenario: Praca lokalna

- **WHEN** moduł startuje bez wymagania tożsamości
- **THEN** przyjmuje wywołania i przypisuje je do tożsamości lokalnej

### Requirement: Poświadczenie nie wędruje w adresie

Poświadczenie MUST być przekazywane tak, by nie trafiało do adresu wywołania — także przy
wywołaniu, którego odpowiedź jest strumieniem. Adres wędruje do logów serwera, do historii
przeglądarki i do nagłówka `Referer`, i zostaje tam długo po tym, jak połączenie się
skończyło.

#### Scenario: Strumień odpowiedzi zestawiany z przeglądarki

- **WHEN** terminal prosi o odpowiedź agenta i odbiera ją strumieniem
- **THEN** poświadczenie jedzie poza adresem wywołania

### Requirement: Wywołanie z przeglądarki przychodzi z uznanego adresu

Terminal i moduł agenta stoją pod różnymi adresami, więc przeglądarka pyta o zgodę, zanim
wyśle wywołanie niosące poświadczenie. Moduł MUST uznawać wywołania pochodzące z adresów
skonfigurowanych jako dozwolone i MUST NOT uznawać wywołań z pozostałych. Lista dozwolonych
adresów MUST być konfiguracją, nie wartością wpisaną w kod, i MUST NOT być otwarta na
dowolny adres.

Zapytanie wstępne przeglądarki poprzedza wysłanie poświadczenia i samo go nie niesie. MUST
zostać obsłużone, bo inaczej żadne wywołanie z przeglądarki nie dojdzie do skutku —
niezależnie od tego, jak poprawną tożsamość ma operator.

#### Scenario: Wywołanie z adresu terminala

- **WHEN** przeglądarka pyta, czy wolno wysłać wywołanie z adresu terminala
- **THEN** moduł odpowiada, że wolno, wraz z nagłówkiem niosącym poświadczenie

#### Scenario: Wywołanie z adresu spoza listy

- **WHEN** przeglądarka pyta o zgodę dla adresu, którego nie ma w konfiguracji
- **THEN** moduł nie potwierdza zgody

#### Scenario: Zapytanie wstępne bez poświadczenia

- **WHEN** przychodzi zapytanie wstępne przeglądarki, które z natury nie niesie poświadczenia
- **THEN** zostaje obsłużone i nie kończy się odmową z powodu braku poświadczenia

### Requirement: Poświadczenia nie trafiają do logów ani do odpowiedzi

Moduł MUST NOT umieszczać w logach, komunikatach błędów ani odpowiedziach poświadczenia
wołającego ani poświadczenia, którym sam przedstawia się dostawcy modeli. Odmowa MUST być
zalogowana z przyczyną, bez cytowania poświadczenia, którego dotyczy.

#### Scenario: Odmowa trafia do logu

- **WHEN** moduł odmawia wywołania z powodu poświadczenia i loguje to zdarzenie
- **THEN** log niesie przyczynę odmowy
- **AND** nie niesie poświadczenia ani jego fragmentu
