## Purpose

Opisuje rozmowę operatora z agentem: jak sesja powstaje i trwa, co dokładnie zostaje z
niej zapisane, w jakiej kolejności, oraz jak odpowiedź modelu dociera do wołającego —
strumieniem, który może pęknąć w połowie zdania.

## ADDED Requirements

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

Prompt MUST nazywać granice agenta: agent nie ma dostępu do świec, wskaźników ani pozycji
i MUST NOT twierdzić inaczej. Agent MUST NOT wystawiać rekomendacji inwestycyjnej ani
podawać liczby jako ceny, której nie widział.

#### Scenario: Sesja pamięta wersję promptu

- **WHEN** sesja powstaje
- **THEN** zostaje przy niej zapisany identyfikator wersji promptu systemowego

#### Scenario: Prompt zmienia się między rozmowami

- **WHEN** prompt systemowy zostaje zmieniony, a operator otwiera sesję sprzed zmiany
- **THEN** transkrypt nadal wskazuje wersję, na której powstał
- **AND** dalszy ciąg tej rozmowy MUST być prowadzony na wersji obowiązującej teraz, z
  zapisem tej wersji przy nowych wiadomościach

### Requirement: Odpowiedź płynie strumieniem

Odpowiedź agenta MUST docierać do wołającego przyrostowo, w miarę jak powstaje, a nie
jednym blokiem po jej zakończeniu. Strumień MUST kończyć się zdarzeniem oznaczającym
domknięcie odpowiedzi — cisza na łączu jest nieodróżnialna od zerwania, a wołający MUST
mieć na czym oprzeć różnicę.

Wypowiedź agenta MUST być zapisana w transkrypcie w całości, także wtedy, gdy strumień
zostanie porzucony w połowie: operator, który zamknął panel, MUST znaleźć pełną odpowiedź
po powrocie do sesji.

#### Scenario: Fragmenty docierają przed końcem odpowiedzi

- **WHEN** model generuje długą odpowiedź
- **THEN** wołający dostaje jej kolejne fragmenty przed jej zakończeniem

#### Scenario: Wołający rozłącza się w trakcie

- **WHEN** wołający zamyka połączenie w trakcie strumienia
- **THEN** odpowiedź zostaje dokończona i zapisana w transkrypcie
- **AND** ponowny odczyt sesji zwraca ją w całości

#### Scenario: Model przerywa w połowie

- **WHEN** wywołanie modelu kończy się błędem po wysłaniu części fragmentów
- **THEN** strumień niesie zdarzenie błędu, odróżnialne od domknięcia odpowiedzi
- **AND** to, co model zdążył wypowiedzieć, MUST być zapisane wraz z oznaczeniem, że
  odpowiedź jest niepełna
