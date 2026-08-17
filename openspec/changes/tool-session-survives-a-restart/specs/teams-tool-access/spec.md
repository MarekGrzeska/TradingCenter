## Purpose

Skąd moduł bierze narzędzia, jak łączy się z serwerem, który je publikuje, i co robi, kiedy
tego serwera nie da się zapytać — łącznie z tym, które narzędzia dostaje który agent.

## ADDED Requirements

### Requirement: Wywołanie odrzucone z powodu nieznanej sesji jest ponawiane raz

Moduł utrzymuje sesję z serwerem narzędzi między wywołaniami, a serwer może ją stracić bez
uprzedzenia — restart serwera jest tego zwykłym powodem. Kiedy serwer odrzuca wywołanie,
stwierdzając, że sesji nie zna, moduł MUST odtworzyć sesję i wysłać to samo wywołanie
**dokładnie raz** jeszcze. Drugie niepowodzenie MUST być oddane modelowi jako awaria dostępu,
bez trzeciej próby.

Ponowienie MUST być ograniczone do odpowiedzi, która **dowodzi, że żądanie nie zostało
obsłużone**. Przekroczony czas oczekiwania, awaria po stronie serwera i zerwane połączenie
MUST NOT być ponawiane: po żadnym z nich nie wiadomo, czy żądanie dotarło, a wywołanie
zmieniające rachunek powtórzone po takim stanie jest drugim zleceniem, nie ponowieniem
pierwszego. To rozróżnienie MUST być przeprowadzone na tym, co odpowiedział serwer, a nie na
nazwie wywoływanego narzędzia — narzędzie czytające i zapisujące odrzucone przy tej samej
bramce są odrzucone tak samo.

Ponowienie MUST zostawić w śladzie przebiegu **jeden** wpis wywołania. Model wywołał
narzędzie raz i ponowienie nie jest jego decyzją; ślad pokazujący dwa wpisy kazałby czytać
jako dwie próby coś, co próbą było raz.

#### Scenario: Serwer narzędzi wstał od nowa między wywołaniami

- **WHEN** serwer odrzuca wywołanie, nie znając sesji, którą moduł trzymał
- **THEN** moduł otwiera sesję na nowo i wysyła to samo wywołanie jeszcze raz
- **AND** model dostaje wynik tego wywołania, a nie awarię dostępu

#### Scenario: Sesji nie da się odtworzyć

- **WHEN** wywołanie zostaje odrzucone z powodu nieznanej sesji, a ponowienie po jej
  odtworzeniu również się nie udaje
- **THEN** model dostaje wynik nazywający awarię dostępu
- **AND** żadna trzecia próba nie jest podejmowana

#### Scenario: Wywołanie przekracza dozwolony czas

- **WHEN** wywołanie narzędzia nie kończy się odpowiedzią w dozwolonym czasie
- **THEN** moduł MUST NOT wysłać go ponownie
- **AND** model dostaje wynik nazywający awarię dostępu i nieznany skutek wywołania

#### Scenario: Ślad ponowionego wywołania

- **WHEN** wywołanie udaje się dopiero po odtworzeniu sesji
- **THEN** ślad przebiegu niesie jeden wpis tego wywołania, z jego wynikiem
