## MODIFIED Requirements

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
