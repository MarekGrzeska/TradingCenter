# telegram-gateway-upstream-access Specification

## Purpose
Dwie powierzchnie Telegrama, którymi ta brama się posługuje, i jedna droga do każdej z nich — wraz z
regułą, która nie pozwala im się zamienić rolami.
## Requirements
### Requirement: Wysyłka idzie kanałem bota, nigdy kontem użytkownika

Moduł MUST wysyłać wiadomości wyłącznie tożsamością bota. Nawet gdy sesja konta użytkownika jest
skonfigurowana, MUST NOT być użyta do wysłania powiadomienia.

Powiadomienie wysłane kontem operatora jest nieodróżnialne od tego, co operator napisał sam, a każda
taka wysyłka obciąża limity prywatnego konta — czyli awaria zbiórki staje się ryzykiem dla konta.

#### Scenario: Sesja konta jest skonfigurowana

- **WHEN** moduł ma skonfigurowaną sesję konta i wysyła powiadomienie
- **THEN** MUST użyć tożsamości bota

### Requirement: Sesja konta służy jednej rzeczy

Sesja konta użytkownika MUST być używana wyłącznie do zalogowania i wylogowania tego konta oraz do
rozmowy z botem-twórcą w celu założenia, skasowania lub zrotowania tokenu bota. MUST NOT służyć do
czytania cudzych rozmów, dołączania do grup, wysyłania komukolwiek innemu niż bot-twórca ani do
czegokolwiek, o co ta brama nie została poproszona.

Konto jest dedykowane botom, nie prywatne — ale jego sesja dalej pozwala pisać jako boty, którym
operator ufa, więc wąski zakres jest tak samo ważny jak przy koncie prywatnym.

#### Scenario: Zakres użycia sesji

- **WHEN** moduł posługuje się sesją konta
- **THEN** MUST to być logowanie, wylogowanie albo rozmowa z botem-twórcą i niczym innym

### Requirement: Sekret nie jest częścią adresu ani logu

Token bota, dane identyfikujące aplikację Telegrama, sekret sesji, klucz szyfrujący sesję, kod
logowania i hasło dwuetapowe MUST NOT pojawiać się w adresie zapisywanym w logu, w treści logu ani w
żadnej odpowiedzi modułu.

Kanał bota przyjmuje token jako część ścieżki żądania, więc adres tego żądania **jest** sekretem —
zalogowanie go przy awarii jest najprostszym sposobem, żeby go stracić.

#### Scenario: Nieudane żądanie do Telegrama

- **WHEN** żądanie do Telegrama kończy się błędem i moduł je loguje
- **THEN** wpis MUST NOT zawierać tokenu w żadnej postaci

#### Scenario: Nieudane logowanie

- **WHEN** logowanie konta kończy się odmową Telegrama i moduł ją loguje
- **THEN** wpis MUST NOT zawierać kodu, hasła ani sesji

### Requirement: Brak sesji konta nie blokuje startu

Moduł MUST wstać i serwować bez skonfigurowanej sesji konta użytkownika. MUST NOT traktować jej
braku jako błędu konfiguracji.

#### Scenario: Start bez sesji

- **WHEN** moduł startuje bez sesji konta
- **THEN** MUST zacząć serwować i MUST powiedzieć przez trasę stanu, że zakładanie botów jest niedostępne

