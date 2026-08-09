# terminal-dialogs Specification

## Purpose
Opisuje, jak terminal pyta operatora o zgodę: że pytanie ma zawsze formę modalnego dialogu, co taki
dialog musi powiedzieć i jak się zachować, gdy praca trwa albo zawodzi, oraz dlaczego wszystkie
dialogi terminala wychodzą z jednego miejsca zamiast być pisane od nowa przy każdym pytaniu.

## Requirements
### Requirement: Pytanie o zgodę jest dialogiem, nie interfejsem w miejscu

Każde pytanie, po którym terminal zrobi coś nieodwracalnego, kosztownego albo zmieniającego stan
archiwum, MUST być zadane w modalnym dialogu. Terminal MUST NOT pytać o zgodę interfejsem
doklejonym do miejsca, z którego padło pytanie — wierszem dopisanym do tabeli, panelem
rozwijanym pod przyciskiem ani paskiem wsuniętym nad listę.

Powód jest jeden: pytanie doklejone do listy konkuruje o uwagę z listą i dziedziczy po niej zakres.
Wiersz z pytaniem stojący przy jednym wierszu tabeli mówi „dotyczy tego wiersza", nawet gdy dotyczy
czegoś szerszego — a operator czyta położenie, zanim przeczyta zdanie.

Zasada dotyczy pytania, nie odpowiedzi. Terminal MAY pokazywać w miejscu to, co się już wydarzyło —
komunikat o skutku, wiersz, który zmienił stan, ostrzeżenie o nieudanym odświeżeniu — bo to nie jest
prośba o decyzję.

#### Scenario: Operator wywołuje działanie wymagające zgody

- **WHEN** operator wybiera działanie, które terminal wykona dopiero po potwierdzeniu
- **THEN** terminal otwiera modalny dialog z tym pytaniem
- **AND** MUST NOT dopisywać pytania do listy ani do wiersza, przy którym stał przycisk

#### Scenario: Komunikat o tym, co się stało

- **WHEN** terminal ma powiedzieć, co już zostało zrobione, i o nic nie pyta
- **THEN** MAY powiedzieć to w miejscu, bez otwierania dialogu

### Requirement: Dialog nazywa skutek i jego zakres

Dialog MUST nazwać, co się stanie po potwierdzeniu, i czego to obejmie — ile rzeczy, jakich, i
w jakim zakresie. Gdy skutek jest nieodwracalny, dialog MUST stwierdzić to wprost. Dialog MUST mieć
akcję potwierdzającą i akcję wycofującą, a wycofanie MUST NOT zmieniać niczego.

Nazwa akcji potwierdzającej MUST opisywać to, co faktycznie się zdarzy, w zakresie, w jakim się
zdarzy. Przycisk obiecujący węziej niż działa jest błędem tej samej wagi co brak potwierdzenia:
operator zatwierdza wtedy coś innego, niż przeczytał.

#### Scenario: Dialog przed działaniem obejmującym wiele rzeczy

- **WHEN** potwierdzane działanie obejmie więcej niż jedną rzecz
- **THEN** dialog podaje, ile ich jest i jakie są
- **AND** akcja potwierdzająca jest nazwana zakresem całości, a nie jednej z nich

#### Scenario: Operator się wycofuje

- **WHEN** operator wybiera wycofanie albo zamyka dialog bez potwierdzenia
- **THEN** nic nie zostaje zrobione
- **AND** widok pod dialogiem pozostaje w stanie sprzed pytania

### Requirement: Dialog zostaje na ekranie, dopóki praca trwa

Po potwierdzeniu dialog MUST pozostać otwarty do rozstrzygnięcia pracy i MUST powiedzieć, że praca
trwa. Dialog MUST NOT dopuścić do potwierdzenia tej samej pracy dwa razy z rzędu.

Powodzenie MUST zakończyć pytanie: dialog MUST się zamknąć albo zastąpić pytanie wynikiem, który
operator już tylko przyjmuje do wiadomości. Zastąpienie wynikiem jest dopuszczalne wtedy i tylko
wtedy, gdy praca zwróciła coś, czego widok pod dialogiem nie pokaże — częściową odmowę, listę tego,
co faktycznie ruszyło. Dialog pokazujący wynik MUST NOT nieść akcji, która wykonałaby tę samą pracę
po raz drugi.

#### Scenario: Praca trwa

- **WHEN** operator potwierdził, a terminal czeka na odpowiedź archiwum
- **THEN** dialog pozostaje otwarty i mówi, że praca trwa
- **AND** ponowne wybranie akcji potwierdzającej nie zleca tej pracy drugi raz

