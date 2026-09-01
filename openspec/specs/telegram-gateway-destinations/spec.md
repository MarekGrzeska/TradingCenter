# telegram-gateway-destinations Specification

## Purpose
Adresat: czym jest, jak powstaje bez przepisywania liczb z telefonu, i co się z nim dzieje, kiedy
przestaje odbierać.
## Requirements
### Requirement: Adresat powstaje z tapnięcia, nie z konfiguracji

Bot Telegrama nie może odezwać się pierwszy, więc adresat MUST powstawać z tego, że człowiek raz
uruchomi rozmowę. Moduł MUST wydawać na żądanie odnośnik startowy niosący jednorazowy sekret i MUST
związać adresata dopiero wtedy, gdy ten sam sekret wróci do niego w komendzie startowej.

Konfiguracja MUST NOT być drugą drogą do tego samego: identyfikator czatu wpisany ręcznie omija
jedyny moment, w którym moduł wie, że rozmowa naprawdę istnieje.

#### Scenario: Operator prosi o adresata

- **WHEN** operator prosi o związanie nowego adresata pod nazwą
- **THEN** moduł MUST zwrócić odnośnik startowy do wskazanego bota, niosący jednorazowy sekret

#### Scenario: Tapnięcie wiąże

- **WHEN** Telegram dostarcza komendę startową z tym sekretem
- **THEN** moduł MUST związać rozmowę z nazwą, pod którą sekret został wydany

#### Scenario: Sekret zużyty albo przeterminowany

- **WHEN** ten sam sekret wraca po raz drugi albo po upływie swojej ważności
- **THEN** moduł MUST NOT związać niczego

### Requirement: Adresat, który zablokował bota, przestaje być próbowany

Moduł MUST oznaczyć adresata, którego Telegram odrzucił jako blokującego bota, i MUST przestać go
próbować, dopóki nie zostanie związany ponownie. Stan adresata MUST mówić wprost, że czeka na
ponowne uruchomienie rozmowy.

#### Scenario: Blokada

- **WHEN** wysyłka do adresata zostaje odrzucona z powodu blokady bota
- **THEN** moduł MUST zapisać ten stan, a kolejna wysyłka pod tę nazwę MUST zostać odmówiona z tym powodem

### Requirement: Usunięcie adresata nie rusza bota

Usunięcie adresata MUST usuwać wyłącznie wiązanie. Bot, przez którego szła wysyłka, MUST zostać
nietknięty, bo może obsługiwać innych adresatów.

#### Scenario: Adresat usunięty

- **WHEN** operator usuwa adresata
- **THEN** bot MUST pozostać, a pozostali adresaci tego bota MUST dalej odbierać
