## MODIFIED Requirements

### Requirement: Adresat powstaje z tapnięcia, nie z konfiguracji

Bot Telegrama nie może odezwać się pierwszy, więc wiązanie adresata MUST powstawać z tego, że człowiek raz uruchomi
rozmowę **z tym botem**. Moduł MUST wydawać na żądanie odnośnik startowy niosący jednorazowy sekret i MUST związać
adresata z botem dopiero wtedy, gdy ten sam sekret wróci do niego w komendzie startowej.

Ta sama nazwa adresata MAY być związana przez kilku botów. Każde takie wiązanie ma własny czat, własny stan i własne
tapnięcie, bo uruchomienie rozmowy z jednym botem nie daje drugiemu prawa pisać. Para (nazwa, bot) MUST być unikalna;
sama nazwa MUST NOT.

Konfiguracja MUST NOT być drugą drogą do tego samego: identyfikator czatu wpisany ręcznie omija jedyny moment, w którym
moduł wie, że rozmowa naprawdę istnieje.

#### Scenario: Operator prosi o adresata

- **WHEN** operator prosi o związanie nowego adresata pod nazwą przez wskazanego bota
- **THEN** moduł MUST zwrócić odnośnik startowy do tego bota, niosący jednorazowy sekret

#### Scenario: Ten sam adresat przez drugiego bota

- **WHEN** operator prosi o związanie nazwy, która jest już związana przez innego bota, przez drugiego bota
- **THEN** moduł MUST utworzyć drugie wiązanie pod tą samą nazwą z własnym odnośnikiem startowym i MUST NOT zmienić pierwszego

#### Scenario: Tapnięcie wiąże

- **WHEN** Telegram dostarcza komendę startową z tym sekretem
- **THEN** moduł MUST związać rozmowę z nazwą i botem, pod którymi sekret został wydany

#### Scenario: Sekret zużyty albo przeterminowany

- **WHEN** ten sam sekret wraca po raz drugi albo po upływie swojej ważności
- **THEN** moduł MUST NOT związać niczego

### Requirement: Adresat, który zablokował bota, przestaje być próbowany

Moduł MUST oznaczyć wiązanie, które Telegram odrzucił jako blokujące bota, i MUST przestać je próbować, dopóki nie
zostanie związane ponownie. Stan MUST mówić wprost, że czeka na ponowne uruchomienie rozmowy. Blokada jednego bota MUST
NOT zmieniać wiązania tej samej nazwy przez innego bota.

#### Scenario: Blokada

- **WHEN** wysyłka przez wiązanie zostaje odrzucona z powodu blokady bota
- **THEN** moduł MUST zapisać ten stan, a kolejna wysyłka przez to samo wiązanie MUST zostać odmówiona z tym powodem

#### Scenario: Blokada jednego bota

- **WHEN** adresat zablokował jednego ze swoich botów
- **THEN** wysyłka tej samej nazwy przez drugiego bota MUST nadal dochodzić

### Requirement: Usunięcie adresata nie rusza bota

Usunięcie MUST usuwać wyłącznie jedno wiązanie (nazwa, bot). Bot MUST zostać nietknięty, a pozostałe wiązania tej
samej nazwy przez innych botów MUST dalej działać. Gdy nazwa ma kilka wiązań, a prośba nie wskazuje bota, moduł MUST
odmówić i wymienić boty, zamiast usuwać wszystkie albo wybierać jedno.

#### Scenario: Adresat usunięty

- **WHEN** operator usuwa wiązanie adresata przez wskazanego bota
- **THEN** bot MUST pozostać, a pozostali adresaci tego bota i wiązania tej nazwy przez innych botów MUST dalej odbierać

#### Scenario: Usunięcie bez wskazania bota przy kilku wiązaniach

- **WHEN** nazwa ma dwa wiązania, a prośba o usunięcie nie wskazuje bota
- **THEN** moduł MUST odmówić nazywając oba boty i MUST NOT usunąć niczego
