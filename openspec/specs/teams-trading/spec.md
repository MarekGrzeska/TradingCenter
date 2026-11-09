# teams-trading Specification

## Purpose
Na jakich warunkach zespół rusza rachunek: jakie granice niesie jego rewizja, kiedy są
sprawdzane i co po każdym złożonym zleceniu zostaje w śladzie przebiegu.
## Requirements
### Requirement: Rewizja zespołu niesie własne granice handlowe

Definicja zespołu MUST móc nieść trzy granice: maksymalną wielkość jednego zlecenia, liczbę
zleceń dopuszczalną w jednym przebiegu oraz liczbę zleceń dopuszczalną dobowo dla zespołu.
Granice MUST być częścią rewizji, a MUST NOT pochodzić z konfiguracji modułu.

Dwa warianty zespołu różniące się tym, ile wolno im złożyć, to dwa różne eksperymenty. Granica
trzymana w konfiguracji byłaby jedną liczbą dla wszystkich wariantów i nie byłoby jej w
śladzie, po którym te warianty się porównuje.

#### Scenario: Odczyt rewizji z granicami

- **WHEN** operator odczytuje rewizję, której definicja niosła granice handlowe
- **THEN** rewizja niesie te same granice, na których biegły jej przebiegi

#### Scenario: Zmiana granic zapisana jako kolejna rewizja

- **WHEN** operator zmienia granice handlowe zespołu
- **THEN** powstaje kolejna rewizja
- **AND** przebiegi wykonane na poprzedniej pozostają opisane jej granicami

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

### Requirement: Granica jest sprawdzana przed wywołaniem narzędzia zapisującego

Moduł MUST sprawdzić granice handlowe przed każdym wywołaniem narzędzia zmieniającego stan
rachunku, a nie po nim. Sprawdzenie MUST zapadać w module i MUST NOT być powierzone treści
promptu.

Wyczerpanie liczby zleceń przebiegu MUST zatrzymać przebieg ze statusem nazywającym zlecenia
jako przyczynę — odróżnialnym od zatrzymania z powodu kosztu. Zlecenie przekraczające
maksymalną wielkość MUST być odmówione modelowi jako wywołanie, bez zatrzymywania przebiegu:
wielkość jest czymś, co agent może poprawić, a wyczerpany limit zleceń — nie.

#### Scenario: Przebieg wyczerpuje liczbę zleceń

- **WHEN** agent sięga po narzędzie zapisujące, a przebieg złożył już tyle zleceń, ile
  dopuszcza jego rewizja
- **THEN** wywołanie nie dochodzi do skutku
- **AND** przebieg zostaje zatrzymany ze statusem nazywającym granicę zleceń jako przyczynę

#### Scenario: Zlecenie ponad dopuszczalną wielkość

- **WHEN** agent składa zlecenie większe niż maksymalna wielkość z rewizji
- **THEN** wywołanie zostaje odmówione z komunikatem nazywającym granicę i wielkość
- **AND** przebieg pracuje dalej

#### Scenario: Zespół bez ustawionych granic handlowych

- **WHEN** przebieg biegnie na rewizji, której żaden agent nie ma narzędzia zapisującego
- **THEN** brak granic handlowych nie zatrzymuje przebiegu

### Requirement: Granica dobowa jest sprawdzana przed utworzeniem przebiegu

Moduł MUST sprawdzić dobową liczbę zleceń zespołu przed utworzeniem przebiegu i MUST odmówić
uruchomienia, gdy jest wyczerpana, nazywając granicę dobową jako przyczynę. Doba MUST być
liczona jednym zegarem modułu, od północy UTC.

Przebieg odmówiony w połowie to przebieg, który już wydał pieniądze i już ruszył rachunek.
Jeden zegar, bo limit chodzący za strefą operatora byłby latem innym limitem.

#### Scenario: Zespół wyczerpał dobową liczbę zleceń

- **WHEN** operator uruchamia przebieg zespołu, którego dobowa liczba zleceń jest wyczerpana
- **THEN** moduł odmawia uruchomienia, nazywając granicę dobową jako przyczynę
- **AND** żaden agent nie zostaje wywołany

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

