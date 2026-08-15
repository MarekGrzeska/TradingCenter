# agent-chat Specification

## Purpose

Opisuje rozmowę operatora z agentem: jak sesja powstaje i trwa, co dokładnie zostaje z
niej zapisane, w jakiej kolejności, oraz jak odpowiedź modelu dociera do wołającego —
strumieniem, który może pęknąć w połowie zdania.

## Requirements

### Requirement: Sesja rozmowy trwa poza przeglądarką

Rozmowa MUST być zapisana po stronie modułu, a nie w przeglądarce: sesja i każda należąca
do niej wiadomość MUST przetrwać zamknięcie karty, restart terminala i restart samego
modułu. Sesja MUST nieść moment utworzenia oraz moment ostatniej aktywności, po którym
lista rozmów jest porządkowana — operator wraca najczęściej do tej, którą przed chwilą
zostawił.

Sesja MUST mieć tytuł nadany przez moduł przy pierwszej wymianie zdań, wyprowadzony z
pierwszej wiadomości operatora. Rozmowa nazwana „Nowa rozmowa" po dwudziestu innych
rozmowach nie daje się od nich odróżnić, a proszenie operatora o tytuł przed zadaniem
pytania odwraca kolejność, w jakiej ktokolwiek myśli.

#### Scenario: Rozmowa po restarcie modułu

- **WHEN** operator prowadzi rozmowę, moduł zostaje zrestartowany, a operator otwiera tę
  samą sesję
- **THEN** transkrypt zawiera wszystkie wcześniejsze wiadomości w tej samej kolejności
- **AND** kolejna wypowiedź dopisuje się do niego, a nie zaczyna nowego wątku

#### Scenario: Tytuł powstaje z pierwszego pytania

- **WHEN** operator wysyła pierwszą wiadomość w nowo utworzonej sesji
- **THEN** sesja dostaje tytuł wyprowadzony z treści tej wiadomości
- **AND** tytuł nie zmienia się przy kolejnych wypowiedziach

#### Scenario: Pusta sesja nie zaśmieca historii

- **WHEN** operator tworzy nową sesję i zamyka terminal, nie wysyłając w niej żadnej
  wiadomości
- **THEN** sesja bez ani jednej wiadomości MUST NOT pojawić się na liście rozmów

### Requirement: Transkrypt zachowuje kolejność i autorstwo

Każda wiadomość MUST nieść rolę swojego autora — operator albo agent — oraz porządek
względem pozostałych wiadomości w sesji, niezależny od zegara. Dwie wiadomości zapisane w
tej samej milisekundzie MUST dać się ustawić w jednej, powtarzalnej kolejności; odczyt
transkryptu MUST zwracać ją zawsze tak samo.

Wypowiedź operatora MUST być zapisana zanim moduł zawoła model. Wywołanie, które się nie
powiodło, zostawia pytanie w transkrypcie — inaczej operator traci to, co napisał, w
momencie awarii, czyli dokładnie wtedy, kiedy najmniej ma na to ochoty.

#### Scenario: Odczyt zwraca stałą kolejność

- **WHEN** transkrypt sesji jest odczytywany wielokrotnie
- **THEN** wiadomości wracają w tej samej kolejności za każdym razem

#### Scenario: Model odmawia odpowiedzi

- **WHEN** operator wysyła wiadomość, a wywołanie modelu kończy się błędem
- **THEN** wiadomość operatora zostaje w transkrypcie
- **AND** operator dostaje informację o niepowodzeniu, a nie pustą odpowiedź agenta

### Requirement: Agent pracuje na jednym prompcie systemowym

Moduł MUST prowadzić rozmowę z promptem systemowym opisującym agenta terminala
tradingowego. Prompt MUST być wersjonowany, a sesja MUST nieść identyfikator wersji, na
której powstała — bez tego o starym transkrypcie nie da się powiedzieć, na co właściwie
agent wtedy odpowiadał, a zmiana promptu unieważnia wnioski z każdej wcześniejszej
rozmowy naraz.