#### Scenario: Praca się udaje

- **WHEN** potwierdzona praca kończy się powodzeniem, a odpowiedź nie niesie nic ponad sam fakt
- **THEN** dialog się zamyka
- **AND** widok pod nim pokazuje stan po tej pracy

#### Scenario: Praca udaje się połowicznie

- **WHEN** potwierdzona praca zwraca wynik, którego widok pod dialogiem nie pokaże — na przykład
  odmowę części tego, o co poszła
- **THEN** dialog zastępuje pytanie tym wynikiem
- **AND** nie da się z niego zlecić tej samej pracy drugi raz

### Requirement: Nieudana praca zostaje w dialogu

Gdy potwierdzona praca zawiedzie, dialog MUST pozostać otwarty, MUST nazwać przyczynę w sobie i
MUST zostawić możliwość spróbowania raz jeszcze. Terminal MUST NOT zamykać dialogu po nieudanej
próbie — komunikat wyrzucony do widoku, z którego dialog właśnie zniknął, traci związek z decyzją,
którą tłumaczy.

Przyczyna MUST być nazwana bez cytowania poświadczenia operatora ani jego fragmentu, tak samo jak
w każdym innym komunikacie terminala.

#### Scenario: Archiwum odmawia

- **WHEN** potwierdzona praca kończy się błędem
- **THEN** dialog pozostaje otwarty i podaje przyczynę
- **AND** operator może spróbować ponownie albo się wycofać

#### Scenario: Widok pod dialogiem po nieudanej próbie

- **WHEN** potwierdzona praca zawiodła
- **THEN** widok pod dialogiem MUST NOT wyglądać, jakby praca ruszyła

### Requirement: Dialog obsługuje się klawiaturą

Otwarty dialog MUST przejąć fokus, a klawisz `Escape` MUST go zamknąć tak samo jak wycofanie się —
z jednym wyjątkiem: dialog czekający na rozstrzygnięcie potwierdzonej pracy MUST NOT dać się w ten
sposób zamknąć, bo praca trwa niezależnie od tego, czy operator na nią patrzy. Fokus klawiatury
MUST pozostawać wewnątrz dialogu, dopóki jest otwarty, a po zamknięciu MUST wrócić na element,
z którego dialog został wywołany.

Dialog MUST być ogłoszony jako dialog i MUST nieść własną nazwę, żeby czytnik ekranu podał, o co
pytanie, a nie tylko że coś się otworzyło.

#### Scenario: Zamknięcie klawiaturą

- **WHEN** operator naciska `Escape` w otwartym dialogu, w którym nic jeszcze nie potwierdził
- **THEN** dialog zamyka się, nic nie robiąc
- **AND** fokus wraca na element, z którego dialog został otwarty

#### Scenario: Escape w trakcie pracy

- **WHEN** operator naciska `Escape`, a potwierdzona praca trwa
- **THEN** dialog pozostaje otwarty

#### Scenario: Fokus po otwarciu

- **WHEN** dialog się otwiera
- **THEN** fokus jest w środku dialogu
- **AND** nie da się go klawiaturą przenieść na to, co jest pod dialogiem

### Requirement: Wszystkie dialogi wychodzą z jednego miejsca

Zachowania opisane wyżej — fokus, klawiatura, praca w toku, błąd zatrzymany w dialogu, układ akcji
potwierdzającej i wycofującej — MUST być zapewnione przez jedną wspólną część terminala, z której
korzysta każdy dialog. Dołożenie kolejnego pytania o zgodę MUST NOT wymagać napisania tych zachowań
po raz kolejny; miejsce pytające MUST dostarczać wyłącznie treść pytania i to, co ma się stać po
potwierdzeniu.

Powielone dialogi rozjeżdżają się po jednym zachowaniu naraz — jeden łapie fokus, drugi nie; jeden
zostaje po błędzie, drugi znika — i operator przestaje wiedzieć, czego się po nich spodziewać.

#### Scenario: Nowe pytanie o zgodę

- **WHEN** do terminala dochodzi kolejne działanie wymagające potwierdzenia
- **THEN** jego dialog zachowuje się identycznie jak pozostałe, bez powtarzania tych zachowań
  w kodzie miejsca pytającego

#### Scenario: Zmiana wspólnego zachowania

- **WHEN** zmienia się sposób, w jaki dialogi obsługują pracę w toku
- **THEN** zmiana obejmuje każde miejsce pytające o zgodę, bez edycji każdego z osobna
