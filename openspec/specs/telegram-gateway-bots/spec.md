# telegram-gateway-bots Specification

## Purpose
Zakładanie bota bez otwierania Telegrama: kiedy moduł to potrafi, kiedy uczciwie odmawia, i dlaczego
token, który sam wytworzył, nigdy nie wychodzi na zewnątrz.
## Requirements
### Requirement: Brak sesji konta jest konfiguracją wspieraną

Zakładanie bota wymaga rozmowy z botem-twórcą Telegrama, a taką rozmowę może prowadzić wyłącznie
konto użytkownika, zalogowane przez `telegram-gateway-account`. Moduł MUST startować i MUST wysyłać
wiadomości bez zalogowanego konta. Bez niego trasa zakładająca, kasująca i rotująca bota MUST
odmówić, mówiąc, że konto nie jest zalogowane, i MUST NOT odpowiadać błędem wewnętrznym. Wklejenie
tokenu bota MUST działać bez konta.

Ten kształt jest ten sam co u nieobecnego adresu serwera narzędzi w workbenchu: nieobecność
konta jest stanem, przez który przechodzą testy, a nie awarią.

#### Scenario: Wysyłka bez sesji

- **WHEN** moduł nie ma zalogowanego konta, a wywołujący prosi o wysłanie wiadomości
- **THEN** moduł MUST wysłać ją normalnie

#### Scenario: Zakładanie bez sesji

- **WHEN** moduł nie ma zalogowanego konta, a ktoś prosi o założenie bota
- **THEN** moduł MUST odmówić, mówiąc, że konto trzeba najpierw zalogować

### Requirement: Moduł zakłada bota wyłącznie na żądanie

Moduł MUST NOT zakładać, kasować ani rotować bota z własnej inicjatywy — ani przy starcie, ani gdy
nie ma żadnego, ani gdy wysyłka się nie udała. Automatyzacja konta jest dokładnie tym, za co
Telegram konta ogranicza, więc każda rozmowa z botem-twórcą MUST wynikać z wyraźnego żądania.

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

### Requirement: Rotacja tokenu zachowuje wiązania

Moduł MUST pozwolić operatorowi zrotować token bota, którego właścicielem jest zalogowane konto,
rozmową z botem-twórcą. Nowy token MUST zastąpić stary w bazie, a adresaci tego bota MUST dalej
odbierać bez ponownego tapnięcia. Stary token MUST przestać działać, zanim moduł potwierdzi rotację.

#### Scenario: Rotacja przy związanym adresacie

- **WHEN** operator rotuje token bota, który ma odbierającego adresata, a potem przychodzi wiadomość do tego adresata
- **THEN** wiadomość MUST dojść wysłana nowym tokenem

#### Scenario: Odpowiedź bez nowego tokenu

- **WHEN** bot-twórca odpowiada na rotację treścią bez tokenu
- **THEN** moduł MUST odmówić, oddać tę treść i MUST NOT zmienić tokenu w bazie

