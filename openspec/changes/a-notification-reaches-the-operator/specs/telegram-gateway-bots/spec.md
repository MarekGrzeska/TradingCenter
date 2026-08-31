## Purpose

Zakładanie bota bez otwierania Telegrama: kiedy moduł to potrafi, kiedy uczciwie odmawia, i dlaczego
token, który sam wytworzył, nigdy nie wychodzi na zewnątrz.

## ADDED Requirements

### Requirement: Brak sesji konta jest konfiguracją wspieraną

Zakładanie bota wymaga rozmowy z botem-twórcą Telegrama, a taką rozmowę może prowadzić wyłącznie
konto użytkownika. Moduł MUST startować i MUST wysyłać wiadomości bez skonfigurowanej sesji takiego
konta. Bez niej trasa i narzędzie zakładające bota MUST odmówić, nazywając brakujące ustawienie, i
MUST NOT odpowiadać błędem wewnętrznym.

Ten kształt jest ten sam co u nieobecnego adresu serwera narzędzi w workbenchu: nieobecność
ustawienia jest stanem, przez który przechodzą testy, a nie awarią.

#### Scenario: Wysyłka bez sesji

- **WHEN** moduł nie ma skonfigurowanej sesji konta, a wywołujący prosi o wysłanie wiadomości
- **THEN** moduł MUST wysłać ją normalnie

#### Scenario: Zakładanie bez sesji

- **WHEN** moduł nie ma skonfigurowanej sesji konta, a ktoś prosi o założenie bota
- **THEN** moduł MUST odmówić, nazywając ustawienie, którego brakuje

### Requirement: Moduł zakłada bota wyłącznie na żądanie

Moduł MUST NOT zakładać bota z własnej inicjatywy — ani przy starcie, ani gdy nie ma żadnego, ani
gdy wysyłka się nie udała. Automatyzacja prywatnego konta jest dokładnie tym, za co Telegram konta
ogranicza, więc każda rozmowa z botem-twórcą MUST wynikać z wyraźnego żądania.

#### Scenario: Start bez botów

- **WHEN** moduł startuje i nie zna żadnego bota
- **THEN** MUST NOT zakładać żadnego i MUST działać, odmawiając wysyłki z braku adresata

### Requirement: Sufit liczby botów jest sprawdzany przed rozmową

Telegram ogranicza, ile botów może założyć jedno konto. Moduł MUST odmówić założenia po
przekroczeniu tego sufitu, zanim odezwie się do bota-twórcy, i MUST nazwać sufit w odmowie.

Odmowa po fakcie kosztuje próbę wliczaną w limity konta — a to jest zasób, którego wyczerpanie
dotyka operatora poza tym systemem.

#### Scenario: Sufit osiągnięty

- **WHEN** moduł obsługuje już tyle botów, ile dopuszcza konto, i dostaje żądanie założenia kolejnego
- **THEN** MUST odmówić bez wysyłania czegokolwiek do bota-twórcy

### Requirement: Odpowiedź bez tokenu jest odmową, nie domysłem

Bot-twórca odpowiada zdaniem w języku naturalnym, którego brzmienie nie jest kontraktem. Moduł MUST
uznać założenie za udane wyłącznie wtedy, gdy w odpowiedzi znajdzie token o wymaganym kształcie.
Odpowiedź bez tokenu MUST być odmową oddającą otrzymaną treść w całości.

#### Scenario: Odpowiedź, której moduł nie rozumie

- **WHEN** bot-twórca odpowiada treścią, w której nie ma tokenu
- **THEN** moduł MUST odmówić, oddać tę treść wywołującemu i MUST NOT zapisać żadnego bota

### Requirement: Token bota nie wychodzi z modułu

Żadna trasa, żadne narzędzie i żaden log MUST NOT zawierać tokenu bota — także tego, który moduł
sam przed chwilą uzyskał. Odczyt bota MUST zwracać jego nazwę i identyfikator publiczny.

Pudło w tej regule jest ciche: token w odpowiedzi wygląda jak działająca funkcja, a jest wydanym
sekretem, którym każdy może pisać w imieniu tego systemu.

#### Scenario: Odczyt bota

- **WHEN** wywołujący odczytuje listę botów
- **THEN** odpowiedź MUST NOT zawierać tokenu żadnego z nich

#### Scenario: Świeżo założony bot

- **WHEN** moduł kończy zakładanie bota
- **THEN** odpowiedź MUST potwierdzić założenie bez podawania tokenu, a token MUST NOT trafić do logu
