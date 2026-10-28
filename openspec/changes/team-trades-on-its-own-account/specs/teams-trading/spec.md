## ADDED Requirements

### Requirement: Rewizja może przypisać zespołowi konto

Definicja zespołu MUST móc nieść identyfikator konta demo, na którym zespół handluje. Konto
MUST być częścią rewizji, tak jak granice handlowe: dwa warianty strategii na dwóch kontach to
dwa eksperymenty, a ich porównanie wymaga, żeby każdy przebieg był opisany kontem, na którym
biegł. Konto MUST być pomijalne, a rewizja bez konta MUST działać na koncie aktywnym, tak jak
przed tą zmianą.

Gdy rewizja niesie konto, moduł MUST wskazywać je w każdym wywołaniu narzędzia czytającego
albo zmieniającego rachunek, a wartość podana przez model MUST NOT tego zmienić. Model MUST NOT
widzieć parametru konta w schemacie narzędzia: parametr, którego nie widzi, jest parametrem,
którego nie poda błędnie.

Rewizja, która niesie konto, MUST NOT przypisywać żadnemu agentowi narzędzia przełączającego
konto aktywne ani korygującego saldo. Pierwsze przestawiłoby konto wszystkim innym wołającym,
a drugie zmieniłoby warunek eksperymentu w jego trakcie. Zapis takiej rewizji MUST zostać
odrzucony z nazwą narzędzia i agenta.

Przebieg rewizji, której konta bramka nie zna, MUST zostać odmówiony przed wywołaniem
pierwszego agenta, z nazwą konta jako przyczyną.

#### Scenario: Zespół z kontem składa zlecenie

- **WHEN** agent zespołu, którego rewizja niesie konto X, składa zlecenie
- **THEN** zlecenie trafia na konto X
- **AND** konto aktywne pozostaje tym, którym było

#### Scenario: Dwa zespoły na dwóch kontach biegną jednocześnie

- **WHEN** zespół A z kontem X i zespół B z kontem Y biegną w tym samym czasie i oba odczytują
  pozycje
- **THEN** zespół A widzi wyłącznie pozycje konta X, a zespół B wyłącznie pozycje konta Y

#### Scenario: Model podaje konto

- **WHEN** model w wywołaniu narzędzia podaje konto inne niż przypisane rewizji
- **THEN** wywołanie działa na koncie przypisanym rewizji

#### Scenario: Rewizja z kontem i narzędziem przełączającym konto

- **WHEN** operator zapisuje rewizję, która niesie konto i przypisuje agentowi narzędzie
  przełączające konto aktywne
- **THEN** zapis zostaje odrzucony z nazwą narzędzia i agenta

#### Scenario: Konto rewizji przestało istnieć

- **WHEN** operator uruchamia przebieg rewizji, której konta bramka nie zna
- **THEN** moduł odmawia uruchomienia, nazywając konto jako przyczynę
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Rewizja bez konta

- **WHEN** biegnie rewizja, która nie niesie konta
- **THEN** wywołania narzędzi rachunku działają na koncie aktywnym

## MODIFIED Requirements

### Requirement: Każde wywołanie zapisujące zostawia własny wiersz śladu

Moduł MUST zapisać wiersz na każde wywołanie narzędzia zmieniającego stan rachunku: przebieg,
agenta, konto, symbol, kierunek, wielkość, poziom, skutek oraz identyfikator zlecenia nadany
przez providera, gdy taki wrócił. Konto MUST być tym, które moduł wskazał w wywołaniu, a puste
MUST znaczyć konto aktywne. Wiersz MUST powstać przed wysłaniem wywołania i MUST zostać
uzupełniony o skutek, gdy ten wróci.

Wywołanie, którego skutek pozostał nieznany, MUST zostać zapisane jako nieznany, a MUST NOT
zostać zapisane jako nieudane ani usunięte. To jest jedyny ślad zlecenia, które mogło zostać
złożone mimo braku odpowiedzi.

#### Scenario: Zespół składa zlecenie

- **WHEN** agent składa zlecenie, a provider je wykonuje
- **THEN** ślad przebiegu niesie wiersz z kontem, symbolem, kierunkiem, wielkością, poziomem i
  identyfikatorem zlecenia
- **AND** wiersz wskazuje agenta, który je złożył

#### Scenario: Odpowiedź nie wraca

- **WHEN** wywołanie zapisujące kończy się awarią dostępu bez znanego skutku
- **THEN** wiersz śladu pozostaje ze skutkiem oznaczonym jako nieznany

#### Scenario: Odczyt zleceń przebiegu

- **WHEN** operator odczytuje ślad zakończonego przebiegu
- **THEN** widzi wszystkie wywołania zapisujące, jakie ten przebieg wykonał, wraz z ich
  skutkami i kontem