Prompt MUST nazywać granice agenta zgodnie z tym, co agent naprawdę ma. Gdy agent ma
narzędzia sięgające do archiwum, prompt MUST mówić, że dane pochodzą z archiwum
zbierającego wybrane pary, a nie z całego rynku, i że brak świec w zebranym oknie nie
jest ciszą rynku. Gdy agent narzędzi nie ma — bo serwer narzędzi jest niedostępny albo
nieskonfigurowany — prompt MUST mówić to samo, co mówił zawsze: agent nie widzi świec,
wskaźników ani pozycji i MUST NOT twierdzić inaczej.

Agent MUST NOT wystawiać rekomendacji inwestycyjnej. Agent MUST NOT podawać liczby jako
ceny, której nie dostał — ani z rozmowy, ani z narzędzia.

#### Scenario: Sesja pamięta wersję promptu

- **WHEN** sesja powstaje
- **THEN** zostaje przy niej zapisany identyfikator wersji promptu systemowego

#### Scenario: Prompt zmienia się między rozmowami

- **WHEN** prompt systemowy zostaje zmieniony, a operator otwiera sesję sprzed zmiany
- **THEN** transkrypt nadal wskazuje wersję, na której powstał
- **AND** dalszy ciąg tej rozmowy MUST być prowadzony na wersji obowiązującej teraz, z
  zapisem tej wersji przy nowych wiadomościach

#### Scenario: Prompt nazywa granice tego, co narzędzia mówią

- **WHEN** agent ma narzędzia sięgające do archiwum
- **THEN** prompt nazywa, że archiwum zbiera wybrane pary, a nie cały rynek
- **AND** nazywa, że brak świec nie jest sam z siebie ciszą rynku

#### Scenario: Agent bez narzędzi mówi, że ich nie ma

- **WHEN** serwer narzędzi jest niedostępny, a operator pyta o cenę
- **THEN** agent mówi, że nie ma teraz dostępu do tych danych
- **AND** MUST NOT podać liczby ani stwierdzić, że archiwum jej nie ma

### Requirement: Odpowiedź płynie strumieniem

Odpowiedź agenta MUST docierać do wołającego przyrostowo, w miarę jak powstaje, a nie
jednym blokiem po jej zakończeniu. Strumień MUST kończyć się zdarzeniem oznaczającym
domknięcie odpowiedzi — cisza na łączu jest nieodróżnialna od zerwania, a wołający MUST
mieć na czym oprzeć różnicę.

Strumień MUST nieść także wywołania narzędzi, którymi agent dochodzi do odpowiedzi, jako
zdarzenia odróżnialne od fragmentu tekstu, od domknięcia i od błędu. Wywołanie MUST
dotrzeć w chwili, w której się rozstrzygnęło, a nie po zakończeniu całej tury: runda
narzędzi trwa sekundy, w których nie powstaje żaden fragment tekstu, i bez tego jest dla
wołającego nieodróżnialna od modelu, który się zawiesił.

Zdarzenie wywołania MUST nieść nazwę narzędzia, argumenty, którymi je wywołano, to jak
się skończyło, jego wynik albo powód odmowy oraz czas trwania. Wynik MUST być tą samą
treścią, którą dostał model — wołający, który widzi streszczenie, nie ma jak stwierdzić,
że model dostał coś innego.

Wypowiedź agenta MUST być zapisana w transkrypcie w całości, także wtedy, gdy strumień
zostanie porzucony w połowie: operator, który zamknął panel, MUST znaleźć pełną odpowiedź
po powrocie do sesji. To samo MUST dotyczyć wywołań narzędzi tej tury — wołający, który
odczyta transkrypt po zakończeniu tury, MUST dostać te same wywołania, które niósł
strumień.

