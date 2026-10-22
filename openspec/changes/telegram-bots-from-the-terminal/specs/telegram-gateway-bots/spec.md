## MODIFIED Requirements

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

## ADDED Requirements

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

### Requirement: Bot z przypisaniem nie znika po cichu

Usunięcie bota, którego którykolwiek adresat ma przypisany cel, MUST być odmową nazywającą te cele.
Moduł MUST NOT usuwać przypisań kaskadowo.

Usunięty bot z przypisaniem to alerty, które przestają przychodzić bez jednej odmowy, którą ktoś by
zobaczył.

#### Scenario: Usunięcie bota z przypisaniem

- **WHEN** operator prosi o usunięcie bota, którego adresat dostaje cel `youtube`
- **THEN** moduł MUST odmówić, nazywając cel `youtube`, i MUST NOT odezwać się do bota-twórcy
