## MODIFIED Requirements

### Requirement: Zestaw obejmuje wybór konta i jego zasilenie

Zestaw MUST pozwalać wyliczyć konta osiągalne poświadczeniami modułu, przełączyć aktywne oraz
skorygować saldo konta demo. Rachunek, na którym agent handluje, jest warunkiem eksperymentu —
i był dotąd jedyną rzeczą w nim, której nie dało się ustawić inaczej niż ręką na stronie
dostawcy.

Wyliczenie kont MUST oznaczać, które konto jest aktywne: „ile mam" i „gdzie składam zlecenie"
MUST NOT móc dotyczyć dwóch różnych rachunków.

Każde narzędzie, które czyta albo zmienia rachunek — pozycje, zlecenia oczekujące, saldo,
składanie, zamykanie, zmiana stopów, anulowanie i korekta salda — MUST przyjmować opcjonalny
identyfikator konta i działać na tym koncie. Bez identyfikatora narzędzie MUST działać na
koncie aktywnym. Identyfikator MUST trafić do bramki w żądaniu, a MUST NOT zostać zamieniony
na przełączenie konta aktywnego: przełączenie dotyczy wszystkich wołających naraz, a wskazanie
konta tylko tego jednego wywołania. Wiersz śladu każdego wywołania zapisującego MUST nazywać
konto, na które poszło.

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

#### Scenario: Zlecenie na wskazanym koncie

- **WHEN** wołający składa zlecenie, podając identyfikator konta innego niż aktywne
- **THEN** zlecenie trafia na wskazane konto
- **AND** konto aktywne pozostaje tym, którym było

#### Scenario: Wskazane konto jest nieznane

- **WHEN** wołający podaje identyfikator konta, którego bramka nie zna
- **THEN** narzędzie odpowiada odmową nazywającą konto
- **AND** nic nie trafia na żadne konto

#### Scenario: Model koryguje saldo konta demo

- **WHEN** model koryguje saldo o kwotę dodatnią albo ujemną
- **THEN** narzędzie potwierdza wykonanie i podaje saldo po korekcie

#### Scenario: Dostawca odmawia korekty salda

- **WHEN** dostawca odrzuca korektę salda
- **THEN** narzędzie odpowiada odmową nazywającą powód
- **AND** odmowa MUST NOT być podana jako awaria dostępu do modułu
