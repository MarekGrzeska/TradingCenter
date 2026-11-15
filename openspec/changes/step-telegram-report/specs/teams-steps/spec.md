## ADDED Requirements

### Requirement: Wynik strategy_execute niesie cenę i wynik transakcji

Wynik `strategy_execute` przy wejściu MUST nieść cenę wykonania. Cenę MUST brać z potwierdzenia zlecenia, a gdy
potwierdzenie jej nie niesie, z ceny otwarcia pozycji, którą zlecenie otworzyło na rachunku.

Wynik przy wyjściu MUST nieść cenę otwarcia, cenę zamknięcia, wielkość, kierunek i wynik w walucie rachunku. Wynik
MUST być różnicą salda rachunku po zamknięciu i przed nim. Gdy saldo nie zmieni się w krótkim oknie po zamknięciu,
wynik MUST być ostatnim niezrealizowanym wynikiem pozycji sprzed zamknięcia, oznaczonym jako przybliżony. Wartość,
której przepis nie zna, MUST być pusta, a nie szacowana.

#### Scenario: Wyjście z zyskiem

- **WHEN** krok zamyka własną pozycję zespołu, a saldo rachunku rośnie po zamknięciu
- **THEN** wynik kroku niesie cenę otwarcia, cenę zamknięcia i wynik równy przyrostowi salda

#### Scenario: Saldo nie zdążyło się zmienić

- **WHEN** krok zamyka pozycję, a saldo w oknie po zamknięciu jest takie jak przed nim
- **THEN** wynik kroku niesie niezrealizowany wynik pozycji sprzed zamknięcia oznaczony jako przybliżony

### Requirement: Przepis telegram_report opowiada wynik kroku bez modelu

Przepis `telegram_report` MUST przyjmować adresata (wymagany), bota (opcjonalny) i stały prefiks (opcjonalny). MUST
czytać wynik kroku `strategy_execute` przekazany mu jako praca poprzednika i MUST wysłać najwyżej jedną wiadomość przez
narzędzie wysyłające wiadomość, bez wołania modelu.

Wiadomość MUST zostać wysłana, gdy decyzja to wejście, wyjście, odmowa, wynik nieznany, strategia nieobsługiwana albo
pominięcie z innego powodu niż wcześniejsza próba na tej samej świecy sygnałowej. Przy braku działania i przy
pominięciu z powodu próby już wykonanej przepis MUST NOT wysyłać nic.

Wiadomość MUST mieć stały kształt: prefiks, rodzaj zdarzenia, symbol i kierunek, przy wejściu cenę wykonania, przy
wyjściu cenę otwarcia, cenę zamknięcia i wynik, oraz świecę sygnałową i powód. Pole, którego wynik kroku nie niesie,
MUST być napisane jako niedostępne. Przepis MUST NOT ponawiać wysyłki; nieudana wysyłka MUST być wynikiem kroku, a nie
awarią przebiegu.

#### Scenario: Wejście

- **WHEN** poprzednik kończy się wejściem z ceną wykonania
- **THEN** operator dostaje jedną wiadomość z ceną wykonania, kierunkiem i wielkością

#### Scenario: Brak działania

- **WHEN** poprzednik kończy się brakiem działania
- **THEN** żadna wiadomość nie zostaje wysłana

#### Scenario: Brak ceny w wyniku

- **WHEN** wynik poprzednika nie niesie ceny zamknięcia
- **THEN** wiadomość pisze cenę zamknięcia jako niedostępną
