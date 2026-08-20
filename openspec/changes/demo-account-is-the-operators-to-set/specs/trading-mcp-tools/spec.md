## ADDED Requirements

### Requirement: Zestaw obejmuje wybór konta i jego zasilenie

Zestaw MUST pozwalać wyliczyć konta osiągalne poświadczeniami modułu, przełączyć aktywne oraz
skorygować saldo konta demo. Rachunek, na którym agent handluje, jest warunkiem eksperymentu —
i był dotąd jedyną rzeczą w nim, której nie dało się ustawić inaczej niż ręką na stronie
dostawcy.

Wyliczenie kont MUST oznaczać, które konto jest aktywne: „ile mam" i „gdzie składam zlecenie"
MUST NOT móc dotyczyć dwóch różnych rachunków.

Opis narzędzia przełączającego konto MUST mówić, że przełączenie zrywa strumień notowań, i że
przerwa dotyczy zbierania danych, a nie tej rozmowy. Model, który tego nie wie, przełącza
konto w środku zbierania świec i nie ma jak zauważyć skutku — strumień jest po drugiej
stronie systemu, a narzędzie odpowiada mu sukcesem.

Korekta salda MUST przyjmować kwotę ujemną tak samo jak dodatnią. Odmowa dostawcy — sufit
salda, zakres kwoty, wyczerpany limit dobowy — MUST dotrzeć jako odmowa nazywająca powód,
odróżnialna od awarii dostępu, tak jak każda inna odmowa w tym zestawie.

#### Scenario: Model wylicza konta

- **WHEN** model prosi o listę kont
- **THEN** każde konto niesie identyfikator, nazwę, walutę i saldo
- **AND** dokładnie jedno jest oznaczone jako aktywne

#### Scenario: Model przełącza konto

- **WHEN** model przełącza aktywne konto na znany identyfikator
- **THEN** narzędzie potwierdza, które konto jest teraz aktywne
- **AND** jego opis mówi, że przełączenie zrywa strumień notowań

#### Scenario: Model koryguje saldo konta demo

- **WHEN** model koryguje saldo o kwotę dodatnią albo ujemną
- **THEN** narzędzie potwierdza wykonanie i podaje saldo po korekcie

#### Scenario: Dostawca odmawia korekty salda

- **WHEN** dostawca odrzuca korektę salda
- **THEN** narzędzie odpowiada odmową nazywającą powód
- **AND** odmowa MUST NOT być podana jako awaria dostępu do modułu

## MODIFIED Requirements

### Requirement: Narzędzie zapisujące jest oznaczone jako zmieniające stan

Każde narzędzie zmieniające stan rachunku MUST być tak oznaczone w tym, co moduł ogłasza,
a narzędzie wyłącznie czytające MUST być oznaczone jako czytające. Oznaczenie MUST być
zgodne z tym, co narzędzie robi.

Zmianą stanu jest także wybór rachunku i jego zasilenie, nie tylko ruch na rynku:
przełączenie konta zmienia to, czego dotyczy każde następne zlecenie, a korekta salda zmienia
ilość pieniędzy, którymi agent dysponuje. Oba MUST być oznaczone jako zmieniające stan.

Wywołujący, który dobiera agentom narzędzia, ma z ogłoszenia poznać, które z nich ruszają
pieniądze — bez czytania kodu tego modułu i bez zgadywania z nazwy.

#### Scenario: Klient czyta listę narzędzi

- **WHEN** klient MCP prosi o listę narzędzi
- **THEN** narzędzia składające zlecenie, zamykające pozycję, zmieniające stopy i anulujące
  zlecenie są oznaczone jako zmieniające stan
- **AND** narzędzia przełączające aktywne konto oraz korygujące saldo są oznaczone jako
  zmieniające stan
- **AND** narzędzia o pozycjach, zleceniach oczekujących, saldzie i liście kont są oznaczone
  jako czytające
