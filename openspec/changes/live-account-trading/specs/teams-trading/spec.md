## MODIFIED Requirements

### Requirement: Każda granica handlowa daje się wyłączyć, a moduł żadnej nie narzuca

Każda z trzech granic MUST być pomijalna niezależnie od pozostałych, a granica pominięta
MUST znaczyć „bez ograniczenia". Moduł MUST NOT podstawiać żadnej wartości domyślnej,
MUST NOT trzymać w kodzie sufitu, którego operator nie może podnieść, i MUST NOT odmówić
zapisu ani uruchomienia wyłącznie z powodu pominiętej granicy.

Granice są narzędziem operatora, nie zgodą, której moduł mu udziela. Zespół, któremu
operator świadomie pozwala handlować całym kapitałem, MUST dać się w tym module zapisać i
uruchomić — a sufit wpisany na sztywno byłby dokładnie tą decyzją podjętą za operatora,
której ten moduł podejmować nie ma prawa. Ochroną przed nieodwracalnym skutkiem jest tu,
na koncie demo, konto demonstracyjne wymuszone u gatewaya (`trading-mcp-upstream-access`), a na koncie realnym granice
egzekwowane przez proces konta realnego (`capital-live-account`) — w obu przypadkach poza tym modułem, a nie liczba,
której nie da się zmienić.

#### Scenario: Zespół bez żadnej granicy handlowej

- **WHEN** operator zapisuje i uruchamia rewizję, której agenci mają narzędzia zapisujące,
  a która nie niesie żadnej granicy handlowej
- **THEN** zapis zostaje przyjęty, a przebieg rusza
- **AND** żadne wywołanie zapisujące nie zostaje zatrzymane z powodu granicy

#### Scenario: Jedna granica ustawiona, pozostałe pominięte

- **WHEN** definicja niesie wyłącznie maksymalną wielkość zlecenia
- **THEN** wielkość jest egzekwowana
- **AND** liczba zleceń w przebiegu i dobowa pozostają nieograniczone

#### Scenario: Granica wyższa, niż moduł uznałby za rozsądną

- **WHEN** operator ustawia granicę o dowolnie dużej wartości
- **THEN** moduł przyjmuje ją bez zmiany i egzekwuje dokładnie tę wartość

### Requirement: Rewizja może przypisać zespołowi konto

Definicja zespołu MUST móc nieść środowisko — demo albo realne, demo, gdy pominięte — oraz identyfikator konta w tym
środowisku, na którym zespół handluje. Środowisko i konto MUST być częścią rewizji, tak jak granice handlowe: dwa
warianty strategii na dwóch kontach to dwa eksperymenty, a ich porównanie wymaga, żeby każdy przebieg był opisany
środowiskiem i kontem, na którym biegł. Na demo konto MUST być pomijalne, a rewizja bez konta MUST działać na koncie
aktywnym, tak jak przed tą zmianą. Rewizje zapisane przed tą zmianą MUST czytać się jako rewizje demo.

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

- **WHEN** biegnie rewizja demo, która nie niesie konta
- **THEN** wywołania narzędzi rachunku działają na koncie aktywnym

#### Scenario: Rewizja sprzed zmiany

- **WHEN** operator odczytuje rewizję zapisaną, zanim definicja mogła nieść środowisko
- **THEN** rewizja czyta się jako rewizja demo, z tym samym kontem co przedtem

## ADDED Requirements

### Requirement: Zespół na koncie realnym idzie przez serwer narzędzi konta realnego

Rewizja ze środowiskiem realnym MUST nieść konto; zapis takiej rewizji bez konta MUST zostać odrzucony z nazwą
brakującego pola. Narzędzia rachunku zespołu ze środowiskiem realnym MUST pochodzić wyłącznie z serwera narzędzi konta
realnego, a zespołu demo — wyłącznie z instancji demo; nazwy narzędzi w rewizji MUST znaczyć to samo w obu środowiskach.
Rewizja realna przypisująca agentowi narzędzie, którego instancja realna nie wystawia, MUST zostać odrzucona z nazwą
narzędzia i agenta.

Gdy serwer narzędzi konta realnego nie jest skonfigurowany, przebieg rewizji realnej MUST zostać odmówiony przed
wywołaniem pierwszego agenta, z tą przyczyną nazwaną — tak jak dziś zespół z przypisanymi narzędziami rachunku bez
serwera narzędzi. Każdy wiersz śladu wywołania zapisującego MUST nazywać środowisko obok konta.

#### Scenario: Rewizja realna bez konta

- **WHEN** operator zapisuje rewizję ze środowiskiem realnym, która nie niesie konta
- **THEN** zapis zostaje odrzucony z nazwą brakującego konta

#### Scenario: Przebieg realny bez serwera narzędzi konta realnego

- **WHEN** biegnie rewizja ze środowiskiem realnym, a serwer narzędzi konta realnego nie jest skonfigurowany
- **THEN** moduł odmawia uruchomienia, nazywając brak serwera jako przyczynę
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Zespół realny składa zlecenie ponad granicę bramy

- **WHEN** agent zespołu realnego składa zlecenie większe niż granica bramy konta realnego
- **THEN** agent dostaje odmowę nazywającą granicę
- **AND** wiersz śladu nazywa środowisko realne, konto i odmowę
