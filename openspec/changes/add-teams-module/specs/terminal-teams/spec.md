## Purpose

Zakładka, w której operator składa zespół i patrzy, jak pracuje: co widać na obrazie zespołu,
jak edytuje się role i zależności, skąd bierze się lista katalogu i co pokazuje przebieg
w trakcie.

## ADDED Requirements

### Requirement: Zespół jest widoczny jako obraz zależności, nie jako lista ról

Terminal MUST pokazywać zespół jako agentów i prowadzące między nimi zależności, rozmieszczone
tak, żeby kierunek pracy dało się odczytać bez klikania. Przy każdym agencie MUST być widoczna
jego rola i model, którym pracuje.

Zależności są tu treścią, a nie ozdobą: to one decydują, kto co widzi (`teams-runs`, „Agent
widzi wypowiedzi poprzedników, a nie całą historię przebiegu"). Lista ról pokazuje wszystko
oprócz tej jednej rzeczy, dla której zespół jest zespołem.

#### Scenario: Otwarcie zapisanego zespołu

- **WHEN** operator otwiera zespół z katalogu
- **THEN** widzi jego agentów, zależności między nimi oraz rolę i model przy każdym agencie

#### Scenario: Zespół o jednym agencie

- **WHEN** operator otwiera zespół złożony z jednego agenta
- **THEN** widzi go bez żadnej zależności i może dodać kolejnych

### Requirement: Operator składa zespół w tym samym widoku, w którym go ogląda

Terminal MUST pozwalać dodać agenta, usunąć go, poprowadzić i usunąć zależność oraz zmienić
rolę, prompt, wytyczne, model i przypisane narzędzia — bez opuszczania widoku zespołu. Wybór
modelu MUST pochodzić z katalogu modeli modułu, a wybór narzędzi z tego, co moduł ogłasza;
terminal MUST NOT nieść własnej listy jednych ani drugich.

#### Scenario: Operator dokłada rolę i wiąże ją z istniejącą

- **WHEN** operator dodaje agenta i prowadzi do niego zależność od agenta już obecnego
- **THEN** obraz zespołu pokazuje nowego agenta i nową zależność

#### Scenario: Wybór modelu dla agenta

- **WHEN** operator wybiera model dla agenta
- **THEN** wybiera spośród modeli z katalogu modułu
- **AND** terminal nie ma w swoim kodzie ani jednego identyfikatora modelu

### Requirement: Rozmieszczenie agentów jest wyborem operatora i przeżywa zamknięcie widoku

Operator MUST móc przesunąć agenta na obrazie zespołu, a moduł MUST zapamiętać to
rozmieszczenie i oddać je przy kolejnym otwarciu. Rozmieszczenie MUST NOT być częścią rewizji:
przesunięcie agenta MUST NOT tworzyć nowej rewizji ani zmieniać żadnej zapisanej.

Agent, którego rozmieszczenie nie obejmuje — dołożony po ostatnim przesunięciu albo obecny
w rewizji, na której biegnie oglądany przebieg — MUST dostać miejsce wyliczone z zależności,
zamiast wylądować w rogu.

Układ automatyczny odczytuje kierunek pracy i na tym kończy swoją wiedzę. Operator wie
o swoim zespole rzeczy, których w grafie nie ma — które role są tą samą myślą, co czym jest
tylko podparte — i to jest jedyna rzecz, którą obraz może po nim zapamiętać. Poza rewizją,
bo dwa przebiegi tej samej rewizji MUST różnić się odpowiedzią modelu, nigdy pikselami.

#### Scenario: Operator przesuwa agenta i wraca do zespołu

- **WHEN** operator przesuwa agenta na obrazie zespołu, zamyka zespół i otwiera go ponownie
- **THEN** agent jest tam, gdzie operator go zostawił

#### Scenario: Przesunięcie nie jest zmianą definicji

- **WHEN** operator przesuwa agenta i nie zmienia niczego więcej
- **THEN** wersja zespołu pozostaje ta sama
- **AND** żadna zapisana rewizja się nie zmienia

#### Scenario: Agent bez zapamiętanego miejsca

- **WHEN** operator otwiera zespół, do którego dołożył agenta po ostatnim przesuwaniu
- **THEN** ten agent dostaje miejsce wyliczone z zależności, a pozostali zostają tam, gdzie ich
  zostawiono

### Requirement: Zapis odrzucony przez moduł jest pokazany przy miejscu, którego dotyczy

Gdy moduł odrzuca zapis definicji, terminal MUST pokazać przyczynę i MUST wskazać agenta albo
zależność, której odmowa dotyczy. Terminal MUST NOT poprzestać na komunikacie ogólnym.

Odmowa mówiąca „definicja niepoprawna" przy zespole o ośmiu rolach zostawia operatora
z szukaniem po omacku tego, co moduł już wie.

#### Scenario: Zapis z cyklem zależności

- **WHEN** operator zapisuje zespół, w którym zależności tworzą cykl, a moduł odmawia
- **THEN** terminal pokazuje przyczynę
- **AND** wskazuje zależność, przez którą odmowa zapadła

### Requirement: Katalog pokazuje, co jest do uruchomienia

Terminal MUST pokazywać listę zapisanych zespołów z nazwą, opisem i momentem ostatniej zmiany,
a z tej listy MUST dać się otworzyć zespół do edycji i uruchomić jego przebieg.

#### Scenario: Wejście do zakładki

- **WHEN** operator wchodzi na zakładkę zespołów
- **THEN** widzi listę zapisanych zespołów
- **AND** z każdej pozycji może otworzyć zespół albo uruchomić przebieg

### Requirement: Przebieg widać na obrazie zespołu w trakcie, nie po fakcie

W trakcie przebiegu terminal MUST pokazywać na obrazie zespołu, który agent czeka, który
pracuje, a który skończył, i MUST udostępniać to, co agenci wypracowali, oraz wywołane przez
nich narzędzia. Zamknięcie widoku MUST NOT przerwać przebiegu, a ponowne otwarcie MUST pokazać
stan bieżący.

Przebieg zespołu trwa dłużej niż jedna odpowiedź modelu. Obraz, na którym nic się nie zmienia,
nie daje odróżnić pracy od zawieszenia — a to jest pierwsza rzecz, którą operator chce
wiedzieć.

#### Scenario: Przebieg w toku

- **WHEN** przebieg trwa, a pracuje drugi z trzech agentów
- **THEN** obraz zespołu pokazuje pierwszego jako zakończonego, drugiego jako pracującego,
  a trzeciego jako czekającego

#### Scenario: Operator wraca do trwającego przebiegu

- **WHEN** operator zamyka widok przebiegu i otwiera go ponownie
- **THEN** przebieg pracuje nieprzerwanie
- **AND** widok pokazuje stan bieżący, a nie stan sprzed zamknięcia

#### Scenario: Przebieg zatrzymany z powodu kosztu

- **WHEN** przebieg zostaje zatrzymany po przekroczeniu granicy kosztu
- **THEN** terminal pokazuje koszt jako przyczynę zatrzymania
- **AND** pokazuje to, co agenci zdążyli wypracować