Wołający, który nie zna rodzaju zdarzenia, MUST móc je pominąć bez utraty odpowiedzi.

#### Scenario: Fragmenty docierają przed końcem odpowiedzi

- **WHEN** model generuje długą odpowiedź
- **THEN** wołający dostaje jej kolejne fragmenty przed jej zakończeniem

#### Scenario: Wywołanie narzędzia dociera w trakcie tury

- **WHEN** model wywołuje narzędzie i czeka na jego wynik
- **THEN** wołający dostaje zdarzenie tego wywołania, zanim przyjdzie domknięcie
  odpowiedzi
- **AND** zdarzenie niesie nazwę, argumenty, wynik albo powód odmowy oraz czas trwania

#### Scenario: Wywołanie odmówione dociera tak samo

- **WHEN** narzędzie odmawia zamiast odpowiedzieć
- **THEN** wołający dostaje zdarzenie tego wywołania z powodem odmowy
- **AND** tura toczy się dalej, a odmowa MUST NOT być podana jako błąd strumienia

#### Scenario: Wołający rozłącza się w trakcie

- **WHEN** wołający zamyka połączenie w trakcie strumienia
- **THEN** odpowiedź zostaje dokończona i zapisana w transkrypcie
- **AND** ponowny odczyt sesji zwraca ją w całości, wraz z wywołaniami narzędzi tej tury

#### Scenario: Model przerywa w połowie

- **WHEN** wywołanie modelu kończy się błędem po wysłaniu części fragmentów
- **THEN** strumień niesie zdarzenie błędu, odróżnialne od domknięcia odpowiedzi
- **AND** to, co model zdążył wypowiedzieć, MUST być zapisane wraz z oznaczeniem, że
  odpowiedź jest niepełna
- **AND** wywołania, które zdążyły paść przed błędem, MUST zostać przy tej wypowiedzi

### Requirement: Operator nazywa i usuwa rozmowy

Operator MUST móc nadać rozmowie własną nazwę w miejsce tytułu wyprowadzonego z pierwszego
pytania. Tytuł automatyczny wystarcza, dopóki rozmów jest kilka; przy kilkudziesięciu
pierwsze zdanie mówi, od czego rozmowa się zaczęła, a nie czego dotyczyła. Nazwa nadana
ręcznie MUST przetrwać kolejne wypowiedzi — moduł MUST NOT nadpisać jej tytułem
wyprowadzonym.

Operator MUST móc usunąć rozmowę z historii. Rozmowa usunięta MUST zniknąć z listy i MUST
przestać być czytelna, nieodróżnialnie od sesji, która nigdy nie istniała — tak samo jak
sesja cudza (`agent-browser-access`). Dalsza wypowiedź w usuniętej rozmowie MUST być
odmówiona.

Usunięcie MUST NOT usunąć śladu zużycia, który ta rozmowa zostawiła — patrz `agent-usage`,
„Skasowanie rozmowy nie zmniejsza rachunku".

#### Scenario: Rozmowa dostaje nazwę od operatora

- **WHEN** operator zmienia nazwę rozmowy, która miała tytuł wyprowadzony z pierwszego
  pytania
- **THEN** lista rozmów pokazuje nazwę nadaną przez operatora
- **AND** kolejna wypowiedź w tej rozmowie nie przywraca tytułu wyprowadzonego

#### Scenario: Nazwa pusta jest odmową

- **WHEN** przychodzi żądanie nadania rozmowie nazwy pustej albo złożonej z samych spacji
- **THEN** moduł odmawia
- **AND** rozmowa zachowuje nazwę, którą miała

#### Scenario: Usunięta rozmowa jest nie do odróżnienia od nieistniejącej

- **WHEN** operator usuwa rozmowę, a potem próbuje ją odczytać, przemianować albo dopisać
  do niej wypowiedź
- **THEN** moduł odpowiada tak, jakby ta sesja nie istniała
- **AND** rozmowa nie pojawia się na liście
