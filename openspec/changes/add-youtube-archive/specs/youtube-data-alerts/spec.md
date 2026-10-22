## Purpose

Kiedy odczytany film jest wart wiadomości na Telegram, co znaczy „już o nim powiedziano" i co moduł
robi, gdy nie ma dokąd wysłać.

## ADDED Requirements

### Requirement: Regułę alertu wybiera kanał i temat

Każdy kanał i temat MUST nieść regułę alertu: zawsze, od progu wpływu albo nigdy. Reguła „od
progu" MUST porównywać ocenę wpływu z progiem z ustawień. Film bez odczytu MUST NOT powiadamiać
pod żadną regułą.

#### Scenario: Kanał z regułą „zawsze"

- **WHEN** film kanału z regułą „zawsze" zostaje odczytany z oceną 3
- **THEN** moduł MUST wysłać o nim wiadomość

#### Scenario: Film bez odczytu

- **WHEN** film jest przetranskrybowany, a model nie jest skonfigurowany
- **THEN** moduł MUST NOT wysłać o nim niczego

### Requirement: Znacznik po udanej wysyłce

Moduł MUST oznaczyć film jako powiadomiony dopiero po odpowiedzi bramy Telegrama oznaczającej
powodzenie, i MUST NOT powiadamiać ponownie o filmie ze znacznikiem. Nieudana wysyłka MUST zostać
ponowiona w kolejnym przebiegu.

#### Scenario: Brama odmawia

- **WHEN** brama odmawia wysłania
- **THEN** film MUST NOT dostać znacznika, a następny przebieg MUST spróbować ponownie

### Requirement: Wiadomość prowadzi do filmu

Wiadomość MUST nieść tytuł, kanał, krótkie streszczenie, instrumenty z kierunkiem, ocenę wpływu i
odnośnik do filmu na YouTube, i MUST mieścić się w limicie długości bramy.

#### Scenario: Długie streszczenie

- **WHEN** streszczenie przekracza miejsce w wiadomości
- **THEN** moduł MUST je skrócić sam, zamiast wysłać treść, której brama odmówi

### Requirement: Brak adresata jest stanem wspieranym

Gdy adresat alertów nie jest ustawiony, moduł MUST działać normalnie, MUST NOT wysyłać niczego i
MUST mówić w trasie stanu, że nie powiadamia.

#### Scenario: Adresat nieustawiony

- **WHEN** film przekracza regułę, a adresat nie jest ustawiony
- **THEN** film MUST zostać zapisany normalnie, bez błędu i bez wysyłki
